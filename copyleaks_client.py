"""Copyleaks-backed AI-content detection (accurate, real detector API).

Only the SYNCHRONOUS AI Detector (v2 `writer-detector`) is wired here — it is a plain
request/response call. Copyleaks' plagiarism scan is webhook/async (needs a public callback
URL) and is intentionally NOT wired; plagiarism stays on the Gemini-grounded check.

Auth: log in with email + API key to get a short-lived bearer token (cached ~40h).
Set these in .env (gitignored):
    COPYLEAKS_EMAIL=you@example.com
    COPYLEAKS_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    COPYLEAKS_SANDBOX=1   # optional: test wiring without spending credits

This module RAISES on any failure; the caller (ai_detect.run_ai_detection) catches it and
falls back to the free Gemini heuristic, so a missing key or API hiccup never breaks the app.
"""
from __future__ import annotations

import base64
import os
import time
import uuid
from typing import Any, Dict

import requests
from dotenv import load_dotenv

load_dotenv()

_LOGIN_URL = "https://id.copyleaks.com/v3/account/login/api"
_AI_URL = "https://api.copyleaks.com/v2/writer-detector/{scan_id}/check"

# module-level token cache: {"value": <jwt>, "exp": <unix seconds>}
_token: Dict[str, Any] = {"value": None, "exp": 0.0}


def _email() -> str:
    return (os.getenv("COPYLEAKS_EMAIL") or "").strip()


def _key() -> str:
    return (os.getenv("COPYLEAKS_API_KEY") or "").strip()


def _sandbox() -> bool:
    return (os.getenv("COPYLEAKS_SANDBOX") or "").strip().lower() in ("1", "true", "yes", "on")


def available() -> bool:
    """True only when both Copyleaks credentials are configured."""
    return bool(_email() and _key())


def _band(likelihood: int) -> str:
    if likelihood > 66:
        return "high"
    if likelihood >= 34:
        return "medium"
    return "low"


def _login(timeout: float = 15.0) -> str:
    """Return a valid bearer token, reusing the cached one until shortly before it expires."""
    now = time.time()
    if _token["value"] and float(_token["exp"]) - 60 > now:
        return str(_token["value"])
    r = requests.post(_LOGIN_URL, json={"email": _email(), "key": _key()}, timeout=timeout)
    r.raise_for_status()
    tok = ((r.json() or {}) if r.content else {}).get("access_token") or ""
    if not tok:
        raise RuntimeError("Copyleaks login returned no access_token")
    _token["value"] = tok
    _token["exp"] = now + 40 * 3600  # tokens last ~48h; refresh well before
    return tok


def _parse_ai_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Copyleaks AI-Detector response to {likelihood, band, reasoning, source}.

    The response carries `summary.ai` — the fraction (0..1) of the document classified as
    AI-written. We surface that as a 0-100 likelihood.
    """
    summary = (data or {}).get("summary") or {}
    ai = summary.get("ai")
    if ai is None:
        # tolerate alternate shapes rather than crash the whole check
        ai = ((data or {}).get("score") or {}).get("aggregatedScore")
    try:
        frac = float(ai)
    except (TypeError, ValueError):
        raise RuntimeError("Copyleaks AI response missing 'summary.ai'")
    likelihood = int(round(frac * 100)) if frac <= 1.0 else int(round(frac))
    likelihood = max(0, min(100, likelihood))
    return {
        "likelihood": likelihood,
        "band": _band(likelihood),
        "reasoning": f"Copyleaks AI Detector: {likelihood}% of the text classified as AI-written.",
        "source": "copyleaks",
    }


def ai_detection(text: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Run Copyleaks AI detection on `text`. Raises on any failure (caller falls back)."""
    token = _login()
    url = _AI_URL.format(scan_id=uuid.uuid4().hex)
    body = {"text": text or "", "sandbox": _sandbox()}
    r = requests.post(
        url,
        json=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()
    return _parse_ai_response((r.json() or {}) if r.content else {})


# --- Plagiarism (async v3 scans, webhook-based) -----------------------------------
# Unlike the synchronous AI Detector, the plagiarism scan is push-based: submit the text,
# and Copyleaks POSTs the completed results to a PUBLIC webhook. So this needs
# COPYLEAKS_PUBLIC_BASE_URL (the reachable HTTPS base of our backend) on top of the creds.

_SUBMIT_URL = "https://api.copyleaks.com/v3/scans/submit/file/{scan_id}"


def _public_base() -> str:
    return (os.getenv("COPYLEAKS_PUBLIC_BASE_URL") or "").strip().rstrip("/")


def plagiarism_available() -> bool:
    """True only when creds AND a public base URL (for the completion webhook) are set."""
    return bool(_email() and _key() and _public_base())


def submit_plagiarism_scan(text: str, scan_id: str, timeout: float = 30.0) -> None:
    """Submit plain text for a plagiarism scan. Copyleaks will POST the result to
    {COPYLEAKS_PUBLIC_BASE_URL}/api/copyleaks/webhook/{scan_id}/{STATUS}. Raises on failure;
    the caller falls back to the free Gemini check."""
    token = _login()
    b64 = base64.b64encode((text or "").encode("utf-8")).decode("ascii")
    webhook = f"{_public_base()}/api/copyleaks/webhook/{scan_id}/{{STATUS}}"
    body = {
        "base64": b64,
        "filename": "submission.txt",
        "properties": {
            "webhooks": {"status": webhook},
            "sandbox": _sandbox(),
            "developerPayload": str(scan_id)[:512],
        },
    }
    r = requests.put(
        _SUBMIT_URL.format(scan_id=scan_id),
        json=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()


def _score_to_percent(agg) -> Any:
    """aggregatedScore can arrive as a 0-1 fraction or a 0-100 percent; normalize to 0-100."""
    try:
        v = float(agg)
    except (TypeError, ValueError):
        return None
    pct = v * 100 if v <= 1.0 else v
    return max(0, min(100, round(pct)))


def _source_url(item: Dict[str, Any]) -> str:
    url = (item.get("url") or "").strip()
    if url:
        return url
    meta = item.get("metadata") or {}
    return (meta.get("finalUrl") or meta.get("canonicalUrl") or "").strip()


def parse_completion_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Copyleaks scan-completed webhook body to a compact plagiarism result:
    {percent, word buckets, totalWords, sources:[{url,title,matchedWords,kind}]}."""
    results = (payload or {}).get("results") or {}
    score = results.get("score") or {}
    scanned = (payload or {}).get("scannedDocument") or {}
    sources = []
    for kind in ("internet", "database", "batch", "repositories"):
        for s in (results.get(kind) or []):
            if not isinstance(s, dict):
                continue
            url = _source_url(s)
            sources.append({
                "url": url,
                "title": (s.get("title") or "").strip() or url or "source",
                "matchedWords": s.get("matchedWords"),
                "kind": kind,
            })
    sources.sort(key=lambda x: (x.get("matchedWords") or 0), reverse=True)
    return {
        "engine": "copyleaks",
        "status": "completed",
        "percent": _score_to_percent(score.get("aggregatedScore")),
        "identicalWords": score.get("identicalWords"),
        "minorChangedWords": score.get("minorChangedWords"),
        "relatedMeaningWords": score.get("relatedMeaningWords"),
        "totalWords": scanned.get("totalWords"),
        "sources": sources[:10],
        "count": len(sources),
    }
