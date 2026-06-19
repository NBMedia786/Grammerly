import os, sys, json, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from fastapi.testclient import TestClient


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORY_DIR", str(tmp_path))
    import main
    importlib.reload(main)
    review = ("BEGIN_JSON\n" + json.dumps({
        "scores": {"Grammar": 8, "Spelling": 9, "Punctuation": 7, "Tense/Narrative": 8, "Hooks": 7},
        "per_parameter": {}, "overall_rating": 8, "strengths": [], "weaknesses": [],
        "suggestions": [], "summary": "ok", "corrected_text": "ok",
    }) + "\nEND_JSON")
    # mocked engine that still fires progress so the stream shows it
    def fake_engine(script_text, prompts_dir, temperature, include_facts, on_progress=None):
        if on_progress:
            for s in ("Grammar", "Spelling", "Punctuation", "Tense/Narrative", "Hooks", "Overall"):
                on_progress(s)
        return review
    monkeypatch.setattr(main, "run_review_multi", fake_engine)
    monkeypatch.setattr(main, "run_fact_check", lambda text: {"web_grounded": True, "claims": []})
    return main


def test_stream_emits_stages_progress_result(monkeypatch, tmp_path):
    main = _app(monkeypatch, tmp_path)
    c = TestClient(main.app)
    r = c.post("/api/analyze-stream", json={"text": "They was late to the meeting. " * 3})
    assert r.status_code == 200
    body = r.text
    assert "event: stages" in body
    assert "event: progress" in body
    assert "event: result" in body
    # the result frame carries the writing param_order
    result_line = [l for l in body.splitlines() if l.startswith("data:") and "param_order" in l][0]
    data = json.loads(result_line[len("data:"):].strip())
    assert set(data["param_order"]) == {"Tense/Narrative", "Hooks", "Grammar", "Spelling", "Punctuation"}


def test_stream_short_text(monkeypatch, tmp_path):
    main = _app(monkeypatch, tmp_path)
    c = TestClient(main.app)
    assert c.post("/api/analyze-stream", json={"text": "short"}).status_code == 422
