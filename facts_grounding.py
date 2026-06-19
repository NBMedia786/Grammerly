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


def _grounded_call(prompt: str, temperature: float) -> str:
    """Vertex Gemini with Google Search grounding. Raises if the SDK path is unavailable."""
    import vertexai
    from vertexai.generative_models import GenerativeModel, Tool, grounding, GenerationConfig

    vertexai.init(project=_project(), location=_location())
    tool = Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())
    model = GenerativeModel(_model_name())
    resp = model.generate_content(
        prompt,
        tools=[tool],
        generation_config=GenerationConfig(temperature=temperature),
    )
    return getattr(resp, "text", "") or ""


def _ungrounded_call(prompt: str, temperature: float) -> str:
    """Plain Vertex Gemini via langchain (same path as other specialists)."""
    from langchain_google_vertexai import ChatVertexAI

    llm = ChatVertexAI(
        model=_model_name(),
        temperature=temperature,
        top_p=0.0,
        top_k=1,
        project=_project(),
        location=_location(),
    )
    resp = llm.invoke(prompt)
    return getattr(resp, "content", "") or ""


def grounded_generate(prompt: str, temperature: float = 0.0) -> str:
    """Try grounded; on any failure, fall back to ungrounded so Facts never blocks the run."""
    try:
        return _grounded_call(prompt, temperature)
    except Exception:
        return _ungrounded_call(prompt, temperature)
