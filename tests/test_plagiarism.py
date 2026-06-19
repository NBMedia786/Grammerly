import plagiarism


def test_seam_exists():
    assert hasattr(plagiarism, "run_plagiarism_check")


def test_parses_matches(monkeypatch):
    payload = ('BEGIN_JSON\n{"matches":[{"quote_verbatim":"the war ended in 1945",'
               '"sources":["https://example.com/a","https://example.com/b"],'
               '"note":"appears verbatim"}]}\nEND_JSON')
    monkeypatch.setattr(plagiarism, "_grounded", lambda prompt: payload)
    out = plagiarism.run_plagiarism_check("the war ended in 1945 and more text here to pass length")
    assert out["web_grounded"] is True
    assert out["count"] == 1
    m = out["matches"][0]
    assert m["quote_verbatim"] == "the war ended in 1945"
    assert m["sources"] == ["https://example.com/a", "https://example.com/b"]


def test_empty_matches(monkeypatch):
    monkeypatch.setattr(plagiarism, "_grounded", lambda prompt: 'BEGIN_JSON\n{"matches":[]}\nEND_JSON')
    out = plagiarism.run_plagiarism_check("some original text long enough to check here")
    assert out["count"] == 0 and out["matches"] == []
