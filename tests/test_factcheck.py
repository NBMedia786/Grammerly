import factcheck


def test_seams_exist():
    assert hasattr(factcheck, "_grounded_text")
    assert hasattr(factcheck, "_plain_text")
    assert hasattr(factcheck, "run_fact_check")


def test_run_fact_check_shape_with_grounded(monkeypatch):
    payload = ('BEGIN_JSON\n{"claims":[{"quote_verbatim":"ended in 1946",'
               '"claim":"war ended 1946","verdict":"incorrect","correction":"ended in 1945",'
               '"explanation":"It was 1945.","sources":["https://example.com/wwii"]}]}\nEND_JSON')
    monkeypatch.setattr(factcheck, "_grounded_text", lambda prompt: payload)
    out = factcheck.run_fact_check("the war ended in 1946")
    assert out["web_grounded"] is True
    assert len(out["claims"]) == 1
    c = out["claims"][0]
    assert c["verdict"] == "incorrect" and c["correction"] == "ended in 1945"
    assert c["sources"] == ["https://example.com/wwii"]


def test_run_fact_check_falls_back_to_plain(monkeypatch):
    def _boom(prompt): raise RuntimeError("no grounding")
    monkeypatch.setattr(factcheck, "_grounded_text", _boom)
    monkeypatch.setattr(factcheck, "_plain_text",
                        lambda prompt: 'BEGIN_JSON\n{"claims":[]}\nEND_JSON')
    out = factcheck.run_fact_check("hello")
    assert out["web_grounded"] is False and out["claims"] == []
