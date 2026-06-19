# React + FastAPI Writing Assistant (sole UI) + VPS History — Design

**Date:** 2026-06-19
**Status:** Approved — proceed to plan + implementation
**Supersedes UI of:** 2026-06-19-writing-assistant-design.md (Streamlit). The shared
engine/prompts/utils from that spec are reused; the Streamlit UI is removed.

## 1. Goal

Replace the Streamlit UI with the repo's existing **React (Vite) + FastAPI** stack as the
**single** UI for the Writing Assistant, rewired to the new 5-category engine, with a
richer web-grounded fact-check, a paste-text option, and a **VPS-disk review history**
(50 GB quota, usage progress bar, permanent delete).

## 2. Scope decisions (locked)

- **One UI only.** Delete the Streamlit app `app_grammarly_ui.py`; remove `streamlit` from
  requirements. Shared modules stay: `utils1.py`, `review_engine_multi.py`, `prompts/`,
  `facts_grounding.py`.
- **Fact-check via `factcheck.py`** (rich: verdict + sources + per-claim Apply). The engine's
  own "Facts" category is NOT used by the API (avoids a duplicate grounded pass).
- **History on VPS local disk** (not S3), JSON-per-review, 50 GB quota, block-new-saves when
  full, permanent delete.
- **Paste tab included** (parity with the removed Streamlit paste tab).
- **No `corrected_text` panel** — the React app builds the edited script from Apply/Dismiss
  decisions (`buildEditedText`), which is the better inline UX.
- **No auth / multi-user** — single shared history store on the VPS.

## 3. Architecture

```
React SPA (Vite, :5173)
   │  POST /api/analyze (file)         GET /api/history
   │  POST /api/analyze-text (text)    GET /api/history/{id}
   │  GET  /api/storage                DELETE /api/history/{id}
   ▼
FastAPI (backend/main.py, :8000)
   ├─ utils1.load_script_file / extract_review_json / PARAM_ORDER
   ├─ review_engine_multi.run_review_multi(..., include_facts=False)   # 4 writing cats + aggregator
   ├─ backend/matching.py   build_spans_by_param / locate_quote        # quote -> char spans
   ├─ factcheck.py          run_fact_check                             # google-genai + google_search
   └─ backend/history.py    save/list/load/delete/storage_usage        # VPS-disk history (NEW)
```

## 4. Engine change

`review_engine_multi.run_review_multi` gains `include_facts: bool = True`. When `False`,
the specialist loop runs indices 1–4 only (Grammar, Spelling, Punctuation, Style/Clarity);
the aggregator runs over those 4. Default `True` keeps existing tests/behaviour. The API
calls it with `include_facts=False`.

## 5. Fact-check fix (`factcheck.py`)

Migrate grounding to the working SDK (same fix already applied to `facts_grounding.py`):
- `_grounded_text` → `google-genai` `Client(vertexai=True, ...)` with
  `types.Tool(google_search=types.GoogleSearch())` (the deprecated `google_search_retrieval`
  is rejected by gemini-2.5).
- Fallback `_plain_text` → `google-genai` without tools (drop the langchain/torch path).
- Output contract unchanged: `{web_grounded: bool, claims: [{quote_verbatim, claim, verdict,
  correction, explanation, sources}]}`.

## 6. Span matcher (`backend/matching.py`)

- Replace the 7-viral `PARAM_COLORS` with 4 writing-category colors:
  Grammar `#ff6b6b`, Spelling `#6b8cff`, Punctuation `#eab308`, Style/Clarity `#a78bfa`.
- Relax heading suppression (same as the Streamlit fix): in `build_spans_by_param` stop
  calling `_is_heading_like` / `_overlaps_any(heading_ranges)` / `_is_heading_context`; in
  `locate_quote` drop the `_is_heading_like` gate. Keep the helper defs.

## 7. Backend API (`backend/main.py`)

- Response drops `drop_off_risks` / `viral_quotient`; adds `summary`. `param_order` /
  `param_colors` reflect the 4 writing categories; the Fact Check pill/colors stay as today.
- `POST /api/analyze` (file upload) and new `POST /api/analyze-text` (`{ "text": "..." }`)
  run the same pipeline (text path skips file parsing; min length 50 enforced).
- Both auto-save the result to history (Section 8). If save is blocked (storage full), the
  response still returns the analysis plus `"saved": false, "save_error": "storage_full"`.
- History endpoints:
  - `GET /api/history` → `[{ id, title, created_at, overall_rating, size_bytes }]` newest first.
  - `GET /api/history/{id}` → the full saved payload (re-render).
  - `DELETE /api/history/{id}` → permanent `os.remove`; returns updated storage usage.
  - `GET /api/storage` → `{ used_bytes, quota_bytes, percent, count }`.

## 8. History store (`backend/history.py`, NEW)

- Config: `HISTORY_DIR` (env, default `Scriptmodel/outputs/_history`),
  `HISTORY_QUOTA_GB` (env, default `50`).
- File per review: `{iso_ts}__{uuid}.json` containing the full analysis payload plus
  `{ id, title, created_at, overall_rating }`.
- `storage_usage()` sums file sizes under `HISTORY_DIR` → `{ used_bytes, quota_bytes, percent, count }`.
- `save_review(payload, title)`: if `used_bytes >= quota_bytes`, return `{saved: False,
  reason: "storage_full"}` WITHOUT writing. Else write the JSON, return `{saved: True, id}`.
- `list_reviews()`: parse each file's metadata; sort by `created_at` desc.
- `load_review(id)`: return the stored payload, or None.
- `delete_review(id)`: permanent `os.remove`; return updated usage. Path is validated to be
  inside `HISTORY_DIR` (no traversal).

## 9. Frontend (`frontend/`)

- Rebrand "Viral Script Reviewer" → "Writing Assistant"; fix copy ("7 storytelling
  parameters / 8 passes" → "grammar, spelling, punctuation & style + web-checked facts").
- `ScorePanel` shows `summary` + scores; remove `drop_off_risks` / `viral_quotient`.
- Category filter pills already derive from `param_order` — adapt automatically.
- **Paste tab** on the upload screen: textarea + "Analyze text" → `POST /api/analyze-text`.
- **History view** (new screen, reachable from the header): list of saved reviews
  (title · date · overall), click to open (loads payload → review screen), each row has a
  **Delete** button (confirm → `DELETE /api/history/{id}`).
- **Storage progress bar** (new component): "X.X GB of 50 GB (NN%)" from `GET /api/storage`;
  refreshes after each save and delete; bar turns red ≥ 90%.
- **Storage-full banner**: when an analysis returns `saved:false`, show
  "History full (50 GB) — delete old reviews to save new ones."

## 10. Docs

Fold `README_REACT.md` into `README.md` as the single source: backend + frontend run steps,
env vars (Vertex + `HISTORY_DIR` / `HISTORY_QUOTA_GB`), the history/storage feature.

## 11. Testing

- `backend/history.py` unit tests (pytest, temp dir): save/list/load/delete round-trip;
  quota enforcement (save blocked at/over quota); `storage_usage` math; delete is permanent
  and path-safe.
- `factcheck.py`: structural test that `_grounded_text`/`_plain_text` exist and
  `run_fact_check` returns the documented shape (network mocked).
- Engine `include_facts=False`: a test asserting only the 4 writing categories run.
- Frontend: manual smoke (upload, paste, filters, apply/dismiss, history open/delete,
  storage bar) documented in README; live Vertex env required.

## 12. Risks

- Live fact-check grounding depends on the `google-genai` migration (already proven working
  for `facts_grounding`). Same code path, so low risk.
- `frontend` files reference old fields (`ScorePanel`); must be read and updated precisely.
- Quota math must use a consistent byte base (1 GB = 1024^3) shared by backend + UI label.
