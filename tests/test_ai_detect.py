import ai_detect


def test_seam_exists():
    assert hasattr(ai_detect, "run_ai_detection")


def test_parses_and_clamps(monkeypatch):
    monkeypatch.setattr(ai_detect, "_generate",
                        lambda prompt: 'BEGIN_JSON\n{"likelihood":140,"reasoning":"uniform phrasing"}\nEND_JSON')
    out = ai_detect.run_ai_detection("some text long enough to evaluate for ai content here")
    assert out["likelihood"] == 100        # clamped
    assert out["band"] == "high"           # derived
    assert "uniform" in out["reasoning"]


def test_bad_json_safe_default(monkeypatch):
    monkeypatch.setattr(ai_detect, "_generate", lambda prompt: "not json at all")
    out = ai_detect.run_ai_detection("text")
    assert out["likelihood"] == 0 and out["band"] == "low"


def test_band_thresholds(monkeypatch):
    monkeypatch.setattr(ai_detect, "_generate", lambda prompt: 'BEGIN_JSON\n{"likelihood":50}\nEND_JSON')
    assert ai_detect.run_ai_detection("x")["band"] == "medium"
