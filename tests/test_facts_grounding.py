import facts_grounding


def test_module_exposes_grounded_generate():
    assert hasattr(facts_grounding, "grounded_generate")


def test_falls_back_to_ungrounded_on_grounding_error(monkeypatch):
    calls = {"grounded": 0, "ungrounded": 0}

    def fake_grounded(prompt, temperature):
        calls["grounded"] += 1
        raise RuntimeError("grounding tool unavailable")

    def fake_ungrounded(prompt, temperature, model=None):
        calls["ungrounded"] += 1
        return "FALLBACK_TEXT"

    monkeypatch.setattr(facts_grounding, "_grounded_call", fake_grounded)
    monkeypatch.setattr(facts_grounding, "_ungrounded_call", fake_ungrounded)

    out = facts_grounding.grounded_generate("check this", temperature=0.0)
    assert out == "FALLBACK_TEXT"
    assert calls["grounded"] == 1 and calls["ungrounded"] == 1
