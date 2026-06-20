"""Copyleaks AI-detection client: parsing, banding, availability, and fallback wiring.
No network — the live API call is exercised only when real credentials are present."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import copyleaks_client as cc
import ai_detect


def test_band_thresholds():
    assert cc._band(0) == "low"
    assert cc._band(33) == "low"
    assert cc._band(34) == "medium"
    assert cc._band(66) == "medium"
    assert cc._band(67) == "high"
    assert cc._band(100) == "high"


def test_parse_fraction_to_likelihood():
    assert cc._parse_ai_response({"summary": {"ai": 1.0, "human": 0.0}})["likelihood"] == 100
    assert cc._parse_ai_response({"summary": {"ai": 0.0}})["likelihood"] == 0
    mid = cc._parse_ai_response({"summary": {"ai": 0.5}})
    assert mid["likelihood"] == 50 and mid["band"] == "medium"


def test_parse_sets_source_and_band():
    out = cc._parse_ai_response({"summary": {"ai": 0.95}})
    assert out["source"] == "copyleaks"
    assert out["band"] == "high"
    assert "Copyleaks" in out["reasoning"]


def test_parse_aggregated_score_fallback_on_0_100_scale():
    # alternate shape: a 0..100 score rather than a 0..1 fraction
    out = cc._parse_ai_response({"score": {"aggregatedScore": 80}})
    assert out["likelihood"] == 80 and out["band"] == "high"


def test_parse_missing_ai_raises():
    with pytest.raises(RuntimeError):
        cc._parse_ai_response({"summary": {"human": 1.0}})


def test_available_requires_both_creds(monkeypatch):
    monkeypatch.delenv("COPYLEAKS_EMAIL", raising=False)
    monkeypatch.delenv("COPYLEAKS_API_KEY", raising=False)
    assert cc.available() is False
    monkeypatch.setenv("COPYLEAKS_EMAIL", "a@b.com")
    assert cc.available() is False  # key still missing
    monkeypatch.setenv("COPYLEAKS_API_KEY", "secret")
    assert cc.available() is True


def test_run_ai_detection_falls_back_to_gemini(monkeypatch):
    monkeypatch.setattr(cc, "available", lambda: False)
    monkeypatch.setattr(ai_detect, "_gemini_ai_detection",
                        lambda t: {"likelihood": 12, "band": "low", "reasoning": "g", "source": "gemini"})
    out = ai_detect.run_ai_detection("some text to check that is long enough")
    assert out["source"] == "gemini" and out["likelihood"] == 12


def test_run_ai_detection_uses_copyleaks_when_available(monkeypatch):
    monkeypatch.setattr(cc, "available", lambda: True)
    monkeypatch.setattr(cc, "ai_detection",
                        lambda t: {"likelihood": 91, "band": "high", "reasoning": "c", "source": "copyleaks"})
    out = ai_detect.run_ai_detection("some text to check that is long enough")
    assert out["source"] == "copyleaks" and out["likelihood"] == 91


def test_run_ai_detection_copyleaks_error_falls_back(monkeypatch):
    monkeypatch.setattr(cc, "available", lambda: True)
    def boom(_):
        raise RuntimeError("api down")
    monkeypatch.setattr(cc, "ai_detection", boom)
    monkeypatch.setattr(ai_detect, "_gemini_ai_detection",
                        lambda t: {"likelihood": 5, "band": "low", "reasoning": "g", "source": "gemini"})
    out = ai_detect.run_ai_detection("text")
    assert out["source"] == "gemini"


# --- plagiarism (async) ---

def test_score_to_percent_handles_fraction_and_percent():
    assert cc._score_to_percent(0.23) == 23      # 0-1 fraction
    assert cc._score_to_percent(23) == 23        # already 0-100
    assert cc._score_to_percent(1.0) == 100      # full match as fraction
    assert cc._score_to_percent(0) == 0
    assert cc._score_to_percent(None) is None
    assert cc._score_to_percent("x") is None


def test_plagiarism_available_requires_base_url(monkeypatch):
    monkeypatch.setenv("COPYLEAKS_EMAIL", "a@b.com")
    monkeypatch.setenv("COPYLEAKS_API_KEY", "k")
    monkeypatch.delenv("COPYLEAKS_PUBLIC_BASE_URL", raising=False)
    assert cc.plagiarism_available() is False
    monkeypatch.setenv("COPYLEAKS_PUBLIC_BASE_URL", "https://x.example.com/")
    assert cc.plagiarism_available() is True
    assert cc._public_base() == "https://x.example.com"  # trailing slash stripped


def test_parse_completion_webhook_extracts_score_and_sources():
    payload = {
        "scannedDocument": {"totalWords": 480},
        "results": {
            "score": {"aggregatedScore": 23, "identicalWords": 90,
                      "minorChangedWords": 12, "relatedMeaningWords": 8},
            "internet": [
                {"url": "https://en.wikipedia.org/wiki/Foo", "title": "Foo", "matchedWords": 70},
                {"title": "NoURL", "matchedWords": 20, "metadata": {"finalUrl": "https://news.ex/x"}},
            ],
            "database": [{"title": "Prev", "matchedWords": 5, "scanId": "y"}],
        },
    }
    r = cc.parse_completion_webhook(payload)
    assert r["status"] == "completed" and r["percent"] == 23
    assert r["totalWords"] == 480 and r["count"] == 3
    # sorted by matchedWords desc; url falls back to metadata.finalUrl; database has no url
    assert [s["matchedWords"] for s in r["sources"]] == [70, 20, 5]
    assert r["sources"][0]["url"] == "https://en.wikipedia.org/wiki/Foo"
    assert r["sources"][1]["url"] == "https://news.ex/x"
    assert r["sources"][2]["url"] == ""


def test_parse_completion_webhook_empty():
    r = cc.parse_completion_webhook({})
    assert r["status"] == "completed" and r["percent"] is None and r["count"] == 0


def test_capability_tokens_are_deterministic_distinct_and_scoped(monkeypatch):
    monkeypatch.setenv("COPYLEAKS_API_KEY", "secret-key")
    monkeypatch.delenv("COPYLEAKS_WEBHOOK_SECRET", raising=False)
    w = cc.webhook_token("abc")
    r = cc.result_token("abc")
    assert len(w) == 32 and len(r) == 32
    assert w != r                          # different label -> different token
    assert cc.webhook_token("abc") == w    # deterministic
    assert cc.webhook_token("xyz") != w    # per-scan-id
    assert cc.result_token("xyz") != r


def test_source_url_rejects_dangerous_schemes():
    assert cc._source_url({"url": "https://ok.com/x"}) == "https://ok.com/x"
    assert cc._source_url({"url": "http://ok.com/x"}) == "http://ok.com/x"
    assert cc._source_url({"url": "javascript:alert(1)"}) == ""
    assert cc._source_url({"url": "data:text/html,<script>"}) == ""
    assert cc._source_url({"metadata": {"finalUrl": "https://m.com/y"}}) == "https://m.com/y"
    assert cc._source_url({"metadata": {"finalUrl": "ftp://m.com/y"}}) == ""
