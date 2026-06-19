# run_review_multi.py — S3-first prompt loader (Runpod), no local prompts required
from __future__ import annotations

import os
import re
import json
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, conint  # for structured aggregator output

# langchain_google_vertexai pulls in `transformers`, which imports `torch` by default.
# On machines with a broken/GPU-only torch build that crashes the import. This app only
# needs tokenizers, so disable the heavy ML backends BEFORE the langchain import. (Must be
# set here, not via .env — transformers reads these at import time, before load_dotenv runs.)
os.environ.setdefault("USE_TORCH", "0")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_FLAX", "0")

try:
    from langchain_google_vertexai import ChatVertexAI  # type: ignore[import]
except Exception:  # pragma: no cover — missing/broken in some envs
    ChatVertexAI = None  # type: ignore[assignment,misc]

# Use the shared normalizer/sanitizer so artifacts are cleaned before UI
from utils1 import normalize_review_payload

# Grounded Facts call (Task 3)
from facts_grounding import grounded_generate

# -----------------------------
# Runpod S3 client (boto3)
# -----------------------------
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

load_dotenv()

_RP_ENDPOINT = os.getenv("RUNPOD_S3_ENDPOINT", "").strip()
_RP_BUCKET   = os.getenv("RUNPOD_S3_BUCKET", "").strip()
_RP_REGION   = os.getenv("RUNPOD_S3_REGION", "").strip()

def _s3_enabled() -> bool:
    return bool(_RP_ENDPOINT and _RP_BUCKET)

_S3_CLIENT = None
def _s3_client():
    global _S3_CLIENT
    if _S3_CLIENT is not None:
        return _S3_CLIENT
    if not _s3_enabled():
        return None
    _S3_CLIENT = boto3.client(
        "s3",
        endpoint_url=_RP_ENDPOINT,
        region_name=_RP_REGION or None,
        config=Config(s3={"addressing_style": "path"})
    )
    return _S3_CLIENT

def _read_s3_text(key: str) -> Optional[str]:
    """Return object body as UTF-8 text or None."""
    cli = _s3_client()
    if not cli:
        return None
    try:
        obj = cli.get_object(Bucket=_RP_BUCKET, Key=key)
        return obj["Body"].read().decode("utf-8", errors="ignore")
    except ClientError:
        return None
    except Exception:
        return None

def _join_s3_key(prefix: str, filename: str) -> str:
    return f"{prefix.rstrip('/')}/{filename.lstrip('/')}"

# -----------------------------------------------------------------------------#
# Env / model
# -----------------------------------------------------------------------------#
def _require_vertex_config() -> None:
    """
    Vertex AI authenticates via a Google Cloud project + service-account
    credentials (Application Default Credentials), NOT an API key.
    Requires GOOGLE_CLOUD_PROJECT (and GOOGLE_APPLICATION_CREDENTIALS pointing
    at a service-account JSON, unless running on GCP with ambient credentials).
    """
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        raise EnvironmentError(
            "GOOGLE_CLOUD_PROJECT not set. Vertex AI needs a GCP project id in "
            "the environment/.env (and GOOGLE_APPLICATION_CREDENTIALS pointing "
            "at a service-account JSON)."
        )

def _make_llm(temperature: float):
    """
    Create a Gemini chat LLM on Vertex AI with minimal, deterministic-ish defaults.
    Project/region/credentials are read from the environment (.env):
      GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, GOOGLE_APPLICATION_CREDENTIALS
    """
    _llm_cls = ChatVertexAI
    if _llm_cls is None:
        from langchain_google_vertexai import ChatVertexAI as _llm_cls  # type: ignore[assignment]
    model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
    location = os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"
    return _llm_cls(
        model=model,
        temperature=temperature,
        top_p=0.0,
        top_k=1,
        project=project,
        location=location,
    )

# -----------------------------------------------------------------------------#
# Prompt loaders (S3-first; local fallback)
# -----------------------------------------------------------------------------#
def _strip_bom(s: str) -> str:
    return s.lstrip("﻿") if s and s.startswith("﻿") else s

def _read_text_local(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return _strip_bom(f.read())

def _extract_content_block(raw: str) -> str:
    """
    If the YAML uses:
      content: |
        ...
    extract that block; else return whole file.
    """
    raw = raw.strip()
    m = re.search(r"^\s*content\s*:\s*\|?\s*(.*)$", raw, flags=re.S | re.I)
    txt = (m.group(1) if m else raw).replace("\r\n", "\n")
    return txt.strip()

def _load_prompt_s3(prompts_prefix: str, n: int) -> Optional[str]:
    """
    Try S3: {prompts_prefix}/{n}.yaml then {n}.yml
    Returns the prompt text or None if not found.
    """
    if not _s3_enabled():
        return None
    for ext in ("yaml", "yml"):
        key = _join_s3_key(prompts_prefix, f"{n}.{ext}")
        txt = _read_s3_text(key)
        if txt:
            return _extract_content_block(txt)
    return None

def _load_prompt_local(prompts_dir: str, n: int) -> Optional[str]:
    """
    Local fallback if S3 not configured.
    """
    for ext in ("yaml", "yml"):
        p = os.path.join(prompts_dir, f"{n}.{ext}")
        if os.path.isfile(p):
            raw = _read_text_local(p)
            return _extract_content_block(raw)
    return None

def _load_prompt(prompts_dir_or_prefix: str, n: int) -> str:
    """
    Unified loader: prefer S3 (Runpod) if configured; else local.
    `prompts_dir_or_prefix` should be something like "Scriptmodel/prompts".
    """
    # If the caller accidentally passes an s3:// url, strip it to a key prefix:
    prefix = prompts_dir_or_prefix
    if prefix.startswith("s3://"):
        # s3://bucket/... => strip "s3://<bucket>/" so we keep only the key
        parts = prefix.split("/", 3)
        prefix = parts[3] if len(parts) > 3 else ""

    # S3 first
    txt = _load_prompt_s3(prefix, n)
    if txt:
        return txt

    # Local fallback (only if S3 off or missing file)
    txt = _load_prompt_local(prompts_dir_or_prefix, n)
    if txt:
        return txt

    where = f"S3({_RP_BUCKET}:{prefix})" if _s3_enabled() else os.path.abspath(prompts_dir_or_prefix)
    raise FileNotFoundError(f"Prompt {n} (yaml/yml) not found in {where}")

def _inject(template: str, **kwargs: str) -> str:
    out = template
    for k, v in kwargs.items():
        out = out.replace("{" + k + "}", v)
    return out

# -----------------------------------------------------------------------------#
# JSON extraction (for specialists that return plain JSON)
# -----------------------------------------------------------------------------#
_BEGIN = "BEGIN_JSON"
_END = "END_JSON"

def _between_tokens(text: str, start: str, end: str) -> Optional[str]:
    i = text.find(start)
    j = text.rfind(end)
    if i == -1 or j == -1 or j <= i:
        return None
    return text[i + len(start): j].strip()

def _fenced(text: str) -> Optional[str]:
    m = re.search(r"```json\s*(.*?)\s*```", text, flags=re.S | re.I)
    if m: return m.group(1).strip()
    m = re.search(r"```\s*(.*?)\s*```", text, flags=re.S)
    if m: return m.group(1).strip()
    return None

def _balanced(text: str) -> Optional[str]:
    start = text.find("{")
    if start == -1: return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i+1]
    return None

def _normalize_curly_quotes(s: str) -> str:
    """Translate curly/smart quotes to straight ASCII equivalents."""
    return (
        s.replace("“", '"').replace("”", '"')
         .replace("‘", "'").replace("’", "'")
    )

def _parse_json(text: str) -> Dict[str, Any]:
    """
    Try multiple strategies to extract valid JSON. Tolerates trailing commas
    and curly/smart quotes (U+201C/U+201D/U+2018/U+2019).
    """
    for candidate in filter(None, (_between_tokens(text, _BEGIN, _END),
                                  _fenced(text), _balanced(text))):
        try:
            return json.loads(candidate)
        except Exception:
            try:
                fixed = re.sub(r",\s*([\]}])", r"\1", candidate)
                return json.loads(fixed)
            except Exception:
                pass
        # Third attempt: normalize curly quotes then strip trailing commas
        try:
            normalized = _normalize_curly_quotes(candidate)
            normalized = re.sub(r",\s*([\]}])", r"\1", normalized)
            return json.loads(normalized)
        except Exception:
            continue
    raise ValueError("Could not parse JSON from model output")

# -----------------------------------------------------------------------------#
# Conversions -> legacy block for UI
# -----------------------------------------------------------------------------#
def _coerce_explanation(raw: Dict[str, Any]) -> str:
    """
    Accept 'explanation' (string) or 'explanation_bullets' (list[str]).
    """
    explanation = raw.get("explanation", "")
    if isinstance(explanation, str) and explanation.strip():
        return explanation.strip()
    bullets = raw.get("explanation_bullets", [])
    if isinstance(bullets, list) and bullets:
        parts = [str(b).strip().rstrip(".") + "." for b in bullets if str(b).strip()]
        return " ".join(parts)[:1400]
    return ""

def _to_legacy_param_block(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a specialist block to the legacy shape expected by the UI.
    - Raw 'extractions' are intentionally suppressed (we only use AOIs for inline highlights).
    - AOIs pass through untouched (4-field schema, unlimited).
    - 'summary' (plain human note) is passed through for right-panel display.
    """
    score = int(raw.get("score", 0) or 0)
    explanation = _coerce_explanation(raw)
    weakness = str(raw.get("weakness", "") or "").strip() or "Not present"

    # Keep single suggestion for legacy UI AND preserve full list if present
    suggestion = str(raw.get("suggestion", "") or "").strip()
    suggestions_list: List[str] = []
    if not suggestion and isinstance(raw.get("suggestions"), list) and raw["suggestions"]:
        suggestions_list = [str(s).strip() for s in raw["suggestions"] if str(s).strip()]
        suggestion = suggestions_list[0] if suggestions_list else ""
    elif isinstance(raw.get("suggestions"), list):
        suggestions_list = [str(s).strip() for s in raw["suggestions"] if str(s).strip()]
    suggestion = suggestion or "Not present"

    # Hide raw extractions in UI—AOIs only
    ex: List[str] = []
    aoi = raw.get("areas_of_improvement") or []

    block: Dict[str, Any] = {
        "extractions": ex,  # kept in schema but always empty
        "score": score,
        "explanation": explanation,
        "weakness": weakness,
        "suggestion": suggestion,
        "areas_of_improvement": aoi,
        "summary": str(raw.get("summary", "") or "").strip(),
    }
    if suggestions_list:
        block["suggestions_list"] = suggestions_list
    return block

# -----------------------------------------------------------------------------#
# Display-name mapping for UI & aggregator
# -----------------------------------------------------------------------------#
DISPLAY_BY_INDEX = {
    1: "Grammar",
    2: "Spelling",
    3: "Punctuation",
    4: "Style/Clarity",
    5: "Facts",
    # 6 = aggregator, 7 = shared preamble
}

# -----------------------------------------------------------------------------#
# LLM invoke with retries
# -----------------------------------------------------------------------------#
def _invoke_with_retries(llm: ChatVertexAI, prompt: str, tries: int = 3, base_delay: float = 0.8):
    last_err = None
    for k in range(tries):
        try:
            return llm.invoke(prompt)
        except Exception as e:
            last_err = e
            if k < tries - 1:
                time.sleep(base_delay * (2 ** k))
            else:
                raise
    raise last_err  # type: ignore

# -----------------------------------------------------------------------------#
# Aggregator structured schema (model returns this)
# -----------------------------------------------------------------------------#
class AggregatorAll(BaseModel):
    overall_rating: conint(ge=1, le=10)
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]
    summary: str
    corrected_text: str

# -----------------------------------------------------------------------------#
# Core runner
# -----------------------------------------------------------------------------#
def run_review_multi(
    script_text: str,
    prompts_dir: str = "Scriptmodel/prompts",
    temperature: float = 0.0,
    include_commentary: bool = False,  # kept for API parity; ignored
) -> str:
    """
    Execute prompts 1..5 (specialists) with preamble from 7.yaml, route Facts
    through grounded_generate, then aggregate with 6.yaml.
    Returns BEGIN_JSON ... END_JSON for the UI.

    NOTE: `prompts_dir` is treated as an S3 prefix (e.g., "Scriptmodel/prompts") when
    RUNPOD_S3_* env vars are set. If S3 is not configured, it falls back to local files.
    """
    _require_vertex_config()
    llm = _make_llm(temperature)

    # Shared preamble (7.yaml) if present
    try:
        global_preamble = _load_prompt(prompts_dir, 7).strip()
        if global_preamble:
            global_preamble += "\n\n"
    except FileNotFoundError:
        global_preamble = ""

    scores: Dict[str, int] = {}
    per_parameter: Dict[str, Dict[str, Any]] = {}

    for i in range(1, 5 + 1):
        name = DISPLAY_BY_INDEX[i]
        tmpl = _load_prompt(prompts_dir, i)
        prompt_body = _inject(tmpl, script=script_text)
        prompt = f"{global_preamble}{prompt_body}"

        try:
            if name == "Facts":
                raw_text = grounded_generate(prompt, temperature=temperature)
            else:
                resp = _invoke_with_retries(llm, prompt)
                raw_text = getattr(resp, "content", "") or ""
            data = _parse_json(raw_text)
        except Exception as e:
            short = (str(e) or "unknown").strip()
            raise RuntimeError(f"JSON parse failed on prompt {i} ({name}). Error: {short}")

        block = _to_legacy_param_block(data)
        scores[name] = int(block.get("score", 0))
        per_parameter[name] = block

    evidence = {"scores": scores, "per_parameter": per_parameter}
    evidence_json = json.dumps(evidence, ensure_ascii=False)

    tmpl6 = _load_prompt(prompts_dir, 6)
    prompt6_body = _inject(tmpl6, evidence_json=evidence_json, script=script_text)
    prompt6 = f"{global_preamble}{prompt6_body}"

    try:
        llm_aggr = _make_llm(temperature).with_structured_output(AggregatorAll)
        agg: AggregatorAll = llm_aggr.invoke(prompt6)
    except Exception as e:
        short = (str(e) or "unknown").strip()
        raise RuntimeError(f"Aggregator failed on prompt 6. Error: {short}")

    final_payload: Dict[str, Any] = {
        "scores": scores,
        "per_parameter": per_parameter,
        "overall_rating": int(agg.overall_rating),
        "strengths": agg.strengths,
        "weaknesses": agg.weaknesses,
        "suggestions": agg.suggestions,
        "summary": agg.summary,
        "corrected_text": agg.corrected_text,
    }

    final_payload = normalize_review_payload(final_payload)
    return _wrap_json(final_payload)

def _wrap_json(payload: Dict[str, Any]) -> str:
    return f"{_BEGIN}\n{json.dumps(payload, ensure_ascii=False)}\n{_END}\n"
