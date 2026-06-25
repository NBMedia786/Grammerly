"""ENGLISH_VARIANT toggle: the preamble's {ENGLISH_RULES} token swaps US vs British rules."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import review_engine_multi as eng


def test_preamble_carries_the_token():
    # 8.yaml must keep the placeholder so the engine can inject the variant.
    assert "{ENGLISH_RULES}" in eng._load_prompt("prompts", 8)


def test_british_variant(monkeypatch):
    monkeypatch.setenv("ENGLISH_VARIANT", "british")
    out = eng._apply_english_variant("A {ENGLISH_RULES} B")
    assert "{ENGLISH_RULES}" not in out
    assert "BRITISH (UK) ENGLISH" in out
    assert "colour (not color)" in out
    assert "AMERICAN" not in out


def test_us_variant(monkeypatch):
    monkeypatch.setenv("ENGLISH_VARIANT", "us")
    out = eng._apply_english_variant("A {ENGLISH_RULES} B")
    assert "AMERICAN (US) ENGLISH" in out
    assert "color (not colour)" in out
    assert "BRITISH" not in out


def test_default_is_british(monkeypatch):
    monkeypatch.delenv("ENGLISH_VARIANT", raising=False)
    out = eng._apply_english_variant("{ENGLISH_RULES}")
    assert "BRITISH (UK) ENGLISH" in out


def test_variant_aliases(monkeypatch):
    for v in ("us", "US", "american", "en-us"):
        monkeypatch.setenv("ENGLISH_VARIANT", v)
        assert "AMERICAN (US) ENGLISH" in eng._apply_english_variant("{ENGLISH_RULES}")
