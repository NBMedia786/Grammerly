import os, sys, json, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from fastapi.testclient import TestClient


def _load_app(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORY_DIR", str(tmp_path))
    monkeypatch.setenv("HISTORY_QUOTA_GB", "50")
    import main
    importlib.reload(main)
    # stub the heavy pipeline
    review = ("BEGIN_JSON\n" + json.dumps({
        "scores": {"Tense/Narrative": 8, "Hooks": 7, "Grammar": 8, "Spelling": 9, "Punctuation": 7},
        "per_parameter": {"Grammar": {"areas_of_improvement": [
            {"quote_verbatim": "They was late", "issue": "x", "fix": "They were late", "why_this_helps": "y"}]}},
        "overall_rating": 8, "strengths": ["s"], "weaknesses": ["w"], "suggestions": ["g"],
        "summary": "fine", "corrected_text": "They were late",
    }) + "\nEND_JSON")
    monkeypatch.setattr(main, "run_review_multi", lambda **k: review)
    monkeypatch.setattr(main, "run_fact_check",
                        lambda text: {"web_grounded": True, "claims": []})
    return main


def test_analyze_text_returns_writing_contract(monkeypatch, tmp_path):
    main = _load_app(monkeypatch, tmp_path)
    c = TestClient(main.app)
    r = c.post("/api/analyze-text", json={"text": "They was late to the meeting. " * 3})
    assert r.status_code == 200
    j = r.json()
    assert set(j["param_order"]) == {"Tense/Narrative", "Hooks", "Grammar", "Spelling", "Punctuation"}
    assert "viral_quotient" not in j and "drop_off_risks" not in j
    assert j["summary"] == "fine"
    assert j["saved"] is True
    assert any(sp["param"] == "Grammar" for sp in j["spans"])


def test_history_roundtrip_via_api(monkeypatch, tmp_path):
    main = _load_app(monkeypatch, tmp_path)
    c = TestClient(main.app)
    c.post("/api/analyze-text", json={"text": "They was late to the meeting. " * 3})
    lst = c.get("/api/history").json()
    assert len(lst) == 1
    rid = lst[0]["id"]
    assert c.get(f"/api/history/{rid}").json()["summary"] == "fine"
    st = c.get("/api/storage").json()
    assert st["quota_bytes"] == 50 * 1024**3 and st["count"] == 1
    d = c.delete(f"/api/history/{rid}").json()
    assert d["deleted"] is True
    assert c.get("/api/history").json() == []
