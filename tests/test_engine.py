import json
import review_engine_multi as eng


class _Resp:
    def __init__(self, content): self.content = content


def _specialist_json(pid, score):
    return (
        "BEGIN_JSON\n"
        + json.dumps({
            "parameter_id": pid, "score": score,
            "explanation_bullets": ["ok"], "weakness": "Not present",
            "suggestions": [], "areas_of_improvement": [], "summary": "ok",
        })
        + "\nEND_JSON"
    )


def test_run_review_multi_builds_five_category_payload(monkeypatch):
    # 6 writing specialists go through the langchain llm (incl. Concision)
    seq = [_specialist_json(p, 8)
           for p in ("grammar", "spelling", "punctuation", "tense", "hooks", "concision")]

    class _LLM:
        def invoke(self, prompt): return _Resp(seq.pop(0))

    monkeypatch.setattr(eng, "_make_llm", lambda t: _LLM())
    # Facts specialist goes through grounded path
    monkeypatch.setattr(eng, "grounded_generate",
                        lambda prompt, temperature=0.0: _specialist_json("facts", 9))
    # prompt loading -> trivial templates with required placeholders
    def fake_load(prefix, n):
        if n == 7: return "{evidence_json} {script}"
        return "{script}"
    monkeypatch.setattr(eng, "_load_prompt", fake_load)
    monkeypatch.setattr(eng, "_require_vertex_config", lambda: None)

    # Aggregator structured output
    class _Agg:
        overall_rating = 7
        strengths = ["clear"]; weaknesses = ["typos"]; suggestions = ["proofread"]
        summary = "Solid draft."
        corrected_text = "Corrected body."

    class _StructLLM:
        def invoke(self, prompt): return _Agg()

    class _AggLLM:
        def with_structured_output(self, schema): return _StructLLM()

    # second _make_llm call (aggregator) -> object with with_structured_output
    calls = {"n": 0}
    def make_llm(t):
        calls["n"] += 1
        return _LLM() if calls["n"] == 1 else _AggLLM()
    monkeypatch.setattr(eng, "_make_llm", make_llm)

    out = eng.run_review_multi("Some text.", prompts_dir="x", temperature=0.0)
    data = json.loads(out.split("BEGIN_JSON")[1].split("END_JSON")[0])

    assert set(data["scores"].keys()) == {
        "Grammar", "Spelling", "Punctuation", "Tense/Narrative", "Hooks", "Concision", "Facts"}
    assert data["scores"]["Facts"] == 9
    assert data["overall_rating"] == 7
    assert data["corrected_text"] == "Corrected body."
    assert "viral_quotient" not in data
