# Originality Check (Plagiarism + AI) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add an on-demand "Check originality" action: best-effort web-plagiarism (Google-Search-grounded verbatim matches + sources, highlighted inline) and a rough AI-likelihood estimate (labeled not-a-verdict), surfaced in a new Originality panel.

**Architecture:** Two new repo-root modules (`plagiarism.py`, `ai_detect.py`) reuse the proven `facts_grounding` google-genai calls. A new `POST /api/originality` runs both and maps plagiarism matches to character spans via `matching.locate_quote`. The React review screen gets a button, merges the returned spans/aoi into the current result, and shows an `OriginalityPanel`.

**Tech Stack:** Python, FastAPI, google-genai (Vertex), pytest, React.

## Global Constraints

- Best-effort only; both results are labeled indicators, NOT verdicts.
- Plagiarism color `#f97316`; param name `"Plagiarism"`; aoi kind `"plagiarism"`.
- AI bands: likelihood <34 `low` (#2e9e5b), 34–66 `medium` (#d9a400), >66 `high` (#e5484d).
- `POST /api/originality` body `{text}`, min length 50 (→422); does NOT save to history.
- Reuse `facts_grounding.grounded_generate` (search) and a new `facts_grounding.ungrounded_generate` (no search). Parse JSON with `utils1.extract_review_json`.

---

## Task 1: Detection modules (`plagiarism.py`, `ai_detect.py`) + grounding helper

**Files:**
- Modify: `facts_grounding.py`
- Create: `plagiarism.py`, `ai_detect.py`
- Test: `tests/test_plagiarism.py`, `tests/test_ai_detect.py`

**Interfaces:**
- `facts_grounding.ungrounded_generate(prompt: str, temperature: float = 0.0) -> str`
- `plagiarism.run_plagiarism_check(text: str) -> {"web_grounded": bool, "matches": List[{quote_verbatim, sources:List[str], note}], "count": int}`
- `ai_detect.run_ai_detection(text: str) -> {"likelihood": int, "band": str, "reasoning": str}`

- [ ] **Step 1: Write failing tests**

Create `tests/test_plagiarism.py`:
```python
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
```

Create `tests/test_ai_detect.py`:
```python
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
```

- [ ] **Step 2: Run, expect failure**

Run: `python -m pytest tests/test_plagiarism.py tests/test_ai_detect.py -v`
Expected: FAIL (modules missing).

- [ ] **Step 3: Add `ungrounded_generate` to `facts_grounding.py`**

After the existing `grounded_generate` function, add:
```python
def ungrounded_generate(prompt: str, temperature: float = 0.0) -> str:
    """Plain (no search) Gemini call — used by AI-content detection."""
    return _ungrounded_call(prompt, temperature)
```

- [ ] **Step 4: Create `plagiarism.py`**

```python
"""Best-effort web-plagiarism check: find passages that appear verbatim online
via Google Search grounding. Not a true overlap %, won't catch paraphrasing."""
from __future__ import annotations

from typing import Any, Dict, List

from facts_grounding import grounded_generate
from utils1 import extract_review_json

_PROMPT = """You are a plagiarism checker with access to Google Search.
Find passages in the SCRIPT below that appear VERBATIM (or nearly verbatim) on the public web.
Only report a passage if you actually find it published online via search.

STRICT RULES:
- "quote_verbatim" MUST be copied EXACTLY from the script (a real substring), 8+ words.
- "sources" = up to 3 URLs where the passage (or near-identical text) appears. Real URLs only.
- "note" = one short phrase (e.g. "appears verbatim on news site").
- Do NOT report common phrases, names, dates, or short generic fragments.
- If nothing is found, return {"matches": []}.

Return ONLY JSON between the markers:
BEGIN_JSON
{"matches":[{"quote_verbatim":"...","sources":["..."],"note":"..."}]}
END_JSON

SCRIPT:
<<<
{script}
>>>
"""


def _grounded(prompt: str) -> str:
    return grounded_generate(prompt, temperature=0.0)


def _normalize(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for m in raw:
        if not isinstance(m, dict):
            continue
        q = str(m.get("quote_verbatim") or "").strip()
        if not q:
            continue
        srcs = m.get("sources") or []
        if isinstance(srcs, str):
            srcs = [srcs]
        srcs = [str(s).strip() for s in srcs if str(s).strip()][:3]
        out.append({"quote_verbatim": q, "sources": srcs, "note": str(m.get("note") or "").strip()})
    return out


def run_plagiarism_check(text: str) -> Dict[str, Any]:
    prompt = _PROMPT.replace("{script}", text or "")
    web_grounded = True
    try:
        raw_text = _grounded(prompt)
    except Exception:
        return {"web_grounded": False, "matches": [], "count": 0}
    data = extract_review_json(raw_text)
    matches = _normalize((data or {}).get("matches") if isinstance(data, dict) else [])
    return {"web_grounded": web_grounded, "matches": matches, "count": len(matches)}
```

- [ ] **Step 5: Create `ai_detect.py`**

```python
"""Rough AI-content likelihood via a single ungrounded Gemini pass.
LLM-based AI detection is unreliable — this is an indicator, NOT a verdict."""
from __future__ import annotations

from typing import Any, Dict

from facts_grounding import ungrounded_generate
from utils1 import extract_review_json

_PROMPT = """Estimate the probability that the following TEXT was generated by an AI model.
Consider signals like uniform sentence rhythm, generic phrasing, lack of specific voice,
and over-smooth transitions. Be calibrated; human writing can look polished too.

Return ONLY JSON between the markers:
BEGIN_JSON
{"likelihood": <integer 0-100>, "reasoning": "<one or two short sentences>"}
END_JSON

TEXT:
<<<
{script}
>>>
"""


def _band(likelihood: int) -> str:
    if likelihood > 66:
        return "high"
    if likelihood >= 34:
        return "medium"
    return "low"


def _generate(prompt: str) -> str:
    return ungrounded_generate(prompt, temperature=0.0)


def run_ai_detection(text: str) -> Dict[str, Any]:
    prompt = _PROMPT.replace("{script}", text or "")
    try:
        raw = _generate(prompt)
        data = extract_review_json(raw) or {}
    except Exception:
        data = {}
    try:
        likelihood = int(round(float(data.get("likelihood", 0))))
    except (TypeError, ValueError):
        likelihood = 0
    likelihood = max(0, min(100, likelihood))
    reasoning = str(data.get("reasoning") or "").strip()
    return {"likelihood": likelihood, "band": _band(likelihood), "reasoning": reasoning}
```

- [ ] **Step 6: Run tests, expect pass**

Run: `python -m pytest tests/test_plagiarism.py tests/test_ai_detect.py -v`
Expected: PASS.

- [ ] **Step 7: Full suite + commit**

Run: `python -m pytest -q` (all pass).
```bash
git add facts_grounding.py plagiarism.py ai_detect.py tests/test_plagiarism.py tests/test_ai_detect.py
git commit -m "feat: plagiarism (grounded) + ai-detection (rough) best-effort modules"
```

---

## Task 2: `POST /api/originality` endpoint (`backend/main.py`)

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_originality_api.py`

**Interfaces:** Consumes `plagiarism.run_plagiarism_check`, `ai_detect.run_ai_detection`, `matching.locate_quote`. Produces `POST /api/originality` per the spec response shape.

- [ ] **Step 1: Write failing test**

Create `tests/test_originality_api.py`:
```python
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
                                      "matches": [{"quote_verbatim": "They was late to the meeting",
                                                   "sources": ["https://example.com/x"], "note": "verbatim"}]})
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
    assert j["aoi"][aid]["sources"] == ["https://example.com/x"]


def test_originality_short_text(monkeypatch, tmp_path):
    main = _app(monkeypatch, tmp_path)
    c = TestClient(main.app)
    assert c.post("/api/originality", json={"text": "too short"}).status_code == 422
```

- [ ] **Step 2: Run, expect failure**

Run: `python -m pytest tests/test_originality_api.py -v`
Expected: FAIL (endpoint + imports missing).

- [ ] **Step 3: Implement the endpoint in `backend/main.py`**

(a) Add imports near the other detector imports:
```python
from plagiarism import run_plagiarism_check
from ai_detect import run_ai_detection
```
(b) Add the constant near `FACT_COLORS`:
```python
PLAGIARISM_COLOR = "#f97316"
```
(c) Add the endpoint (next to the other endpoints):
```python
class OriginalityIn(BaseModel):
    text: str


@app.post("/api/originality")
def originality(body: OriginalityIn):
    text = (body.text or "").strip()
    if len(text) < 50:
        raise HTTPException(status_code=422, detail="Need at least 50 characters to check.")

    try:
        ai = run_ai_detection(text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI detection failed: {e}")
    ai["disclaimer"] = ("Rough estimate — automated AI detection is unreliable. "
                        "Treat this as a signal, not a verdict.")

    try:
        plag = run_plagiarism_check(text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Plagiarism check failed: {e}")

    spans = []
    aoi = {}
    for i, m in enumerate(plag.get("matches", []), start=1):
        aid = f"PLAG-{i}"
        rng = locate_quote(text, m.get("quote_verbatim", ""))
        matched = bool(rng)
        line = text[rng[0]:rng[1]] if rng else (m.get("quote_verbatim", "") or "")
        aoi[aid] = {
            "param": "Plagiarism", "kind": "plagiarism", "matched": matched,
            "line": line, "issue": "Appears on the web" + (f" — {m['note']}" if m.get("note") else ""),
            "fix": "", "why": "Best-effort verbatim web match. Paraphrasing is not detected — verify manually.",
            "sources": m.get("sources", []),
        }
        if rng:
            spans.append({"start": rng[0], "end": rng[1], "color": PLAGIARISM_COLOR,
                          "aid": aid, "param": "Plagiarism"})

    return {
        "ai_detection": ai,
        "plagiarism": {"web_grounded": plag.get("web_grounded", False), "count": plag.get("count", 0)},
        "spans": spans,
        "aoi": aoi,
    }
```

- [ ] **Step 4: Run tests, expect pass**

Run: `python -m pytest tests/test_originality_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Full suite + commit**

Run: `python -m pytest -q` (all pass).
```bash
git add backend/main.py tests/test_originality_api.py
git commit -m "feat: POST /api/originality endpoint (plagiarism spans + ai detection)"
```

---

## Task 3: Frontend — button, panel, inline plagiarism

**Files:**
- Modify: `frontend/src/api.js`, `frontend/src/App.jsx`, `frontend/src/components/SuggestionList.jsx`, `frontend/src/styles.css`
- Create: `frontend/src/components/OriginalityPanel.jsx`

- [ ] **Step 1: Add API client call (`api.js`)**

Append:
```javascript
export async function checkOriginality(text) {
  return _json(await fetch('/api/originality', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }))
}
```

- [ ] **Step 2: Create `OriginalityPanel.jsx`**

```jsx
import React from 'react'

const BAND = {
  low: { color: '#2e9e5b', label: 'Low' },
  medium: { color: '#d9a400', label: 'Medium' },
  high: { color: '#e5484d', label: 'High' },
}

export default function OriginalityPanel({ data }) {
  if (!data) return null
  const ai = data.ai_detection || {}
  const plag = data.plagiarism || {}
  const band = BAND[ai.band] || BAND.low
  return (
    <div className="orig-panel">
      <div className="orig-title">Originality <span className="orig-tag">best-effort</span></div>

      <div className="orig-row">
        <div className="orig-row-top">
          <span>AI likelihood</span>
          <strong style={{ color: band.color }}>{ai.likelihood ?? 0}% · {band.label}</strong>
        </div>
        <div className="orig-meter"><div className="orig-meter-fill" style={{ width: `${ai.likelihood || 0}%`, background: band.color }} /></div>
        {ai.reasoning && <p className="orig-note">{ai.reasoning}</p>}
        {ai.disclaimer && <p className="orig-disclaimer">{ai.disclaimer}</p>}
      </div>

      <div className="orig-row">
        <div className="orig-row-top">
          <span>Plagiarism</span>
          <strong>{plag.count || 0} match{(plag.count || 0) === 1 ? '' : 'es'}</strong>
        </div>
        <p className="orig-note">
          {plag.web_grounded ? 'Checked against Google Search. ' : 'Web search unavailable. '}
          Verbatim web matches only — paraphrasing isn’t detected. Verify manually.
        </p>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Wire the button + merge in `App.jsx`**

1. Import: add `checkOriginality` to the `./api.js` import, and
   `import OriginalityPanel from './components/OriginalityPanel.jsx'`.
2. Add state: `const [origLoading, setOrigLoading] = useState(false)`.
3. Add handler:
```jsx
  async function onCheckOriginality() {
    if (!result || origLoading) return
    setOrigLoading(true)
    try {
      const o = await checkOriginality(result.script_text)
      setResult((prev) => ({
        ...prev,
        spans: [...prev.spans, ...(o.spans || [])],
        aoi: { ...prev.aoi, ...(o.aoi || {}) },
        param_colors: { ...prev.param_colors, Plagiarism: '#f97316' },
        originality: { ai_detection: o.ai_detection, plagiarism: o.plagiarism },
      }))
    } catch (e) {
      window.alert(e.message || 'Originality check failed.')
    } finally {
      setOrigLoading(false)
    }
  }
```
4. In the review header actions (`.rev-actions`), add the button before "Copy edited":
```jsx
            {!result.originality && (
              <button className="btn" onClick={onCheckOriginality} disabled={origLoading}>
                {origLoading ? 'Checking…' : 'Check originality'}
              </button>
            )}
```
5. In the margin (`.margin-col`), render the panel above the Report (before the `<details className="report">`):
```jsx
            {result.originality && <OriginalityPanel data={result.originality} />}
```

- [ ] **Step 4: Show sources for plagiarism cards (`SuggestionList.jsx`)**

Change the sources condition so plagiarism cards show links too. Replace:
```jsx
      {isFact && item.sources && item.sources.length > 0 && (
```
with:
```jsx
      {item.sources && item.sources.length > 0 && (
```
(The `isFact`/`kind` logic for labels stays; plagiarism items have `kind:"plagiarism"` so they
fall into the non-fact branch for Issue/Fix labels, which is fine — they have an `issue` and no `fix`.)

- [ ] **Step 5: Add CSS (`styles.css`)**

Append:
```css
.orig-panel { border: 1px solid var(--line); border-radius: 10px; background: var(--paper); padding: 12px 14px; margin-bottom: 16px; }
.orig-title { font-size: 12.5px; font-weight: 700; display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.orig-tag { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: #b4540a; background: #f9731620; border-radius: 999px; padding: 2px 7px; }
.orig-row { margin: 10px 0; }
.orig-row-top { display: flex; justify-content: space-between; align-items: baseline; font-size: 12.5px; margin-bottom: 5px; }
.orig-row-top strong { font-variant-numeric: tabular-nums; }
.orig-meter { height: 7px; border-radius: 999px; background: #eceae4; overflow: hidden; }
.orig-meter-fill { height: 100%; border-radius: 999px; transition: width .3s ease; }
.orig-note { font-size: 12px; color: var(--muted); margin: 6px 0 0; }
.orig-disclaimer { font-size: 11.5px; color: #b4540a; margin: 6px 0 0; font-style: italic; }
```

- [ ] **Step 6: Build + manual smoke + commit**

Run: `cd frontend && npm run build` (succeeds).
Manual (with backend + Vertex creds): run a review, click **Check originality** → panel shows AI meter + plagiarism summary; any matched passages highlight orange with source links; the "best-effort" tag + disclaimer are visible.
```bash
git add frontend/src
git commit -m "feat(ui): on-demand originality check — panel, button, inline plagiarism highlights"
```

---

## Self-Review Notes

- Coverage: ungrounded_generate (T1) ✓; plagiarism.py (T1) ✓; ai_detect.py (T1) ✓; endpoint w/ spans+ai (T2) ✓; button+merge+panel+sources (T3) ✓; disclaimers/best-effort labels (T2 disclaimer, T3 panel) ✓.
- Consistency: response keys (`ai_detection`, `plagiarism`, `spans`, `aoi`) produced in T2 match what App.jsx merges in T3; `param:"Plagiarism"` + color `#f97316` consistent across T2/T3; `kind:"plagiarism"` + `sources` consumed by SuggestionList (T3 step 4).
- Honesty: best-effort tag + AI disclaimer + plagiarism caveat are all in the panel; no "%" claim for plagiarism.
