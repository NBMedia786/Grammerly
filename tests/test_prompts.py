import os

PROMPTS = "prompts"

def _content(n):
    with open(os.path.join(PROMPTS, f"{n}.yaml"), encoding="utf-8") as f:
        return f.read()

def test_specialist_prompts_have_script_placeholder():
    for n in (1, 2, 3, 4, 5, 6):
        assert "{script}" in _content(n), f"prompt {n} missing {{script}}"

def test_aggregator_has_placeholders():
    c = _content(7)
    assert "{evidence_json}" in c and "{script}" in c

def test_preamble_exists():
    assert os.path.exists(os.path.join(PROMPTS, "8.yaml"))

def test_prompt_nine_is_concision():
    assert os.path.exists(os.path.join(PROMPTS, "9.yaml"))
    assert "concision" in _content(9).lower()

def test_no_curly_quotes_in_prompts():
    for n in (1, 2, 3, 4, 5, 6, 9):
        t = _content(n)
        assert "“" not in t and "”" not in t, f"prompt {n} has curly quotes"
