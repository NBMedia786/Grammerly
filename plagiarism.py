"""Best-effort web-plagiarism check: find passages that appear verbatim online
via Google Search grounding. Not a true overlap %, won't catch paraphrasing."""
from __future__ import annotations

from typing import Any, Dict, List

from facts_grounding import grounded_generate
from utils1 import extract_review_json

_PROMPT = """You are a plagiarism checker with access to Google Search.
Find passages in the SCRIPT below that appear VERBATIM (or nearly verbatim) on the public web.
Only report a passage if you actually find it published online via search.

STRICT RULES:
- "quote_verbatim" MUST be copied EXACTLY from the script (a real substring), 8+ words.
- "sources" = up to 3 URLs where the passage (or near-identical text) appears. Real URLs only.
- "note" = one short phrase (e.g. "appears verbatim on news site").
- Do NOT report common phrases, names, dates, or short generic fragments.
- If nothing is found, return {"matches": []}.

Return ONLY JSON between the markers:
BEGIN_JSON
{"matches":[{"quote_verbatim":"...","sources":["..."],"note":"..."}]}
END_JSON

SCRIPT:
<<<
{script}
>>>
"""


def _grounded(prompt: str) -> str:
    return grounded_generate(prompt, temperature=0.0)


def _normalize(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for m in raw:
        if not isinstance(m, dict):
            continue
        q = str(m.get("quote_verbatim") or "").strip()
        if not q:
            continue
        srcs = m.get("sources") or []
        if isinstance(srcs, str):
            srcs = [srcs]
        srcs = [str(s).strip() for s in srcs if str(s).strip()][:3]
        out.append({"quote_verbatim": q, "sources": srcs, "note": str(m.get("note") or "").strip()})
    return out


def run_plagiarism_check(text: str) -> Dict[str, Any]:
    prompt = _PROMPT.replace("{script}", text or "")
    web_grounded = True
    try:
        raw_text = _grounded(prompt)
    except Exception:
        return {"web_grounded": False, "matches": [], "count": 0}
    data = extract_review_json(raw_text)
    matches = _normalize((data or {}).get("matches") if isinstance(data, dict) else [])
    return {"web_grounded": web_grounded, "matches": matches, "count": len(matches)}
