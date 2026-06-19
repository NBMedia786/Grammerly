# factcheck.py — verify factual claims (dates, names, events, stats) in a script
# against the web, using Gemini + Google Search grounding on Vertex AI.
#
# If Google Search grounding isn't available in the installed Vertex SDK, it
# falls back to the model's own knowledge and flags web_grounded=False so the
# UI can tell the user the check wasn't live-web-verified.

from __future__ import annotations

import os
from typing import Any, Dict, List

from dotenv import load_dotenv

from utils1 import extract_review_json

load_dotenv()

_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"
_MODEL = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"

_PROMPT = """You are a rigorous fact-checker for short-video scripts.
Read the SCRIPT and extract EVERY checkable factual claim. Pay special attention to:
- dates and years, time periods, centuries ("in 1944", "during the 1980s")
- historical events and the order they happened in
- names, titles, attributions ("invented by", "the first to", "directed by")
- places and geography
- numbers, statistics, measurements and records ("largest", "oldest", "fastest")

For each claim decide one verdict:
- "correct"      -> matches authoritative real-world facts
- "incorrect"    -> contradicts authoritative facts
- "unverifiable" -> a checkable factual claim you cannot confirm or deny from reliable sources

STRICT RULES:
- "quote_verbatim" MUST be copied EXACTLY from the script (a real substring) so it can be highlighted.
- For "incorrect": "correction" MUST be a DROP-IN REPLACEMENT for quote_verbatim with the fact fixed,
  keeping the same wording where possible. Example: quote "the war ended in 1944" -> correction "the war ended in 1945".
- For "correct"/"unverifiable": "correction" may be "".
- "sources" = up to 3 source URLs (or source names) you relied on. May be empty.
- Do NOT flag opinions, jokes, predictions, or obvious dramatization. Only judge concrete, checkable facts.
- Prefer precision on DATES and NUMBERS.

Return ONLY JSON between the markers, nothing else:
BEGIN_JSON
{"claims":[{"quote_verbatim":"...","claim":"<plain statement of the claim>","verdict":"correct|incorrect|unverifiable","correction":"...","explanation":"<1-2 sentences>","sources":["..."]}]}
END_JSON
If there are no factual claims, return {"claims":[]}.

SCRIPT:
<<<
{script}
>>>
"""

_VALID = {"correct", "incorrect", "unverifiable"}


def _normalize(raw_claims: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw_claims, list):
        return out
    for c in raw_claims:
        if not isinstance(c, dict):
            continue
        q = str(c.get("quote_verbatim") or "").strip()
        if not q:
            continue
        verdict = str(c.get("verdict") or "").strip().lower()
        if verdict not in _VALID:
            verdict = "unverifiable"
        srcs = c.get("sources") or []
        if isinstance(srcs, str):
            srcs = [srcs]
        srcs = [str(s).strip() for s in srcs if str(s).strip()][:3]
        out.append({
            "quote_verbatim": q,
            "claim": str(c.get("claim") or "").strip(),
            "verdict": verdict,
            "correction": str(c.get("correction") or "").strip(),
            "explanation": str(c.get("explanation") or "").strip(),
            "sources": srcs,
        })
    return out


def _build_search_tool():
    """Best-effort Google Search grounding tool across Vertex SDK versions."""
    from vertexai.generative_models import Tool
    try:
        from vertexai.generative_models import grounding
    except Exception:
        return None
    builders = [
        lambda: Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval()),
        lambda: Tool.from_google_search_retrieval(grounding.GoogleSearch()),
    ]
    for make in builders:
        try:
            return make()
        except Exception:
            continue
    return None


def _grounded_text(prompt: str) -> str:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    vertexai.init(project=_PROJECT, location=_LOCATION)
    tool = _build_search_tool()
    if tool is None:
        raise RuntimeError("Google Search grounding tool unavailable")
    model = GenerativeModel(_MODEL)
    resp = model.generate_content(
        prompt,
        tools=[tool],
        generation_config={"temperature": 0.0},
    )
    return getattr(resp, "text", "") or ""


def _plain_text(prompt: str) -> str:
    from langchain_google_vertexai import ChatVertexAI
    llm = ChatVertexAI(model=_MODEL, temperature=0.0, project=_PROJECT, location=_LOCATION)
    r = llm.invoke(prompt)
    return getattr(r, "content", "") or ""


def run_fact_check(script_text: str) -> Dict[str, Any]:
    """
    Returns {"web_grounded": bool, "claims": [ ... ]}.
    claims: {quote_verbatim, claim, verdict, correction, explanation, sources}
    """
    prompt = _PROMPT.replace("{script}", script_text or "")
    web_grounded = True
    text = ""
    try:
        text = _grounded_text(prompt)
    except Exception:
        web_grounded = False
        try:
            text = _plain_text(prompt)
        except Exception as e:
            return {"web_grounded": False, "error": str(e), "claims": []}

    data = extract_review_json(text)
    claims = _normalize((data or {}).get("claims") if isinstance(data, dict) else [])
    return {"web_grounded": web_grounded, "claims": claims}
