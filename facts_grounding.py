"""Google-Search-grounded Gemini call on Vertex AI, with an ungrounded fallback.

Isolated here so the rest of the engine never imports Vertex grounding internals.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def _model_name() -> str:
    return os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"


def _project() -> str | None:
    return os.getenv("GOOGLE_CLOUD_PROJECT") or None


def _location() -> str:
    return os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"


def _genai_client():
    """Vertex-backed google-genai client (recommended SDK for Gemini 2.x grounding)."""
    from google import genai
    return genai.Client(vertexai=True, project=_project(), location=_location())


def _grounded_call(prompt: str, temperature: float) -> str:
    """Gemini on Vertex with the Google Search tool (the `google_search` field that
    Gemini 2.x requires — the older `google_search_retrieval` tool is rejected by 2.5)."""
    from google.genai import types

    client = _genai_client()
    resp = client.models.generate_content(
        model=_model_name(),
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=temperature,
        ),
    )
    return getattr(resp, "text", "") or ""


def _ungrounded_call(prompt: str, temperature: float) -> str:
    """Plain Gemini on Vertex via google-genai (no search tool); used only if the
    grounded call fails, so Facts never blocks the run."""
    from google.genai import types

    client = _genai_client()
    resp = client.models.generate_content(
        model=_model_name(),
        contents=prompt,
        config=types.GenerateContentConfig(temperature=temperature),
    )
    return getattr(resp, "text", "") or ""


def grounded_generate(prompt: str, temperature: float = 0.0) -> str:
    """Try grounded; on any failure, fall back to ungrounded so Facts never blocks the run."""
    try:
        return _grounded_call(prompt, temperature)
    except Exception:
        return _ungrounded_call(prompt, temperature)


def ungrounded_generate(prompt: str, temperature: float = 0.0) -> str:
    """Plain (no search) Gemini call — used by AI-content detection."""
    return _ungrounded_call(prompt, temperature)


def resolve_url(uri: str, timeout: float = 5.0) -> str:
    """Follow a grounding-redirect URL to its real final destination (e.g.
    en.wikipedia.org/...). Redirect links expire; the resolved URL is permanent so
    saved-history links keep working. Returns the original uri on any failure."""
    if not uri or "vertexaisearch" not in uri:
        return uri or ""
    try:
        import requests
        r = requests.get(uri, allow_redirects=True, timeout=timeout, stream=True)
        final = r.url or uri
        r.close()
        return final
    except Exception:
        return uri


def _extract_grounding_sources(resp, resolve: bool = True):
    """Pull real citation sources from a grounded response's metadata:
    [{title: '<domain>', uri: '<final url>'}]. The metadata URIs are full redirect links;
    we resolve them to permanent destinations so they don't 404 later."""
    out, seen = [], set()
    try:
        for cand in (getattr(resp, "candidates", None) or []):
            gm = getattr(cand, "grounding_metadata", None)
            for ch in (getattr(gm, "grounding_chunks", None) or []):
                web = getattr(ch, "web", None)
                if not web:
                    continue
                uri = getattr(web, "uri", None)
                title = (getattr(web, "title", None) or "").strip()
                if uri and uri not in seen:
                    seen.add(uri)
                    out.append({"title": title or "source", "uri": uri})
    except Exception:
        pass
    out = out[:8]
    if resolve and out:
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=8) as ex:
                finals = list(ex.map(lambda s: resolve_url(s["uri"]), out))
            for s, f in zip(out, finals):
                s["uri"] = f
        except Exception:
            pass
    return out


def grounded_generate_with_sources(prompt: str, temperature: float = 0.0):
    """Grounded Gemini call returning (text, [{title, uri}]) where sources come from the
    grounding metadata (real domains + full working URLs). Retries once on a transient
    error, then falls back to (ungrounded_text, []) so a hiccup never drops the check."""
    import time
    for attempt in range(2):
        try:
            from google.genai import types
            client = _genai_client()
            resp = client.models.generate_content(
                model=_model_name(),
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=temperature,
                ),
            )
            return (getattr(resp, "text", "") or ""), _extract_grounding_sources(resp)
        except Exception:
            if attempt == 0:
                time.sleep(0.8)
                continue
    # both grounded attempts failed — try plain, else give an empty-but-valid result
    try:
        return _ungrounded_call(prompt, temperature), []
    except Exception:
        return "", []
