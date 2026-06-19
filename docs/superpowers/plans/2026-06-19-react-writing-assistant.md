# React Writing Assistant + VPS History — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repo's React (Vite) + FastAPI stack the single Writing Assistant UI — rewired to the 5-category engine, with a fixed web-grounded fact-check, a paste-text option, and a VPS-disk review history (50 GB quota, usage progress bar, permanent delete). Remove the Streamlit UI.

**Architecture:** FastAPI (`backend/main.py`) reuses `utils1`, `review_engine_multi` (4 writing categories via a new `include_facts=False`), `backend/matching.py` (quote→span), `factcheck.py` (google-genai grounding), and a new `backend/history.py` (VPS-disk JSON store). React SPA renders highlights + suggestion cards + a history view + a storage bar.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, pytest, `google-genai`, `langchain-google-vertexai` (writing specialists), React 18 + Vite.

## Global Constraints

- Writing categories (verbatim, the only ones the API surfaces): `Grammar`, `Spelling`, `Punctuation`, `Style/Clarity`. Plus a separate `Fact Check` path. The engine's own `Facts` category is NOT surfaced by the API.
- Writing-category colors: Grammar `#ff6b6b`, Spelling `#6b8cff`, Punctuation `#eab308`, Style/Clarity `#a78bfa`. Fact verdict colors: incorrect `#ef4444`, unverifiable `#f59e0b`, correct `#22c55e`.
- History: `HISTORY_DIR` env (default `Scriptmodel/outputs/_history`), `HISTORY_QUOTA_GB` env (default `50`). 1 GB = 1024³ bytes. One JSON file per review. Block new saves when `used_bytes >= quota_bytes`. Delete is permanent `os.remove`, path validated inside `HISTORY_DIR`.
- Fact-check uses `google-genai` `Client(vertexai=True,...)` + `types.Tool(google_search=types.GoogleSearch())`; fallback ungrounded via google-genai (no langchain/torch).
- Vertex env: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (default us-central1), `GOOGLE_APPLICATION_CREDENTIALS`, `GEMINI_MODEL` (default gemini-2.5-flash).
- LLM temperature 0.0. English only. No auth/multi-user (single shared history store).

---

## File Structure

- `review_engine_multi.py` — add `include_facts: bool = True` param. **Modify.**
- `factcheck.py` — migrate grounding to google-genai. **Modify.**
- `backend/matching.py` — 4 writing-category colors; relax heading suppression. **Modify.**
- `backend/history.py` — VPS-disk history store. **Create.**
- `backend/main.py` — rewire response, `include_facts=False`, `/api/analyze-text`, history endpoints, auto-save. **Modify.**
- `frontend/src/api.js` — add text/history/storage client calls. **Modify.**
- `frontend/src/components/ScorePanel.jsx` — show `summary`, drop viral fields. **Modify.**
- `frontend/src/components/StorageBar.jsx`, `HistoryView.jsx` — new components. **Create.**
- `frontend/src/App.jsx` — rebrand, paste tab, history view, storage bar, save-full banner. **Modify.**
- `frontend/src/styles.css` — styles for paste/history/storage. **Modify.**
- `app_grammarly_ui.py` — **Delete.** `requirements.txt` — remove `streamlit`. `README.md` — consolidate.
- Tests: `tests/test_history.py`, `tests/test_factcheck.py`, `tests/test_engine_include_facts.py`, `tests/test_backend_api.py`. **Create.**

---

## Task 1: Engine `include_facts` flag

**Files:**
- Modify: `review_engine_multi.py` (function `run_review_multi`)
- Test: `tests/test_engine_include_facts.py`

**Interfaces:**
- Produces: `run_review_multi(script_text, prompts_dir=..., temperature=0.0, include_facts=True)`. When `include_facts=False`, only specialists 1–4 (Grammar, Spelling, Punctuation, Style/Clarity) run and the aggregator runs over those 4; `scores`/`per_parameter` contain exactly those 4 keys.

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_include_facts.py`:
```python
import json
import review_engine_multi as eng


class _Resp:
    def __init__(self, content): self.content = content


def _specialist_json(pid, score):
    return ("BEGIN_JSON\n" + json.dumps({
        "parameter_id": pid, "score": score, "explanation_bullets": ["ok"],
        "weakness": "Not present", "suggestions": [], "areas_of_improvement": [], "summary": "ok",
    }) + "\nEND_JSON")


def test_include_facts_false_runs_only_four_writing_categories(monkeypatch):
    seq = [_specialist_json(p, 8) for p in ("grammar", "spelling", "punctuation", "style")]

    class _LLM:
        def invoke(self, prompt): return _Resp(seq.pop(0))

    class _Agg:
        overall_rating = 7; strengths = ["a"]; weaknesses = ["b"]; suggestions = ["c"]
        summary = "ok"; corrected_text = "fixed"

    class _StructLLM:
        def invoke(self, prompt): return _Agg()

    class _AggLLM:
        def with_structured_output(self, schema): return _StructLLM()

    calls = {"n": 0}
    def make_llm(t):
        calls["n"] += 1
        return _LLM() if calls["n"] == 1 else _AggLLM()

    monkeypatch.setattr(eng, "_make_llm", make_llm)
    monkeypatch.setattr(eng, "_require_vertex_config", lambda: None)
    # grounded_generate must NOT be called when include_facts=False
    def _boom(*a, **k): raise AssertionError("Facts specialist should not run")
    monkeypatch.setattr(eng, "grounded_generate", _boom)
    monkeypatch.setattr(eng, "_load_prompt", lambda prefix, n: ("{evidence_json} {script}" if n == 6 else "{script}"))

    out = eng.run_review_multi("text", prompts_dir="x", temperature=0.0, include_facts=False)
    data = json.loads(out.split("BEGIN_JSON")[1].split("END_JSON")[0])
    assert set(data["scores"].keys()) == {"Grammar", "Spelling", "Punctuation", "Style/Clarity"}
    assert "Facts" not in data["per_parameter"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_include_facts.py -v`
Expected: FAIL — `run_review_multi` has no `include_facts` param (TypeError) or runs Facts.

- [ ] **Step 3: Implement the flag**

In `review_engine_multi.py`, change the signature of `run_review_multi` to add `include_facts: bool = True` (keep other params/order; add it after `temperature`). Then change the specialist loop bound so it stops before Facts when disabled. Replace the loop header:
```python
    last_specialist = 5 if include_facts else 4
    for i in range(1, last_specialist + 1):
```
(Everything inside the loop is unchanged — the `if name == "Facts"` branch simply never runs when `last_specialist == 4`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_include_facts.py -v`
Expected: PASS.

- [ ] **Step 5: Run the existing engine test (default still 5 categories)**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS (default `include_facts=True` keeps 5 categories).

- [ ] **Step 6: Commit**

```bash
git add review_engine_multi.py tests/test_engine_include_facts.py
git commit -m "feat: run_review_multi include_facts flag (skip engine Facts pass)"
```

---

## Task 2: Fact-check grounding migration (`factcheck.py`)

**Files:**
- Modify: `factcheck.py` (`_build_search_tool`/`_grounded_text`/`_plain_text`)
- Test: `tests/test_factcheck.py`

**Interfaces:**
- Produces: `run_fact_check(script_text) -> {"web_grounded": bool, "claims": [...], "error"?: str}`; internal seams `_grounded_text(prompt) -> str` (google-genai + google_search) and `_plain_text(prompt) -> str` (google-genai, no tools). `_normalize` unchanged.

- [ ] **Step 1: Write the failing/structled test**

Create `tests/test_factcheck.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails or passes structurally**

Run: `python -m pytest tests/test_factcheck.py -v`
Expected: the two monkeypatched tests should already pass if seams exist; `test_seams_exist` passes. (If the module import fails for any reason, fix imports first.) Proceed to migrate the seam internals regardless.

- [ ] **Step 3: Migrate `_grounded_text` and `_plain_text` to google-genai**

In `factcheck.py`, DELETE `_build_search_tool` and replace `_grounded_text` and `_plain_text` with:
```python
def _genai_client():
    from google import genai
    return genai.Client(vertexai=True, project=_PROJECT, location=_LOCATION)


def _grounded_text(prompt: str) -> str:
    from google.genai import types
    client = _genai_client()
    resp = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.0,
        ),
    )
    return getattr(resp, "text", "") or ""


def _plain_text(prompt: str) -> str:
    from google.genai import types
    client = _genai_client()
    resp = client.models.generate_content(
        model=_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return getattr(resp, "text", "") or ""
```
Leave `run_fact_check`, `_normalize`, `_PROMPT`, and the module constants unchanged.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_factcheck.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Live smoke (manual; needs Vertex creds)**

Run:
```bash
python -c "import factcheck as f; print(f._grounded_text('Using Google Search, what year did the Titanic sink? Return BEGIN_JSON {\"claims\":[]} END_JSON if unsure, else a one line answer.'))"
```
Expected: a short grounded answer mentioning 1912. If it errors only due to credentials/network, note it; the code path mirrors the already-verified `facts_grounding` fix.

- [ ] **Step 6: Commit**

```bash
git add factcheck.py tests/test_factcheck.py
git commit -m "fix: factcheck.py grounding via google-genai google_search (torch-free)"
```

---

## Task 3: Span matcher — colors + heading relax (`backend/matching.py`)

**Files:**
- Modify: `backend/matching.py`
- Test: `tests/test_matching.py`

**Interfaces:**
- Produces: `PARAM_COLORS` with the 4 writing-category keys; `build_spans_by_param(script_text, data)` and `locate_quote(script_text, quote)` no longer drop heading-like/short quotes.

- [ ] **Step 1: Write the failing test**

Create `tests/test_matching.py`:
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import matching


def test_colors_are_writing_categories():
    assert set(matching.PARAM_COLORS.keys()) == {
        "Grammar", "Spelling", "Punctuation", "Style/Clarity"}


def test_short_heading_like_quote_still_locates():
    # a single capitalized word that the old heading filter would drop
    text = "Introduction\nThey was late."
    rng = matching.locate_quote(text, "Introduction")
    assert rng is not None and text[rng[0]:rng[1]] == "Introduction"


def test_build_spans_maps_grammar_quote():
    text = "They was late to the meeting."
    data = {"per_parameter": {"Grammar": {"areas_of_improvement": [
        {"quote_verbatim": "They was late", "issue": "x", "fix": "They were late", "why_this_helps": "y"}]}}}
    spans_map, ranges = matching.build_spans_by_param(text, data)
    assert spans_map["Grammar"], "expected one Grammar span"
    s, e, color, aid = spans_map["Grammar"][0]
    assert text[s:e].startswith("They was late")
    assert color == "#ff6b6b"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_matching.py -v`
Expected: FAIL — `PARAM_COLORS` still has viral keys and `locate_quote("Introduction")` returns None (heading filter).

- [ ] **Step 3: Replace `PARAM_COLORS`**

In `backend/matching.py`:
```python
PARAM_COLORS: Dict[str, str] = {
    "Grammar":       "#ff6b6b",
    "Spelling":      "#6b8cff",
    "Punctuation":   "#eab308",
    "Style/Clarity": "#a78bfa",
}
```

- [ ] **Step 4: Relax heading suppression**

In `build_spans_by_param`, delete these three lines:
```python
            if _is_heading_like(clean):
                continue
```
```python
            if heading_ranges and _overlaps_any(s, e, heading_ranges):
                continue
            if _is_heading_context(script_text, s, e):
                continue
```
In `locate_quote`, change:
```python
    clean = _clean_quote_for_match(cleaned)
    if not clean or _is_heading_like(clean):
        return None
```
to:
```python
    clean = _clean_quote_for_match(cleaned)
    if not clean:
        return None
```
Leave `_is_heading_like` / `_is_heading_context` / `_overlaps_any` defined (still used elsewhere / harmless).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_matching.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/matching.py tests/test_matching.py
git commit -m "feat: matching.py writing-category colors + relaxed heading suppression"
```

---

## Task 4: VPS history store (`backend/history.py`)

**Files:**
- Create: `backend/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Produces (all paths under `HISTORY_DIR`, quota `HISTORY_QUOTA_GB`*1024³):
  - `storage_usage() -> {"used_bytes": int, "quota_bytes": int, "percent": float, "count": int}`
  - `save_review(payload: dict, title: str) -> {"saved": bool, "id": str|None, "reason": str|None}` — refuses (saved False, reason "storage_full") when `used_bytes >= quota_bytes`.
  - `list_reviews() -> [{"id","title","created_at","overall_rating","size_bytes"}]` newest first.
  - `load_review(id: str) -> dict|None`
  - `delete_review(id: str) -> {"deleted": bool, **storage_usage()}` — permanent; id validated to resolve inside `HISTORY_DIR`.
- Config read at call time from env so tests can set `HISTORY_DIR`/`HISTORY_QUOTA_GB` via monkeypatch.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_history.py -v`
Expected: FAIL — module `history` does not exist.

- [ ] **Step 3: Implement `backend/history.py`**

Create `backend/history.py`:
```python
"""VPS-disk review history: one JSON file per review, with a byte quota."""
from __future__ import annotations

import os
import re
import json
import uuid
import glob
import datetime
from typing import Any, Dict, List, Optional

_GB = 1024 ** 3
_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")  # safe ids only (no path separators)


def _history_dir() -> str:
    d = os.getenv("HISTORY_DIR", "Scriptmodel/outputs/_history")
    os.makedirs(d, exist_ok=True)
    return d


def _quota_bytes() -> int:
    try:
        gb = float(os.getenv("HISTORY_QUOTA_GB", "50"))
    except ValueError:
        gb = 50.0
    return int(gb * _GB)


def _file_for(rid: str) -> Optional[str]:
    if not rid or not _ID_RE.match(rid):
        return None
    p = os.path.join(_history_dir(), rid + ".json")
    # ensure the resolved path stays inside the history dir
    base = os.path.realpath(_history_dir())
    full = os.path.realpath(p)
    if os.path.dirname(full) != base:
        return None
    return p


def storage_usage() -> Dict[str, Any]:
    d = _history_dir()
    files = glob.glob(os.path.join(d, "*.json"))
    used = sum(os.path.getsize(f) for f in files if os.path.exists(f))
    quota = _quota_bytes()
    percent = (used / quota * 100.0) if quota > 0 else 100.0
    return {"used_bytes": used, "quota_bytes": quota, "percent": round(percent, 2), "count": len(files)}


def save_review(payload: Dict[str, Any], title: str) -> Dict[str, Any]:
    usage = storage_usage()
    if usage["used_bytes"] >= usage["quota_bytes"]:
        return {"saved": False, "id": None, "reason": "storage_full"}
    rid = uuid.uuid4().hex
    now = datetime.datetime.now().replace(microsecond=0)
    record = dict(payload)
    record["id"] = rid
    record["title"] = title or "untitled"
    record["created_at"] = now.isoformat()
    if "overall_rating" not in record:
        record["overall_rating"] = payload.get("overall_rating", "")
    path = os.path.join(_history_dir(), rid + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)
    return {"saved": True, "id": rid, "reason": None}


def list_reviews() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in glob.glob(os.path.join(_history_dir(), "*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                j = json.load(fh)
        except Exception:
            continue
        out.append({
            "id": j.get("id") or os.path.splitext(os.path.basename(f))[0],
            "title": j.get("title", "untitled"),
            "created_at": j.get("created_at", ""),
            "overall_rating": j.get("overall_rating", ""),
            "size_bytes": os.path.getsize(f),
        })
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return out


def load_review(rid: str) -> Optional[Dict[str, Any]]:
    path = _file_for(rid)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def delete_review(rid: str) -> Dict[str, Any]:
    path = _file_for(rid)
    deleted = False
    if path and os.path.exists(path):
        try:
            os.remove(path)
            deleted = True
        except OSError:
            deleted = False
    return {"deleted": deleted, **storage_usage()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_history.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/history.py tests/test_history.py
git commit -m "feat: VPS-disk review history store with quota + permanent delete"
```

---

## Task 5: Backend API rewire + endpoints (`backend/main.py`)

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_backend_api.py`

**Interfaces:**
- Consumes: `review_engine_multi.run_review_multi(..., include_facts=False)`, `backend.matching`, `factcheck.run_fact_check`, `backend.history`.
- Produces endpoints: `GET /api/health`, `POST /api/analyze` (file), `POST /api/analyze-text` (`{text}`), `GET /api/history`, `GET /api/history/{id}`, `DELETE /api/history/{id}`, `GET /api/storage`. Analysis response keys: `script_text, scores, overall_rating, strengths, weaknesses, suggestions, summary, param_order, param_colors, per_parameter, spans, aoi, fact_check, saved, save_error`.

- [ ] **Step 1: Write the failing test (FastAPI TestClient, pipeline mocked)**

Create `tests/test_backend_api.py`:
```python
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
        "scores": {"Grammar": 8, "Spelling": 9, "Punctuation": 7, "Style/Clarity": 10},
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
    assert set(j["param_order"]) == {"Grammar", "Spelling", "Punctuation", "Style/Clarity"}
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend_api.py -v`
Expected: FAIL — `/api/analyze-text`, history endpoints, and `summary` don't exist yet.

- [ ] **Step 3: Rewire `backend/main.py`**

Replace the imports block additions and add a shared analyzer + endpoints. Specifically:

(a) Update imports near the top (after the existing `from factcheck import run_fact_check`):
```python
from pydantic import BaseModel
import history as history_store
```
And ensure the engine call passes `include_facts=False` — change the existing `run_review_multi(...)` call to:
```python
        review_text = run_review_multi(script_text=script_text, prompts_dir=PROMPTS_DIR,
                                       temperature=0.0, include_facts=False)
```

(b) Extract the body of the current `analyze` (everything after `script_text` is obtained) into a helper `def _analyze_text(script_text: str, title: str) -> dict:` that returns the response dict. In that response dict:
- remove `"drop_off_risks"` and `"viral_quotient"`;
- add `"summary": data.get("summary", "")`;
- keep `param_order` as the 4 writing categories: `"param_order": [p for p in PARAM_ORDER if p != "Facts"]`;
- at the very end, save to history and attach flags:
```python
    save = history_store.save_review(response, title)
    response["saved"] = save["saved"]
    response["save_error"] = save["reason"]
    return response
```
(Note: build `response` first, then save the same dict; `save_review` adds id/title/created_at to the stored copy.)

(c) Rewrite `analyze` (file upload) to call the helper:
```python
@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    filename = file.filename or "uploaded"
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Please upload a .docx, .pdf, or .txt file.")
    raw = await file.read()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw); tmp_path = tmp.name
        script_text = load_script_file(tmp_path)
    finally:
        if tmp_path:
            try: os.remove(tmp_path)
            except OSError: pass
    if len((script_text or "").strip()) < 50:
        raise HTTPException(status_code=422, detail="Extracted text looks too short. Check the file.")
    return _analyze_text(script_text, os.path.splitext(os.path.basename(filename))[0] or "uploaded")
```

(d) Add the text endpoint + history/storage endpoints:
```python
class TextIn(BaseModel):
    text: str


@app.post("/api/analyze-text")
def analyze_text(body: TextIn):
    script_text = (body.text or "").strip()
    if len(script_text) < 50:
        raise HTTPException(status_code=422, detail="Please paste at least 50 characters of text.")
    return _analyze_text(script_text, "pasted-text")


@app.get("/api/history")
def get_history():
    return history_store.list_reviews()


@app.get("/api/history/{rid}")
def get_history_item(rid: str):
    rec = history_store.load_review(rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    return rec


@app.delete("/api/history/{rid}")
def delete_history_item(rid: str):
    return history_store.delete_review(rid)


@app.get("/api/storage")
def get_storage():
    return history_store.storage_usage()
```
Keep the `_analyze_text` helper wrapping the engine-failure try/except (`EnvironmentError`→500, other→502) and the JSON-parse / span-build / fact-check logic that already exists. Make sure `sys.path.insert(... parent)` stays so `history`/`matching` import from `backend/`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_backend_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Full backend-relevant suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_backend_api.py
git commit -m "feat: backend rewire — writing contract, analyze-text, history+storage endpoints"
```

---

## Task 6: Frontend rewire (`frontend/`)

**Files:**
- Modify: `frontend/src/api.js`, `frontend/src/components/ScorePanel.jsx`, `frontend/src/App.jsx`, `frontend/src/styles.css`
- Create: `frontend/src/components/StorageBar.jsx`, `frontend/src/components/HistoryView.jsx`

**Interfaces:**
- Consumes the backend endpoints from Task 5.
- No automated tests (React); verification is `npm run build` + manual smoke.

- [ ] **Step 1: Extend `frontend/src/api.js`**

Append:
```javascript
async function _json(res) {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try { const j = await res.json(); if (j && j.detail) detail = j.detail } catch (_) {}
    throw new Error(detail)
  }
  return res.json()
}

export async function analyzeText(text) {
  return _json(await fetch('/api/analyze-text', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }))
}

export async function getHistory() { return _json(await fetch('/api/history')) }
export async function getHistoryItem(id) { return _json(await fetch(`/api/history/${id}`)) }
export async function deleteHistoryItem(id) {
  return _json(await fetch(`/api/history/${id}`, { method: 'DELETE' }))
}
export async function getStorage() { return _json(await fetch('/api/storage')) }
```
(Leave `analyzeFile` as-is.)

- [ ] **Step 2: Update `ScorePanel.jsx`**

Replace the two viral `<Bullets>`/`viral_quotient` blocks (lines rendering "Drop-off Risks" and "Viral Quotient") with a Summary block:
```jsx
      <Bullets title="Strengths" items={result.strengths} />
      <Bullets title="Weaknesses" items={result.weaknesses} />
      <Bullets title="Suggestions" items={result.suggestions} />

      {result.summary && (
        <div className="block">
          <h4>Summary</h4>
          <p>{result.summary}</p>
        </div>
      )}
```

- [ ] **Step 3: Create `frontend/src/components/StorageBar.jsx`**

```jsx
import React from 'react'

function gb(bytes) { return (bytes / (1024 ** 3)).toFixed(2) }

export default function StorageBar({ usage }) {
  if (!usage) return null
  const pct = Math.min(100, usage.percent || 0)
  const danger = pct >= 90
  return (
    <div className="storagebar">
      <div className="storagebar-label">
        History storage: {gb(usage.used_bytes)} GB of {gb(usage.quota_bytes)} GB ({pct.toFixed(1)}%)
      </div>
      <div className="storagebar-track">
        <div className={`storagebar-fill ${danger ? 'danger' : ''}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Create `frontend/src/components/HistoryView.jsx`**

```jsx
import React from 'react'
import StorageBar from './StorageBar.jsx'

export default function HistoryView({ items, usage, onOpen, onDelete, onBack }) {
  return (
    <div className="historyview">
      <div className="history-head">
        <button className="btn ghost" onClick={onBack}>← Back</button>
        <h2>History</h2>
      </div>
      <StorageBar usage={usage} />
      {(!items || items.length === 0) ? (
        <p className="muted">No saved reviews yet.</p>
      ) : (
        <ul className="history-list">
          {items.map((it) => (
            <li key={it.id} className="history-row">
              <button className="history-open" onClick={() => onOpen(it.id)}>
                <span className="history-title">{it.title}</span>
                <span className="history-meta">{it.created_at} · Overall {it.overall_rating || '—'}/10</span>
              </button>
              <button className="btn ghost danger" onClick={() => onDelete(it.id)}>Delete</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Rewire `App.jsx`**

Make these precise edits:

1. Update imports:
```jsx
import { analyzeFile, analyzeText, getHistory, getHistoryItem, deleteHistoryItem, getStorage } from './api.js'
```
and add `import HistoryView from './components/HistoryView.jsx'`.

2. Add state (near the other `useState`s):
```jsx
  const [pasteText, setPasteText] = useState('')
  const [historyItems, setHistoryItems] = useState([])
  const [storage, setStorage] = useState(null)
  const [saveWarning, setSaveWarning] = useState(false)
```
(extend the `view` union to include `'history'`.)

3. Replace both brand strings `📝 Viral Script Reviewer` with `📝 Writing Assistant`. Replace the loading copy line `Analyzing <strong>{fileName}</strong> across 7 storytelling parameters…` with `Checking <strong>{fileName}</strong> for grammar, spelling, punctuation, style &amp; facts…` and replace `This runs 8 AI passes, so it can take a bit.` with `This runs several AI passes, so it can take a bit.`

4. After a successful analyze (`onPick` and a new paste handler), set the save warning and refresh storage. Add a paste handler and a result-setter helper:
```jsx
  function onResult(data) {
    setResult(data); setDecisions({}); setSelectedParam(null); setActiveAid(null)
    setSaveWarning(data && data.saved === false)
    setView('review')
    getStorage().then(setStorage).catch(() => {})
  }

  async function onAnalyzeText() {
    if (!pasteText.trim()) return
    setFileName('pasted text'); setView('loading'); setError('')
    try { onResult(await analyzeText(pasteText)) }
    catch (e) { setError(e.message || 'Something went wrong.'); setView('error') }
  }
```
and change `onPick` to call `onResult(data)` instead of the inline setters.

5. Add an "📁 History" button in BOTH topbars (upload screen + review screen). On click:
```jsx
  async function openHistory() {
    try {
      const [items, usage] = await Promise.all([getHistory(), getStorage()])
      setHistoryItems(items); setStorage(usage); setView('history')
    } catch (e) { setError(e.message); setView('error') }
  }
  async function openHistoryItem(id) {
    try { onResult(await getHistoryItem(id)) }
    catch (e) { setError(e.message); setView('error') }
  }
  async function removeHistoryItem(id) {
    if (!window.confirm('Permanently delete this saved review? This cannot be undone.')) return
    const usage = await deleteHistoryItem(id)
    setStorage(usage)
    setHistoryItems(await getHistory())
  }
```

6. Add the history screen render (before the `if (view !== 'review')` upload block):
```jsx
  if (view === 'history') {
    return (
      <div className="app">
        <header className="topbar"><div className="brand">📝 Writing Assistant</div></header>
        <div className="center-screen">
          <HistoryView items={historyItems} usage={storage}
            onOpen={openHistoryItem} onDelete={removeHistoryItem} onBack={reset} />
        </div>
      </div>
    )
  }
```

7. In the upload screen, add a paste area under the dropzone and a History button in the topbar:
```jsx
        <header className="topbar">
          <div className="brand">📝 Writing Assistant</div>
          <div className="topbar-right">
            <button className="btn ghost" onClick={openHistory}>📁 History</button>
          </div>
        </header>
```
and after the `dropzone` div, inside the `view === 'upload'` block:
```jsx
              <div className="paste-area">
                <div className="paste-or">or paste text</div>
                <textarea className="paste-input" rows={8} value={pasteText}
                  onChange={(e) => setPasteText(e.target.value)}
                  placeholder="Paste your text here (min 50 characters)…" />
                <button className="btn primary" disabled={pasteText.trim().length < 50}
                  onClick={onAnalyzeText}>Analyze text</button>
              </div>
```

8. In the review topbar-right, add the History button and a save warning banner. Add `<button className="btn ghost" onClick={openHistory}>📁 History</button>` among the buttons, and just below the `<header>` in the review return add:
```jsx
      {saveWarning && (
        <div className="save-warning">History full (50 GB) — delete old reviews to save new ones.</div>
      )}
```

- [ ] **Step 6: Add CSS in `frontend/src/styles.css`**

Append styles (match the existing dark/utility style; values are a sane default):
```css
.paste-area { margin-top: 18px; display: flex; flex-direction: column; gap: 8px; width: min(680px, 92vw); }
.paste-or { color: #9aa4b2; font-size: 13px; text-align: center; }
.paste-input { width: 100%; resize: vertical; padding: 10px 12px; border-radius: 10px;
  border: 1px solid #2a2f37; background: #1c2026; color: inherit; font: inherit; }
.storagebar { margin: 10px 0 18px; }
.storagebar-label { font-size: 12.5px; color: #9aa4b2; margin-bottom: 4px; }
.storagebar-track { height: 10px; border-radius: 999px; background: #2a2f37; overflow: hidden; }
.storagebar-fill { height: 100%; background: #4f8cff; transition: width .2s ease; }
.storagebar-fill.danger { background: #ef4444; }
.historyview { width: min(760px, 94vw); }
.history-head { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.history-list { list-style: none; padding: 0; margin: 0; }
.history-row { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  border: 1px solid #2a2f37; border-radius: 10px; padding: 10px 12px; margin: 8px 0; }
.history-open { flex: 1; text-align: left; background: none; border: 0; color: inherit; cursor: pointer;
  display: flex; flex-direction: column; gap: 3px; }
.history-title { font-weight: 600; }
.history-meta { font-size: 12px; color: #9aa4b2; }
.btn.ghost.danger { color: #ef4444; }
.save-warning { background: #ef444422; border: 1px solid #ef4444; color: #ef4444;
  padding: 8px 14px; text-align: center; font-size: 13.5px; }
```

- [ ] **Step 7: Build the frontend (verification)**

Run:
```bash
cd frontend && npm install && npm run build
```
Expected: build succeeds (no unresolved imports / syntax errors). Note: `npm install` needs network for first run.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: React UI — Writing Assistant rebrand, paste tab, history view, storage bar"
```

---

## Task 7: Remove Streamlit, consolidate docs, end-to-end verification

**Files:**
- Delete: `app_grammarly_ui.py`
- Modify: `requirements.txt` (remove `streamlit`), `README.md` (consolidate), delete `README_REACT.md`

- [ ] **Step 1: Remove the Streamlit app and dep**

Run:
```bash
git rm app_grammarly_ui.py
```
In `requirements.txt`, delete the `streamlit` line. (Leave `google-genai`, `langchain-google-vertexai`, etc.)

- [ ] **Step 2: Verify nothing imports the deleted module**

Run:
```bash
grep -rn "app_grammarly_ui" --include=*.py . || echo "no references — good"
```
Expected: no references.

- [ ] **Step 3: Full Python suite**

Run: `python -m pytest -q`
Expected: all tests pass (history, factcheck, matching, engine, backend api, plus prior utils/prompts/engine tests).

- [ ] **Step 4: Consolidate README**

Replace `README.md` with content describing the single React + FastAPI app: what it checks (grammar/spelling/punctuation/style + web-verified facts), run steps (backend `cd backend && uvicorn main:app --reload --port 8000`; frontend `cd frontend && npm install && npm run dev` → http://localhost:5173), env vars (Vertex + `HISTORY_DIR`, `HISTORY_QUOTA_GB`), the history/storage (50 GB, permanent delete) feature, and a "Manual verification" checklist. Then `git rm README_REACT.md`.

- [ ] **Step 5: Manual end-to-end smoke (real Vertex env)**

Document + (if creds available) run:
1. `cd backend && uvicorn main:app --port 8000`; open http://localhost:8000/api/health → `{"status":"ok"}`.
2. `cd frontend && npm run dev`; open http://localhost:5173.
3. Paste: "They was late too the meetng. World War II ended in 1946." → Analyze text.
   - 4 writing category pills with counts + a 🔎 Fact Check pill.
   - Grammar/Spelling highlights; clicking a card's **Apply** edits inline.
   - Fact Check shows "ended in 1946" wrong → 1945 with a source link.
4. Open **📁 History** → the run is listed; storage bar shows usage; **Delete** removes it permanently (list empties, bar drops).
Record any failures and fix before final review.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove Streamlit UI; consolidate README for React app"
```

---

## Self-Review Notes

- **Spec coverage:** include_facts (T1) ✓; factcheck google-genai (T2) ✓; matching colors+heading (T3) ✓; history store w/ quota+permanent delete (T4) ✓; backend rewire + analyze-text + history/storage endpoints (T5) ✓; React rebrand+paste+history+storage bar+save-full banner (T6) ✓; remove Streamlit + docs (T7) ✓.
- **Type/name consistency:** API response keys produced in T5 (`summary`, `param_order` 4 cats, `saved`, `save_error`) match what ScorePanel/App consume in T6. `PARAM_COLORS` keys (T3) match `param_order` (T5) and the engine category names (T1). History record fields (`id/title/created_at/overall_rating`, T4) match `list_reviews`/HistoryView usage (T4/T6).
- **Risks:** live fact grounding (T2) mirrors the already-verified facts_grounding fix; `npm install` and live Vertex steps need network/creds and are flagged manual.
