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
