# Live Analysis Progress — Design

**Date:** 2026-06-19
**Status:** Approved — proceed to plan + implementation
**Builds on:** the React Writing Assistant.

## 1. Goal

Replace the indeterminate spinner with a **live, per-stage progress** view during a review:
a checklist of the 7 known stages with checkmarks + a progress bar, driven by real
backend signals (not a timer).

## 2. The 7 stages (in order)

`Grammar → Spelling → Punctuation → Tense/Narrative → Hooks → Overall → Fact-check`

(5 writing specialists + the aggregator "Overall" + the backend "Fact-check" pass.)

## 3. Mechanism — SSE streaming

The analysis is one blocking call, so the backend streams progress while it runs:

- **Engine** (`run_review_multi`) gains an optional `on_progress(stage: str)` callback,
  fired at the start of each specialist (stage = its display name) and before the aggregator
  (`"Overall"`).
- **Backend** `_analyze_text(script_text, title, on_progress=None)` passes the callback to the
  engine and fires `on_progress("Fact-check")` before its fact-check pass.
- A **streaming bridge** runs `_analyze_text` in a background thread; `on_progress` pushes
  events onto a `queue.Queue`; a FastAPI `StreamingResponse` (media type `text/event-stream`)
  drains the queue and emits SSE:
  - `event: stages` `{stages:[...7...]}` once at the start,
  - `event: progress` `{stage:"<name>"}` as each stage starts,
  - `event: result` `{<full response>}` at the end, or `event: error` `{detail}`.
  - Headers `Cache-Control: no-cache`, `X-Accel-Buffering: no` (disable proxy buffering).
- Two streaming endpoints: `POST /api/analyze-stream` (`{text}`) and
  `POST /api/analyze-file-stream` (multipart file). The existing non-streaming
  `/api/analyze` + `/api/analyze-text` stay (back-compat + tests).

## 4. Frontend

- **Streaming client** (`api.js`): `analyzeTextStream(text, onProgress)` and
  `analyzeFileStream(file, onProgress)` — POST, read `response.body` with a stream reader,
  parse SSE frames, call `onProgress({type:'stages'|'progress', ...})`, resolve with the
  final `result` (throw on `error`).
- **App.jsx**: a `progress` state `{stages, completed, current}`; `onPick`/`onAnalyzeText`
  use the streaming clients and update progress; reset at start.
- **Loading view**: title ("Reviewing <name>…"), a **progress bar** (`completed/total`), and a
  **stage checklist**: done = ✓, current = spinning, pending = dot. "Tense/Narrative" shows as
  "Tense". Falls back gracefully if no stages arrive yet (plain spinner).

## 5. Out of scope

- The on-demand **originality** check keeps its own simple "Checking…" button state.
- No job persistence / cancellation (single in-flight review per session).

## 6. Testing

- Engine: `on_progress` is called with each stage name (5 specialists + `Overall`) when
  `include_facts=False`.
- Backend: `POST /api/analyze-stream` (mocked pipeline) returns a body containing
  `event: stages`, `event: result`, and the writing `param_order`; 422 on short text.
- Frontend: `npm run build` + manual smoke (checklist advances; bar fills; result shows).

## 7. Risks

- Thread + queue bridge: the worker thread must always enqueue a terminal marker (result OR
  error) so the generator ends — wrapped in try/finally.
- SSE through the Vite dev proxy works; in production ensure the proxy doesn't buffer the
  `text/event-stream` route (the `X-Accel-Buffering: no` header covers nginx).
