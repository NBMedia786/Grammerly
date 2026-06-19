# Proofreader-Workflow Checks — Design

**Date:** 2026-06-19
**Status:** Approved — proceed to plan + implementation
**Builds on:** the React Writing Assistant (2026-06-19-react-writing-assistant-design.md).
Only the *checks* (categories + prompts) change; the app architecture is unchanged.

## 1. Goal

Make the tool check scripts the way the human proofreaders do, in their order:
**story/tense → hooks → facts**, plus baseline grammar/spelling/punctuation. The
signature addition is a **present-tense narrative rule** specific to the channel's
true-crime VO style, taught from the corrected sample scripts.

## 2. Category set (6)

The engine runs 5 writing categories; Facts stays on the web-verified `factcheck.py`
path. **Style/Clarity is removed.**

| Category | Engine index | Checks |
|---|---|---|
| Grammar | 1 | subject-verb, tense agreement, articles, prepositions, fragments/run-ons |
| Spelling | 2 | misspellings/typos |
| Punctuation | 3 | commas, apostrophes, quotes, splices |
| **Tense/Narrative** | 4 | the present-tense rule (Section 3) |
| **Hooks** | 5 | intro hook + mini-cliffhangers (Section 4) |
| Facts | 6 (engine, skipped by backend) | names/dates/places/ages/times via `factcheck.py` |

Display order (PARAM_ORDER, proofreader order): **Tense/Narrative, Hooks, Grammar,
Spelling, Punctuation, Facts**. Backend `param_order` = that list minus `Facts`.

Colors (`PARAM_COLORS`): Tense/Narrative `#a78bfa`, Hooks `#14b8a6`, Grammar `#ff6b6b`,
Spelling `#6b8cff`, Punctuation `#eab308`. Fact verdict colors unchanged.

## 3. The Tense/Narrative rule (signature)

Main-timeline narration is written in **present tense** for immediacy. **Past tense is
correct only for events that happened before the main timeline** (prior incidents,
backstory, flashbacks). The check enforces this **both directions**:

- 🚩 Main-timeline narration written in **past** → flag; `fix` = present-tense rewrite.
- 🚩 A genuinely **prior** event written in **present** → flag; `fix` = past-tense rewrite.
- ✅ Do not flag correct present (main timeline) or correct past (prior events).

Baked-in few-shot excerpts (from the corrected samples):
- ✅ present (main timeline): "officers arrive at Macclenny, Florida after receiving
  desperate calls", "She identifies her baby as Ariya Paige", "the baby is swiftly
  shifted to hospital", "It all begins on May 1, 2019, when the Alvin Police Department
  receives a frantic call".
- ✅ past (allowed — prior event): "babysitter Rhonda Jewell **had picked up** the
  10-month-old around 8:00 a.m. and **took** her to residence … until 1:00 p.m. … Rhonda
  realized she **had forgotten** the 10-month-old".
- 🚩 example flag: "Officers arrived and found the baby unconscious" (main timeline in
  past) → fix "Officers arrive and find the baby unconscious".

Each flag uses the standard AOI schema `{quote_verbatim, issue, fix, why_this_helps}`.

## 4. The Hooks check

Evaluate engagement structure:
- **Intro hook** — does the opening tease the mystery / pose an unanswered question?
- **Mini-cliffhangers** — do sections end on a line that pulls the viewer forward?

Flag weak/missing hooks with a concrete stronger rewrite (AOI schema). Baked-in examples
of strong hooks from the samples:
- intro: "as the investigation unfolds, the suspicion begins to grow over whether the
  incident was truly an accident"; "everything takes a dark turn … the secrets that come
  out leave the officers stunned".
- mini-cliffhangers: "What they find next is truly gut-wrenching."; "had she truly
  forgotten the child, or was it completely intentional?"; "what he says flips the case".

## 5. Files changed

- `prompts/`: drop old Style prompt; write `4.yaml` (Tense/Narrative) and `5.yaml`
  (Hooks) with baked excerpts; move Facts → `6.yaml`, aggregator → `7.yaml`, preamble →
  `8.yaml`. Update aggregator wording to weigh tense/hooks. (Old `6.yaml`/`7.yaml`
  contents move; no `9.yaml`.)
- `review_engine_multi.py`: `DISPLAY_BY_INDEX` = the 6 categories above; specialist loop
  `last_specialist = 6 if include_facts else 5`; aggregator prompt index → 7; preamble
  index → 8.
- `utils1.py`: `PARAM_ORDER` = the new display order.
- `backend/matching.py`: `PARAM_COLORS` = the 5 writing-category colors.
- `factcheck.py`: minor prompt emphasis on person NAMES (already covers names/dates) —
  optional, no contract change.
- `frontend/src/App.jsx`: loading copy → "tense, hooks, grammar, spelling, punctuation &
  facts". Pills/colors auto-derive from `param_order`/`param_colors` — no other change.
- Tests updated for the new names: `tests/test_utils1.py`, `tests/test_prompts.py`,
  `tests/test_engine.py`, `tests/test_engine_include_facts.py`, `tests/test_matching.py`,
  `tests/test_backend_api.py`.

## 6. Unchanged

Backend API shape, history/storage, fact-check path, highlight/match engine, React
components (category-agnostic). `include_facts=False` still skips the engine's Facts pass;
facts come from `factcheck.py`.

## 7. Testing

- Unit tests assert the new category names/order across utils/engine/matching/backend.
- `prompts/4.yaml` (Tense) and `5.yaml` (Hooks) contain `{script}`; aggregator `7.yaml`
  contains `{evidence_json}` + `{script}`; no `9.yaml`.
- Live verification: run a sample VO script; confirm the Tense check flags a planted
  past-tense main-timeline sentence and does NOT flag a prior-event past sentence; Hooks
  flags a flat section ending; Facts still web-verifies names/dates.

## 8. Risks

- Tense distinction (main timeline vs prior event) is the hard call; mitigated by the
  baked few-shot excerpts. Tune the prompt if it over/under-flags during live testing.
- Category rename touches several tests; all must be updated together to stay green.
