import os, sys, json, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def _fresh(monkeypatch, tmp_path, quota_gb="50"):
    monkeypatch.setenv("HISTORY_DIR", str(tmp_path))
    monkeypatch.setenv("HISTORY_QUOTA_GB", quota_gb)
    import history
    importlib.reload(history)
    return history


def test_save_list_load_delete_roundtrip(monkeypatch, tmp_path):
    h = _fresh(monkeypatch, tmp_path)
    r = h.save_review({"script_text": "hi", "overall_rating": 8}, "doc1")
    assert r["saved"] is True and r["id"]
    items = h.list_reviews()
    assert len(items) == 1 and items[0]["title"] == "doc1" and items[0]["overall_rating"] == 8
    loaded = h.load_review(r["id"])
    assert loaded["script_text"] == "hi"
    d = h.delete_review(r["id"])
    assert d["deleted"] is True
    assert h.list_reviews() == [] and h.load_review(r["id"]) is None


def test_quota_blocks_new_saves(monkeypatch, tmp_path):
    # tiny quota so the first save fills it; quota in GB, so use a fractional value
    h = _fresh(monkeypatch, tmp_path, quota_gb="0")  # 0 GB -> always full
    r = h.save_review({"script_text": "x"}, "doc")
    assert r["saved"] is False and r["reason"] == "storage_full"
    assert h.list_reviews() == []


def test_storage_usage_math(monkeypatch, tmp_path):
    h = _fresh(monkeypatch, tmp_path)
    h.save_review({"script_text": "hello"}, "d")
    u = h.storage_usage()
    assert u["quota_bytes"] == 50 * 1024**3
    assert u["used_bytes"] > 0 and u["count"] == 1
    assert 0.0 <= u["percent"] <= 100.0


def test_delete_rejects_path_traversal(monkeypatch, tmp_path):
    h = _fresh(monkeypatch, tmp_path)
    d = h.delete_review("../../etc/passwd")
    assert d["deleted"] is False


def test_save_review_handles_write_error(monkeypatch, tmp_path):
    h = _fresh(monkeypatch, tmp_path)
    import json as _json
    monkeypatch.setattr(h.json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    r = h.save_review({"script_text": "x"}, "doc")
    assert r["saved"] is False and r["reason"] == "write_error"
    assert h.list_reviews() == []  # no partial file left behind
