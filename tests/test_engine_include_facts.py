import json
import review_engine_multi as eng


class _Resp:
    def __init__(self, content): self.content = content


def _specialist_json(pid, score):
    return ("BEGIN_JSON\n" + json.dumps({
        "parameter_id": pid, "score": score, "explanation_bullets": ["ok"],
        "weakness": "Not present", "suggestions": [], "areas_of_improvement": [], "summary": "ok",
    }) + "\nEND_JSON")


def test_include_facts_false_runs_only_four_writing_categories(monkeypatch):
    seq = [_specialist_json(p, 8) for p in ("grammar", "spelling", "punctuation", "tense", "hooks")]

    class _LLM:
        def invoke(self, prompt): return _Resp(seq.pop(0))

    class _Agg:
        overall_rating = 7; strengths = ["a"]; weaknesses = ["b"]; suggestions = ["c"]
        summary = "ok"; corrected_text = "fixed"

    class _StructLLM:
        def invoke(self, prompt): return _Agg()

    class _AggLLM:
        def with_structured_output(self, schema): return _StructLLM()

    calls = {"n": 0}
    def make_llm(t):
        calls["n"] += 1
        return _LLM() if calls["n"] == 1 else _AggLLM()

    monkeypatch.setattr(eng, "_make_llm", make_llm)
    monkeypatch.setattr(eng, "_require_vertex_config", lambda: None)
    # grounded_generate must NOT be called when include_facts=False
    def _boom(*a, **k): raise AssertionError("Facts specialist should not run")
    monkeypatch.setattr(eng, "grounded_generate", _boom)
    monkeypatch.setattr(eng, "_load_prompt", lambda prefix, n: ("{evidence_json} {script}" if n == 7 else "{script}"))

    out = eng.run_review_multi("text", prompts_dir="x", temperature=0.0, include_facts=False)
    data = json.loads(out.split("BEGIN_JSON")[1].split("END_JSON")[0])
    assert set(data["scores"].keys()) == {"Grammar", "Spelling", "Punctuation", "Tense/Narrative", "Hooks"}
    assert "Facts" not in data["per_parameter"]
