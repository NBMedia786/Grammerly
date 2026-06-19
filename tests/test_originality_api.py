import os, sys, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from fastapi.testclient import TestClient


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORY_DIR", str(tmp_path))
    import main
    importlib.reload(main)
    monkeypatch.setattr(main, "run_ai_detection",
                        lambda text: {"likelihood": 40, "band": "medium", "reasoning": "ok"})
    monkeypatch.setattr(main, "run_plagiarism_check",
                        lambda text: {"web_grounded": True, "count": 1,
                                      "sources": [{"title": "example.com", "uri": "https://example.com/x"}],
                                      "matches": [{"quote_verbatim": "They was late to the meeting",
                                                   "sources": [], "note": "verbatim"}]})
    return main


def test_originality_shape(monkeypatch, tmp_path):
    main = _app(monkeypatch, tmp_path)
    c = TestClient(main.app)
    r = c.post("/api/originality", json={"text": "They was late to the meeting. " * 3})
    assert r.status_code == 200
    j = r.json()
    assert j["ai_detection"]["likelihood"] == 40 and j["ai_detection"]["band"] == "medium"
    assert "disclaimer" in j["ai_detection"]
    assert j["plagiarism"]["count"] == 1
    assert any(sp["param"] == "Plagiarism" for sp in j["spans"])
    aid = j["spans"][0]["aid"]
    assert j["aoi"][aid]["kind"] == "plagiarism"
    # card now carries the real resolved grounding sources (objects), capped
    assert j["aoi"][aid]["sources"] == [{"title": "example.com", "uri": "https://example.com/x"}]


def test_originality_short_text(monkeypatch, tmp_path):
    main = _app(monkeypatch, tmp_path)
    c = TestClient(main.app)
    assert c.post("/api/originality", json={"text": "too short"}).status_code == 422
