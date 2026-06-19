"""
Tests for curly-quote normalization in parsers and prompt YAML files.

Covers:
  1. review_engine_multi._parse_json handles curly-quoted JSON correctly.
  2. utils1.extract_review_json handles curly-quoted JSON in ```json``` fences.
  3. Prompt files 1–5 contain no U+201C or U+201D characters (regression guard).
"""
import os
import json

import review_engine_multi as eng
import utils1


# ---------------------------------------------------------------------------
# Helper: build curly-quote variants of otherwise-valid JSON strings
# ---------------------------------------------------------------------------
CURLY_LEFT_DQ  = "“"   # "
CURLY_RIGHT_DQ = "”"   # "
CURLY_LEFT_SQ  = "‘"   # '
CURLY_RIGHT_SQ = "’"   # '


def _curly(s: str) -> str:
    """Replace straight ASCII double-quotes with curly equivalents."""
    # Alternate left/right so they look like a proper typographic pair.
    result = []
    open_next = True
    for ch in s:
        if ch == '"':
            result.append(CURLY_LEFT_DQ if open_next else CURLY_RIGHT_DQ)
            open_next = not open_next
        else:
            result.append(ch)
    return "".join(result)


# ---------------------------------------------------------------------------
# 1. review_engine_multi._parse_json with curly-quoted JSON
# ---------------------------------------------------------------------------

def test_parse_json_curly_between_markers():
    """_parse_json must parse a BEGIN_JSON/END_JSON block whose quotes are curly."""
    raw = '{"score": 9, "ok": "yes"}'
    curly_raw = _curly(raw)
    text = f"BEGIN_JSON\n{curly_raw}\nEND_JSON"
    result = eng._parse_json(text)
    assert result == {"score": 9, "ok": "yes"}


def test_parse_json_straight_quotes_unchanged():
    """Straight-quoted JSON must still parse (no regression)."""
    text = 'BEGIN_JSON\n{"score": 9, "ok": "yes"}\nEND_JSON'
    result = eng._parse_json(text)
    assert result == {"score": 9, "ok": "yes"}


def test_parse_json_curly_fenced():
    """_parse_json must parse a ```json``` block with curly quotes."""
    raw = '{"a": 1, "b": "hello"}'
    curly_raw = _curly(raw)
    text = f"```json\n{curly_raw}\n```"
    result = eng._parse_json(text)
    assert result == {"a": 1, "b": "hello"}


def test_parse_json_curly_trailing_comma():
    """_parse_json must handle curly quotes AND trailing commas together."""
    raw = '{"score": 7, "ok": "yes",}'
    curly_raw = _curly(raw)
    text = f"BEGIN_JSON\n{curly_raw}\nEND_JSON"
    result = eng._parse_json(text)
    assert result == {"score": 7, "ok": "yes"}


# ---------------------------------------------------------------------------
# 2. utils1.extract_review_json with curly-quoted JSON
# ---------------------------------------------------------------------------

def test_extract_review_json_curly_fenced():
    """extract_review_json must parse a ```json``` fence with curly quotes."""
    raw = '{"a": 1}'
    curly_raw = _curly(raw)
    text = f"```json\n{curly_raw}\n```"
    result = utils1.extract_review_json(text)
    assert result == {"a": 1}


def test_extract_review_json_straight_quotes_unchanged():
    """Straight-quoted JSON must still parse (no regression)."""
    text = '```json\n{"a": 1}\n```'
    result = utils1.extract_review_json(text)
    assert result == {"a": 1}


def test_extract_review_json_curly_between_markers():
    """extract_review_json must parse a BEGIN_JSON/END_JSON block with curly quotes."""
    raw = '{"score": 9, "ok": "yes"}'
    curly_raw = _curly(raw)
    text = f"BEGIN_JSON\n{curly_raw}\nEND_JSON"
    result = utils1.extract_review_json(text)
    assert result == {"score": 9, "ok": "yes"}


def test_extract_review_json_curly_trailing_comma():
    """extract_review_json must handle curly quotes AND trailing commas together."""
    raw = '{"score": 7, "note": "good",}'
    curly_raw = _curly(raw)
    text = f"```json\n{curly_raw}\n```"
    result = utils1.extract_review_json(text)
    assert result == {"score": 7, "note": "good"}


# ---------------------------------------------------------------------------
# 3. Prompt files 1–5 must contain no U+201C or U+201D characters
# ---------------------------------------------------------------------------

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


def _read_prompt(n: int) -> str:
    path = os.path.join(_PROMPTS_DIR, f"{n}.yaml")
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_prompt_1_no_curly_double_quotes():
    text = _read_prompt(1)
    assert CURLY_LEFT_DQ not in text, "prompts/1.yaml contains U+201C (“)"
    assert CURLY_RIGHT_DQ not in text, "prompts/1.yaml contains U+201D (”)"


def test_prompt_2_no_curly_double_quotes():
    text = _read_prompt(2)
    assert CURLY_LEFT_DQ not in text, "prompts/2.yaml contains U+201C (“)"
    assert CURLY_RIGHT_DQ not in text, "prompts/2.yaml contains U+201D (”)"


def test_prompt_3_no_curly_double_quotes():
    text = _read_prompt(3)
    assert CURLY_LEFT_DQ not in text, "prompts/3.yaml contains U+201C (“)"
    assert CURLY_RIGHT_DQ not in text, "prompts/3.yaml contains U+201D (”)"


def test_prompt_4_no_curly_double_quotes():
    text = _read_prompt(4)
    assert CURLY_LEFT_DQ not in text, "prompts/4.yaml contains U+201C (“)"
    assert CURLY_RIGHT_DQ not in text, "prompts/4.yaml contains U+201D (”)"


def test_prompt_5_no_curly_double_quotes():
    text = _read_prompt(5)
    assert CURLY_LEFT_DQ not in text, "prompts/5.yaml contains U+201C (“)"
    assert CURLY_RIGHT_DQ not in text, "prompts/5.yaml contains U+201D (”)"
