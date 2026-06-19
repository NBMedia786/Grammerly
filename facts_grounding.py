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


def _extract_grounding_sources(resp):
    """Pull real citation sources from a grounded response's metadata:
    [{title: '<domain>', uri: '<full redirect url>'}]. The metadata URIs are the
    full, valid links (the model truncates them when echoing into text -> 404s)."""
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
    return out[:8]


def grounded_generate_with_sources(prompt: str, temperature: float = 0.0):
    """Grounded Gemini call returning (text, [{title, uri}]) where sources come from the
    grounding metadata (real domains + full working URLs). Falls back to
    (ungrounded_text, []) if the grounded path is unavailable."""
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
        return _ungrounded_call(prompt, temperature), []
