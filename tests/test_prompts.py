import os, re

PROMPTS = "prompts"

def _content(n):
    with open(os.path.join(PROMPTS, f"{n}.yaml"), encoding="utf-8") as f:
        return f.read()

def test_specialist_prompts_have_script_placeholder():
    for n in (1, 2, 3, 4, 5):
        assert "{script}" in _content(n), f"prompt {n} missing {{script}}"

def test_aggregator_has_placeholders():
    c = _content(6)
    assert "{evidence_json}" in c and "{script}" in c

def test_preamble_exists():
    assert os.path.exists(os.path.join(PROMPTS, "7.yaml"))

def test_old_viral_prompts_removed():
    assert not os.path.exists(os.path.join(PROMPTS, "8.yaml"))
    assert not os.path.exists(os.path.join(PROMPTS, "9.yaml"))
