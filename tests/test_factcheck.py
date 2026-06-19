import factcheck


def test_seams_exist():
    assert hasattr(factcheck, "_grounded_with_sources")
    assert hasattr(factcheck, "run_fact_check")


def test_run_fact_check_uses_grounding_sources(monkeypatch):
    payload = ('BEGIN_JSON\n{"claims":[{"quote_verbatim":"ended in 1946",'
               '"claim":"war ended 1946","verdict":"incorrect","correction":"ended in 1945",'
               '"explanation":"It was 1945.","sources":["https://model-text-url/x"]}]}\nEND_JSON')
    srcs = [{"title": "wikipedia.org", "uri": "https://vertexaisearch.cloud.google.com/redirect/abc"}]
    monkeypatch.setattr(factcheck, "_grounded_with_sources", lambda prompt: (payload, srcs))
    out = factcheck.run_fact_check("the war ended in 1946")
    assert out["web_grounded"] is True
    assert out["sources"] == srcs               # real grounding sources surfaced
    c = out["claims"][0]
    assert c["verdict"] == "incorrect" and c["correction"] == "ended in 1945"
    assert c["sources"] == []                   # unreliable per-claim model URLs dropped


def test_run_fact_check_error_path(monkeypatch):
    def _boom(prompt):
        raise RuntimeError("no grounding")
    monkeypatch.setattr(factcheck, "_grounded_with_sources", _boom)
    out = factcheck.run_fact_check("hello")
    assert out["web_grounded"] is False
    assert out["claims"] == [] and out["sources"] == []
