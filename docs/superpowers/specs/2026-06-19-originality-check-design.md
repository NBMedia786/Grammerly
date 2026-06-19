# Originality Check (Plagiarism + AI detection) — Design

**Date:** 2026-06-19
**Status:** Approved — proceed to plan + implementation
**Builds on:** the React Writing Assistant.

## 1. Goal

Add an **on-demand "Check originality"** action that flags (a) passages appearing
verbatim on the web (best-effort plagiarism) and (b) a rough AI-likelihood estimate.
Both are **best-effort indicators, not verdicts**, and the UI says so plainly.

## 2. Scope decisions (locked)

- **Free best-effort** (no paid detector). Pluggable later behind the same panel.
- **On-demand**, not part of every review — a button on the review screen runs it, so
  normal reviews stay fast.
- **Plagiarism** = Google-Search-grounded verbatim matches with source URLs (reuses the
  working `facts_grounding` grounded path). Not a true overlap %, won't catch paraphrase.
- **AI detection** = one ungrounded Gemini pass returning a 0–100 likelihood + band +
  reasoning, labeled "rough estimate, not reliable."

## 3. Backend modules

### `facts_grounding.py` (extend)
Add `ungrounded_generate(prompt, temperature=0.0) -> str` (public wrapper over the existing
`_ungrounded_call`) so AI detection can reuse the proven google-genai path.

### `plagiarism.py` (new, repo root, like `factcheck.py`)
- `run_plagiarism_check(text) -> {"web_grounded": bool, "matches": [...], "count": int}`.
- One grounded call via `facts_grounding.grounded_generate`. Prompt: find passages in the
  SCRIPT that appear verbatim/near-verbatim on the web; return JSON
  `{matches:[{quote_verbatim, sources:[url...], note}]}`. `quote_verbatim` must be an exact
  substring; `sources` ≤ 3. Parse via `utils1.extract_review_json`. `_normalize` filters
  empty/invalid and dedupes.

### `ai_detect.py` (new, repo root)
- `run_ai_detection(text) -> {"likelihood": int(0-100), "band": "low|medium|high", "reasoning": str}`.
- One ungrounded call via `facts_grounding.ungrounded_generate`. Prompt: estimate the
  probability the text was AI-generated, with brief reasoning; output JSON
  `{likelihood, band, reasoning}`. Clamp likelihood to 0–100; derive band if missing
  (<34 low, 34–66 medium, >66 high). Reasoning kept short.

## 4. Backend endpoint (`backend/main.py`)

`POST /api/originality` body `{ "text": "<script_text>" }` →
1. `run_ai_detection(text)` → `ai_detection`.
2. `run_plagiarism_check(text)` → matches.
3. Map each match's `quote_verbatim` to a character span in `text` via
   `matching.locate_quote` (same matcher as facts), build:
   - `spans`: `[{start,end,color:"#f97316",aid:"PLAG-i",param:"Plagiarism"}]` (matched only)
   - `aoi`: `{ "PLAG-i": {param:"Plagiarism", kind:"plagiarism", matched, line, issue:"Found on the web", sources:[...], why} }`
4. Response:
   ```json
   {
     "ai_detection": {"likelihood": 35, "band": "low", "reasoning": "...", "disclaimer": "Rough estimate — AI detectors are unreliable. Not a verdict."},
     "plagiarism": {"web_grounded": true, "count": 2},
     "spans": [ ... ],
     "aoi": { "PLAG-1": { ... } }
   }
   ```
- Min text length 50 → 422. Failures are surfaced cleanly (502) but never crash the app.
- This endpoint does NOT save to history (it augments an existing review in the UI).

## 5. Frontend

- **"Check originality" button** in the review header actions. While running, shows a
  spinner/disabled state.
- On success, **merge** the returned `spans` + `aoi` into the current `result`
  (so plagiarism passages highlight inline and appear as cards), add
  `param_colors["Plagiarism"] = "#f97316"`, and store `result.originality =
  {ai_detection, plagiarism}`.
- A **"Plagiarism" filter pill** appears automatically (counts derive from `aoi`).
- **OriginalityPanel** (new component) pinned at the top of the suggestion margin when
  `result.originality` exists:
  - **AI likelihood** meter (0–100 bar; band color: low green / medium amber / high red),
    the band label, the reasoning, and the bold disclaimer.
  - **Plagiarism** summary: "N passages matched online" + web-grounded note + a one-line
    caveat ("verbatim web matches only — verify manually; paraphrasing isn't detected").
- **Plagiarism cards** reuse the existing suggestion card: render the matched quote,
  "Found on the web", and **source links** (extend the card so sources show for
  `kind === 'plagiarism'` too, not just facts). No Apply button (no fix).

## 6. Colors

Plagiarism highlight/pill: `#f97316` (orange — distinct from the 5 categories + fact reds).
AI bands: low `#2e9e5b`, medium `#d9a400`, high `#e5484d`.

## 7. Testing

- `plagiarism.run_plagiarism_check`: structural test (seam exists; mocked grounded text →
  documented shape; empty → count 0).
- `ai_detect.run_ai_detection`: mocked output → clamped likelihood + derived band; bad JSON
  → safe default (`{likelihood:0, band:"low", reasoning:""}` or similar).
- `facts_grounding.ungrounded_generate`: exists and delegates to `_ungrounded_call`.
- Backend `POST /api/originality`: TestClient with mocked detectors → response shape, spans
  for matched plagiarism, 422 on short text.
- Frontend: `npm run build` + manual smoke (button → panel + inline highlights + cards).

## 8. Risks / honesty

- Plagiarism via search is approximate; label it best-effort, show sources, never a %.
- AI detection is unreliable; the disclaimer is mandatory and prominent.
- Extra latency on the originality call (grounded search is slow) — acceptable since it's
  explicitly user-triggered, with a loading state.
