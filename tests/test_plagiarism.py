import plagiarism


def test_seam_exists():
    assert hasattr(plagiarism, "run_plagiarism_check")


def test_parses_matches_and_uses_grounding_sources(monkeypatch):
    payload = ('BEGIN_JSON\n{"matches":[{"quote_verbatim":"the war ended in 1945",'
               '"sources":["https://model-text-url/a"],"note":"appears verbatim"}]}\nEND_JSON')
    srcs = [{"title": "apnews.com", "uri": "https://vertexaisearch.cloud.google.com/redirect/z"}]
    monkeypatch.setattr(plagiarism, "_grounded_src", lambda prompt: (payload, srcs))
    out = plagiarism.run_plagiarism_check("the war ended in 1945 and more text here to pass length")
    assert out["web_grounded"] is True
    assert out["count"] == 1
    assert out["sources"] == srcs                 # real grounding sources surfaced
    m = out["matches"][0]
    assert m["quote_verbatim"] == "the war ended in 1945"
    assert m["sources"] == []                     # unreliable per-match model URLs dropped


def test_empty_matches(monkeypatch):
    monkeypatch.setattr(plagiarism, "_grounded_src",
                        lambda prompt: ('BEGIN_JSON\n{"matches":[]}\nEND_JSON', []))
    out = plagiarism.run_plagiarism_check("some original text long enough to check here")
    assert out["count"] == 0 and out["matches"] == [] and out["sources"] == []
