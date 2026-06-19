# Live Analysis Progress — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stream real per-stage progress during a review (Grammar → Spelling → Punctuation → Tense/Narrative → Hooks → Overall → Fact-check) so the loading screen shows a live checklist + progress bar instead of a bare spinner.

**Architecture:** The engine gains an `on_progress(stage)` callback; the backend runs `_analyze_text` in a thread and emits SSE (`stages`/`progress`/`result`/`error`) via a queue bridge from two new streaming endpoints; the React loading view consumes the stream and renders a stage checklist.

**Tech Stack:** FastAPI `StreamingResponse` + threading/queue, Gemini engine, pytest, React (fetch stream reader, SSE parse).

## Global Constraints

- Stage order (exact): `["Grammar","Spelling","Punctuation","Tense/Narrative","Hooks","Overall","Fact-check"]`.
- SSE events: `stages` `{stages:[...]}`, `progress` `{stage}`, `result` `{...}`, `error` `{detail}`. Media type `text/event-stream`; headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- Streaming endpoints: `POST /api/analyze-stream` (`{text}`, min 50 → 422) and `POST /api/analyze-file-stream` (multipart). Existing non-streaming endpoints stay unchanged.
- The worker thread must always enqueue a terminal `result` or `error` (try/finally) so the SSE generator ends.
- "Tense/Narrative" displays as "Tense" in the UI.

---

## Task 1: Engine `on_progress` callback

**Files:** Modify `review_engine_multi.py`; Test `tests/test_engine_progress.py`

**Interfaces:** `run_review_multi(script_text, prompts_dir=..., temperature=0.0, include_facts=True, on_progress=None)`. When provided, `on_progress(stage: str)` is called at the start of each specialist (stage = DISPLAY_BY_INDEX name) and once with `"Overall"` before the aggregator.

- [ ] **Step 1: Write the failing test**

Create `tests/test_engine_progress.py`:
```python
import json
import review_engine_multi as eng


class _Resp:
    def __init__(self, c): self.content = c


def _spec(pid):
    return ("BEGIN_JSON\n" + json.dumps({
        "parameter_id": pid, "score": 8, "explanation_bullets": ["x"],
        "weakness": "Not present", "suggestions": [], "areas_of_improvement": [], "summary": "x",
    }) + "\nEND_JSON")


def test_on_progress_fires_each_stage(monkeypatch):
    seq = [_spec(p) for p in ("g", "s", "p", "t", "h")]

    class _LLM:
        def invoke(self, prompt): return _Resp(seq.pop(0))

    class _Agg:
        overall_rating = 7; strengths = []; weaknesses = []; suggestions = []
        summary = "x"; corrected_text = "x"

    class _AggLLM:
        def with_structured_output(self, schema):
            class _S:
                def invoke(self, p): return _Agg()
            return _S()

    calls = {"n": 0}
    def make_llm(t):
        calls["n"] += 1
        return _LLM() if calls["n"] == 1 else _AggLLM()
    monkeypatch.setattr(eng, "_make_llm", make_llm)
    monkeypatch.setattr(eng, "_require_vertex_config", lambda: None)
    monkeypatch.setattr(eng, "_load_prompt", lambda prefix, n: ("{evidence_json} {script}" if n == 7 else "{script}"))

    stages = []
    eng.run_review_multi("text", prompts_dir="x", temperature=0.0,
                         include_facts=False, on_progress=lambda s: stages.append(s))
    assert stages == ["Grammar", "Spelling", "Punctuation", "Tense/Narrative", "Hooks", "Overall"]
```

- [ ] **Step 2: Run, expect fail**

Run: `python -m pytest tests/test_engine_progress.py -v` → FAIL (no `on_progress` param).

- [ ] **Step 3: Implement**

In `review_engine_multi.py`, add `on_progress=None` to `run_review_multi`'s signature (after `include_facts`). In the specialist loop, as the FIRST line inside the `for` body:
```python
        if on_progress:
            on_progress(name)
```
(`name = DISPLAY_BY_INDEX[i]` is already computed just below — move the `name = ...` line above the callback, or compute `name` before calling. Ensure `name` is set before `on_progress(name)`.)
Immediately before the aggregator template is loaded/invoked, add:
```python
    if on_progress:
        on_progress("Overall")
```

- [ ] **Step 4: Run, expect pass**

Run: `python -m pytest tests/test_engine_progress.py tests/test_engine.py tests/test_engine_include_facts.py -v` → PASS (existing engine tests still green since `on_progress` defaults to None).

- [ ] **Step 5: Commit**

```bash
git add review_engine_multi.py tests/test_engine_progress.py
git commit -m "feat: run_review_multi on_progress callback (per-stage)"
```

---

## Task 2: Streaming endpoints (`backend/main.py`)

**Files:** Modify `backend/main.py`; Test `tests/test_stream_api.py`

**Interfaces:** `_analyze_text(script_text, title, on_progress=None)`; `POST /api/analyze-stream`, `POST /api/analyze-file-stream` → `text/event-stream`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stream_api.py`:
```python
import os, sys, json, importlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from fastapi.testclient import TestClient


def _app(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORY_DIR", str(tmp_path))
    import main
    importlib.reload(main)
    review = ("BEGIN_JSON\n" + json.dumps({
        "scores": {"Grammar": 8, "Spelling": 9, "Punctuation": 7, "Tense/Narrative": 8, "Hooks": 7},
        "per_parameter": {}, "overall_rating": 8, "strengths": [], "weaknesses": [],
        "suggestions": [], "summary": "ok", "corrected_text": "ok",
    }) + "\nEND_JSON")
    # mocked engine that still fires progress so the stream shows it
    def fake_engine(script_text, prompts_dir, temperature, include_facts, on_progress=None):
        if on_progress:
            for s in ("Grammar", "Spelling", "Punctuation", "Tense/Narrative", "Hooks", "Overall"):
                on_progress(s)
        return review
    monkeypatch.setattr(main, "run_review_multi", fake_engine)
    monkeypatch.setattr(main, "run_fact_check", lambda text: {"web_grounded": True, "claims": []})
    return main


def test_stream_emits_stages_progress_result(monkeypatch, tmp_path):
    main = _app(monkeypatch, tmp_path)
    c = TestClient(main.app)
    r = c.post("/api/analyze-stream", json={"text": "They was late to the meeting. " * 3})
    assert r.status_code == 200
    body = r.text
    assert "event: stages" in body
    assert "event: progress" in body
    assert "event: result" in body
    # the result frame carries the writing param_order
    result_line = [l for l in body.splitlines() if l.startswith("data:") and "param_order" in l][0]
    data = json.loads(result_line[len("data:"):].strip())
    assert set(data["param_order"]) == {"Tense/Narrative", "Hooks", "Grammar", "Spelling", "Punctuation"}


def test_stream_short_text(monkeypatch, tmp_path):
    main = _app(monkeypatch, tmp_path)
    c = TestClient(main.app)
    assert c.post("/api/analyze-stream", json={"text": "short"}).status_code == 422
```

- [ ] **Step 2: Run, expect fail**

Run: `python -m pytest tests/test_stream_api.py -v` → FAIL.

- [ ] **Step 3: Implement in `backend/main.py`**

(a) Imports near the top:
```python
import json
import queue
import threading
from fastapi.responses import StreamingResponse
```
(b) Add `on_progress=None` to `_analyze_text`'s signature: `def _analyze_text(script_text: str, title: str, on_progress=None) -> dict:`. Pass it to the engine call:
```python
        review_text = run_review_multi(script_text=script_text, prompts_dir=PROMPTS_DIR,
                                       temperature=0.0, include_facts=False, on_progress=on_progress)
```
And immediately before `fc = run_fact_check(script_text)` add:
```python
    if on_progress:
        on_progress("Fact-check")
```
(c) Add the stage list + bridge + endpoints (near the other endpoints):
```python
STREAM_STAGES = ["Grammar", "Spelling", "Punctuation", "Tense/Narrative", "Hooks", "Overall", "Fact-check"]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream_analysis(script_text: str, title: str) -> StreamingResponse:
    q: "queue.Queue" = queue.Queue()

    def on_progress(stage):
        q.put(("progress", {"stage": stage}))

    def worker():
        try:
            res = _analyze_text(script_text, title, on_progress=on_progress)
            q.put(("result", res))
        except HTTPException as he:
            q.put(("error", {"detail": str(he.detail)}))
        except Exception as e:  # pragma: no cover
            q.put(("error", {"detail": str(e)}))
        finally:
            q.put(("__done__", None))

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        yield _sse("stages", {"stages": STREAM_STAGES})
        while True:
            kind, payload = q.get()
            if kind == "__done__":
                break
            yield _sse(kind, payload)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/analyze-stream")
def analyze_stream(body: TextIn):
    text = (body.text or "").strip()
    if len(text) < 50:
        raise HTTPException(status_code=422, detail="Please paste at least 50 characters of text.")
    return _stream_analysis(text, "pasted-text")


@app.post("/api/analyze-file-stream")
async def analyze_file_stream(file: UploadFile = File(...)):
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
    return _stream_analysis(script_text, os.path.splitext(os.path.basename(filename))[0] or "uploaded")
```

- [ ] **Step 4: Run, expect pass**

Run: `python -m pytest tests/test_stream_api.py -v` → PASS (2). Then `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_stream_api.py
git commit -m "feat: SSE streaming analyze endpoints with per-stage progress"
```

---

## Task 3: Frontend streaming + progress checklist

**Files:** Modify `frontend/src/api.js`, `frontend/src/App.jsx`, `frontend/src/styles.css`

- [ ] **Step 1: Add streaming clients to `api.js`**

Append:
```javascript
async function _streamAnalyze(url, init, onProgress) {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try { const j = await res.json(); if (j && j.detail) detail = j.detail } catch (_) {}
    throw new Error(detail)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = '', result = null, errDetail = null
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const frames = buf.split('\n\n'); buf = frames.pop()
    for (const f of frames) {
      let event = 'message', data = ''
      for (const line of f.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      let parsed; try { parsed = JSON.parse(data) } catch (_) { continue }
      if (event === 'stages') onProgress && onProgress({ type: 'stages', stages: parsed.stages })
      else if (event === 'progress') onProgress && onProgress({ type: 'progress', stage: parsed.stage })
      else if (event === 'result') result = parsed
      else if (event === 'error') errDetail = parsed.detail
    }
  }
  if (errDetail) throw new Error(errDetail)
  if (!result) throw new Error('No result received from the server.')
  return result
}

export function analyzeTextStream(text, onProgress) {
  return _streamAnalyze('/api/analyze-stream', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }),
  }, onProgress)
}
export function analyzeFileStream(file, onProgress) {
  const fd = new FormData(); fd.append('file', file)
  return _streamAnalyze('/api/analyze-file-stream', { method: 'POST', body: fd }, onProgress)
}
```

- [ ] **Step 2: Wire progress state + streaming in `App.jsx`**

1. Import: add `analyzeTextStream, analyzeFileStream` to the `./api.js` import (keep `analyzeFile`/`analyzeText` imported too — harmless).
2. Add state: `const [progress, setProgress] = useState({ stages: [], completed: [], current: null })`.
3. Add the progress handler:
```jsx
  function handleProgress(ev) {
    if (ev.type === 'stages') setProgress({ stages: ev.stages, completed: [], current: null })
    else if (ev.type === 'progress') {
      setProgress((p) => ({
        ...p,
        completed: p.current ? [...p.completed, p.current] : p.completed,
        current: ev.stage,
      }))
    }
  }
```
4. Change `onPick` and `onAnalyzeText` to reset progress and use the streaming clients:
```jsx
  async function onPick(file) {
    if (!file) return
    setFileName(file.name); setProgress({ stages: [], completed: [], current: null })
    setView('loading'); setError('')
    try { onResult(await analyzeFileStream(file, handleProgress)) }
    catch (e) { setError(e.message || 'Something went wrong.'); setView('error') }
  }

  async function onAnalyzeText() {
    if (pasteText.trim().length < 50) return
    setFileName('Pasted text'); setProgress({ stages: [], completed: [], current: null })
    setView('loading'); setError('')
    try { onResult(await analyzeTextStream(pasteText, handleProgress)) }
    catch (e) { setError(e.message || 'Something went wrong.'); setView('error') }
  }
```
5. Replace the `view === 'loading'` block in `MainContent` with the progress view:
```jsx
    if (view === 'loading') {
      const total = progress.stages.length || 7
      const pct = Math.round((progress.completed.length / total) * 100)
      const label = (s) => (s === 'Tense/Narrative' ? 'Tense' : s)
      return (
        <div className="center-card">
          <div className="progress-card">
            <p className="progress-title">Reviewing <strong>{fileName}</strong></p>
            <div className="progress-bar"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
            {progress.stages.length === 0 ? (
              <p className="muted">Starting the review…</p>
            ) : (
              <ul className="progress-steps">
                {progress.stages.map((s) => {
                  const state = progress.completed.includes(s) ? 'done'
                    : (s === progress.current ? 'active' : 'pending')
                  return (
                    <li key={s} className={`pstep ${state}`}>
                      <span className="pstep-ico">{state === 'done' ? '✓' : state === 'active' ? '' : ''}</span>
                      {label(s)}
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      )
    }
```

- [ ] **Step 3: Add CSS in `styles.css`**

Append:
```css
.progress-card { width: min(420px, 90vw); text-align: left; }
.progress-title { text-align: center; margin: 0 0 16px; color: var(--text); }
.progress-bar { height: 7px; border-radius: 999px; background: #e3e0d8; overflow: hidden; margin-bottom: 18px; }
.progress-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #8b6dff, #0ea5a5); transition: width .3s ease; }
.progress-steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px 18px; }
.pstep { display: flex; align-items: center; gap: 9px; font-size: 13.5px; color: var(--faint); }
.pstep-ico { width: 18px; height: 18px; flex: none; display: grid; place-items: center; border-radius: 50%;
  border: 1.5px solid var(--line-strong); font-size: 11px; }
.pstep.done { color: var(--text); }
.pstep.done .pstep-ico { background: #2e9e5b; border-color: #2e9e5b; color: #fff; }
.pstep.active { color: var(--text); font-weight: 600; }
.pstep.active .pstep-ico { border-color: #8b6dff; border-top-color: transparent; animation: spin .8s linear infinite; }
```

- [ ] **Step 4: Build + manual smoke + commit**

Run: `cd frontend && npm run build` (succeeds).
Manual (backend + Vertex creds): paste/upload a script → loading view shows the 7-stage checklist; stages tick over (Grammar ✓ … Fact-check) and the bar fills; the review appears at the end.
```bash
git add frontend/src
git commit -m "feat(ui): live per-stage progress checklist via SSE streaming"
```

---

## Self-Review Notes

- Coverage: engine callback (T1) ✓; SSE bridge + streaming endpoints + Fact-check stage (T2) ✓; streaming client + progress UI (T3) ✓.
- Consistency: stage names from engine `DISPLAY_BY_INDEX` (T1) + backend `"Fact-check"` (T2) == `STREAM_STAGES` (T2) == the list the UI renders from the `stages` event (T3). SSE event names (`stages`/`progress`/`result`/`error`) match between T2 emit and T3 parse.
- Safety: worker thread always enqueues a terminal marker (try/finally) so the generator ends; non-streaming endpoints untouched so existing tests stay green.
