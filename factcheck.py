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
_MODEL = os.getenv("FACTS_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"

_PROMPT = """You are a rigorous fact-checker for short-video scripts.
Read the SCRIPT and extract EVERY checkable factual claim. Pay special attention to:
- dates and years, time periods, centuries ("in 1944", "during the 1980s")
- historical events and the order they happened in
- names, titles, attributions ("invented by", "the first to", "directed by")
- places and geography
- numbers, statistics, measurements and records ("largest", "oldest", "fastest")

For each claim decide one verdict. Calibrate the verdict to your CONFIDENCE:
- "correct"      -> reliable sources clearly support it.
- "incorrect"    -> reliable sources CLEARLY and CONSISTENTLY contradict it (e.g. a date, name,
                    or number that is plainly wrong by the weight of evidence). Use red
                    "incorrect" ONLY when you are confident the claim is simply wrong.
- "unverifiable" -> you cannot confirm it from reliable sources, OR sources DISAGREE with each
                    other, OR the claim is close-but-imprecise or conflates two related facts
                    (e.g. it names a REAL date but attaches it to the WRONG event, or it is off
                    by a detail). This is the amber "needs checking" bucket.

WHEN UNSURE between "incorrect" and "unverifiable", always choose "unverifiable". Reserve
"incorrect" for clear, sourced contradictions — do NOT use it for facts that are merely
contested, ambiguous, or unconfirmable.

DATES especially: if sources give differing dates, or you cannot confirm the EXACT date, or the
date is right but tied to the wrong event, mark "unverifiable" (NOT "incorrect"). Only mark a
date "incorrect" when reliable sources agree it is wrong.

STRICT RULES:
- "quote_verbatim" MUST be copied EXACTLY from the script (a real substring) so it can be highlighted.
- For "incorrect": "correction" MUST be a DROP-IN REPLACEMENT for quote_verbatim with the fact fixed,
  keeping the same wording where possible. Example: quote "the war ended in 1944" -> correction "the war ended in 1945".
- For "unverifiable": leave "correction" empty, and in "explanation" say briefly what is uncertain
  or how sources differ (e.g. "Sources date the body's discovery to June 13-14; none confirm she
  was reported missing on June 13.").
- For "correct": "correction" may be "".
- "sources" = up to 3 source URLs (or source names) you relied on. May be empty.
- Do NOT flag opinions, jokes, predictions, or obvious dramatization. Only judge concrete, checkable facts.
- Prefer precision on DATES and NUMBERS, but express uncertainty as "unverifiable", not "incorrect".

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
        # Per-claim source URLs from the model text are unreliable (truncated -> 404).
        # Real sources come from the grounding metadata at the response level instead.
        out.append({
            "quote_verbatim": q,
            "claim": str(c.get("claim") or "").strip(),
            "verdict": verdict,
            "correction": str(c.get("correction") or "").strip(),
            "explanation": str(c.get("explanation") or "").strip(),
            "sources": [],
        })
    return out


def _genai_client():
    from google import genai
    return genai.Client(vertexai=True, project=_PROJECT, location=_LOCATION)


def _grounded_text(prompt: str) -> str:
    from google.genai import types
    client = _genai_client()
    resp = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.0,
        ),
    )
    return getattr(resp, "text", "") or ""


def _plain_text(prompt: str) -> str:
    from google.genai import types
    client = _genai_client()
    resp = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return getattr(resp, "text", "") or ""


def _grounded_with_sources(prompt: str):
    """(text, [{title, uri}]) — grounded call with real citation sources from metadata."""
    from facts_grounding import grounded_generate_with_sources
    return grounded_generate_with_sources(prompt, temperature=0.0)


def run_fact_check(script_text: str) -> Dict[str, Any]:
    """
    Returns {"web_grounded": bool, "claims": [...], "sources": [{title, uri}]}.
    Sources are the web pages the grounded check consulted (real domains + working links).
    """
    prompt = _PROMPT.replace("{script}", script_text or "")
    sources = []
    try:
        text, sources = _grounded_with_sources(prompt)
    except Exception as e:
        return {"web_grounded": False, "error": str(e), "claims": [], "sources": []}

    data = extract_review_json(text)
    claims = _normalize((data or {}).get("claims") if isinstance(data, dict) else [])
    # If we got citation sources, the search grounding definitely ran.
    return {"web_grounded": bool(sources), "claims": claims, "sources": sources}
