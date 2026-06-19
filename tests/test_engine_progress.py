import json
import review_engine_multi as eng


class _Resp:
    def __init__(self, c): self.content = c


def _spec(pid):
    return ("BEGIN_JSON\n" + json.dumps({
        "parameter_id": pid, "score": 8, "explanation_bullets": ["x"],
        "weakness": "Not present", "suggestions": [], "areas_of_improvement": [], "summary": "x",
    }) + "\nEND_JSON")


def test_on_progress_fires_each_stage(monkeypatch):
    seq = [_spec(p) for p in ("g", "s", "p", "t", "h")]

    class _LLM:
        def invoke(self, prompt): return _Resp(seq.pop(0))

    class _Agg:
        overall_rating = 7; strengths = []; weaknesses = []; suggestions = []
        summary = "x"; corrected_text = "x"

    class _AggLLM:
        def with_structured_output(self, schema):
            class _S:
                def invoke(self, p): return _Agg()
            return _S()

    calls = {"n": 0}
    def make_llm(t):
        calls["n"] += 1
        return _LLM() if calls["n"] == 1 else _AggLLM()
    monkeypatch.setattr(eng, "_make_llm", make_llm)
    monkeypatch.setattr(eng, "_require_vertex_config", lambda: None)
    monkeypatch.setattr(eng, "_load_prompt", lambda prefix, n: ("{evidence_json} {script}" if n == 7 else "{script}"))

    stages = []
    eng.run_review_multi("text", prompts_dir="x", temperature=0.0,
                         include_facts=False, on_progress=lambda s: stages.append(s))
    assert stages == ["Grammar", "Spelling", "Punctuation", "Tense/Narrative", "Hooks", "Overall"]
