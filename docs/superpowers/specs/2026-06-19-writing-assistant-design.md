# Writing Assistant (Grammar + Fact Checker) — Design

**Date:** 2026-06-19
**Status:** Approved (direction), pending implementation plan
**Author:** pair session

## 1. Goal

Pivot the existing "Viral Script Reviewer" Streamlit app into a Grammarly-style
**Writing Assistant** that checks a document for:

- **Grammar** — subject-verb agreement, tense, articles, prepositions, sentence structure
- **Spelling** — misspellings and typos
- **Punctuation** — commas, apostrophes, quotes, run-ons, missing terminal punctuation
- **Style / Clarity** — wordiness, passive voice, awkward phrasing, tone
- **Facts** — real-world factual accuracy (dates, names, events) verified via **web search**

The tool shows issues as a sidebar list grouped by category (with counts) AND as
inline highlights in the document with click-to-fix popups. It keeps a single
overall **1–10** quality rating and produces a downloadable **corrected version**
of the text shown side-by-side with the original.

## 2. Key insight — reuse the existing data contract

The current model output is shaped as:

```
per_parameter: { <param>: { score, areas_of_improvement: [ {quote_verbatim, issue, fix, why_this_helps} ], ... } }
scores: { <param>: int }
overall_rating: int
```

A grammar issue maps cleanly onto an "area of improvement":

| AOI field        | Grammar-checker meaning                        |
|------------------|------------------------------------------------|
| `quote_verbatim` | the exact wrong text in the document           |
| `issue`          | what is wrong ("subject-verb disagreement")    |
| `fix`            | the correction                                 |
| `why_this_helps` | short explanation                              |

Therefore the inline-highlight engine, click-to-fix popup, history/Recents, and
S3/storage layers are **reused unchanged**. Only the "brain" (prompts + engine)
and some labels/UI panels change.

## 3. Data contract changes

Keep the shape; change the keys and add two fields.

- `per_parameter` is keyed by the **5 categories**:
  `Grammar`, `Spelling`, `Punctuation`, `Style/Clarity`, `Facts`.
- Each category keeps `score` (1–10) and
  `areas_of_improvement: [{quote_verbatim, issue, fix, why_this_helps}]`.
  - For **Facts**, `why_this_helps` carries the verification note / source found.
- Top level:
  - `scores` — per-category 1–10 (kept)
  - `overall_rating` — 1–10 (kept)
  - `summary` — short overall note (**replaces** `viral_quotient`)
  - `corrected_text` — full cleaned version of the document (**new**)
- **Removed:** `viral_quotient`, `drop_off_risks`, and the 7 viral parameters.
- `strengths` / `weaknesses` / `suggestions` may be kept as general writing notes
  (optional; aggregator decides). Not required for MVP.

## 4. Engine (`review_engine_multi.py`)

- `DISPLAY_BY_INDEX` → the 5 categories (indexes 1–5).
- Main loop runs **5 specialists** (was 7).
- **Grammar / Spelling / Punctuation / Style** → standard Gemini calls, `temperature=0.0`.
- **Facts** → a **Google-Search-grounded** Gemini call so it can verify
  dates/events against the web. Implemented via `ChatVertexAI` with the Google
  Search grounding tool.
  - **Technical risk (validate first):** exact wiring of the grounding tool in
    `langchain-google-vertexai` for the installed version. A spike/smoke test must
    confirm a grounded call returns answers + citations before the rest is built.
    Fallback if grounding is unavailable: Facts specialist runs ungrounded on LLM
    knowledge and labels results as "unverified."
- **Aggregator** (last prompt) returns `overall_rating`, `summary`, and the full
  `corrected_text`. `corrected_text` is produced by the **model** (robust),
  not by programmatic span surgery (fragile with overlaps and fact rewrites).

## 5. Prompts (`prompts/`)

Replace all viral YAMLs. New numbering:

- `1.yaml` — Grammar specialist
- `2.yaml` — Spelling specialist
- `3.yaml` — Punctuation specialist
- `4.yaml` — Style/Clarity specialist
- `5.yaml` — Facts specialist (grounded; extract factual claims, verify, cite)
- `6.yaml` — Aggregator (overall 1–10 + summary + `corrected_text`)
- shared preamble prompt (global rules, JSON discipline) — kept, renumbered

Each specialist enforces the same `BEGIN_JSON … END_JSON` schema and the
`{quote_verbatim, issue, fix, why_this_helps}` AOI shape used today. Hard rules:
quotes are verbatim (≤240 chars), never invented; if none, return empty list.

## 6. UI (`app_grammarly_ui.py`)

- Title → **"Writing Assistant"**. `PARAM_COLORS` → 5 category colors.
- **Center column:** document with inline highlights + click-to-fix popups
  (engine unchanged).
- **Right column:** 5 category chips → issue list with **counts**
  (e.g. "Grammar 12 · Spelling 3 · Facts 2"); each issue clickable.
- **Left column:** per-category 1–10 scores + overall 1–10.
- **New "Corrected version" panel:** original vs. `corrected_text` side-by-side,
  with a **Download** button (download corrected `.txt`/`.docx`).
- **Relax heading suppression:** `_is_heading_like` / `_is_heading_context`
  currently drop highlights inside headings (a script-reviewer concern). For a
  grammar checker, errors in headings/titles SHOULD be caught — relax/remove this
  filtering.
- **Input:** keep upload (`.docx/.pdf/.txt`) and **re-add a "Paste text" tab**
  (natural Grammarly flow; old code already had it).

## 7. Dead-code deletion (explicit workstream)

Remove the large commented-out legacy blocks and viral-only helpers:

- `app_grammarly_ui.py` — commented legacy block (~lines 1–1206)
- `review_engine_multi.py` — commented legacy block (~lines 1–361)
- `utils1.py` — commented legacy block (~lines 1–570), plus viral-only helpers
  (`save_review_docx_claude_style_from_json`, viral fields in
  `normalize_review_payload`)

## 8. Unchanged / reused as-is

- S3 (RunPod) + local history / Recents layer
- DOCX parsing, table flattening, heading-offset metadata
- Span-matching engine (`find_span_smart` and helpers)
- Inline `<mark>` HTML renderer + the JS click-to-fix popup
- JSON extraction helpers (`extract_review_json`)

## 9. Out of scope (YAGNI)

- Per-issue "Apply" buttons that mutate the document in place (we show a whole
  corrected version instead).
- Real-time/as-you-type checking.
- Multi-language grammar (assume English for MVP).
- User accounts / per-user settings.

## 10. Risks & mitigations

1. **Grounding tool wiring** — validate with a smoke test first; ungrounded
   fallback labeled "unverified."
2. **Fact-check latency/cost** — grounded calls are slower; acceptable for a
   one-shot review. Could batch claims into one grounded call.
3. **Highlight matching for tiny quotes** (single misspelled word) — existing
   matcher handles short exact substrings well; relaxing heading suppression
   avoids false drops.
4. **Not a git repo** — design doc is saved but not committed (no `git init`
   unless requested).
