# Proofreader-Workflow Checks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Re-encode the tool's checks around the human proofreaders' flow — add a present-tense **Tense/Narrative** rule and a **Hooks** check, drop Style/Clarity — keeping Grammar/Spelling/Punctuation and the web-verified Facts path. Bake gold-standard excerpts from the corrected sample scripts into the new prompts.

**Architecture:** Category/prompt change only. The engine runs 5 writing specialists (Grammar, Spelling, Punctuation, Tense/Narrative, Hooks; indices 1–5) + Facts (index 6, skipped by the backend via `include_facts=False`) + aggregator (7) + preamble (8). The React UI derives pills/colors from the API's `param_order`/`param_colors`, so it adapts automatically.

**Tech Stack:** Python, FastAPI, Gemini on Vertex (google-genai for facts), pytest, React (no logic change).

## Global Constraints

- Categories + engine index: `1=Grammar, 2=Spelling, 3=Punctuation, 4=Tense/Narrative, 5=Hooks, 6=Facts`. Aggregator prompt = `7.yaml`, shared preamble = `8.yaml`.
- `PARAM_ORDER` (display/proofreader order) = `["Tense/Narrative", "Hooks", "Grammar", "Spelling", "Punctuation", "Facts"]`.
- `PARAM_COLORS` (5 writing cats): Tense/Narrative `#a78bfa`, Hooks `#14b8a6`, Grammar `#ff6b6b`, Spelling `#6b8cff`, Punctuation `#eab308`.
- `include_facts=False` (backend) runs writing specialists 1–5 and skips Facts (6).
- AOI schema unchanged: `{quote_verbatim, issue, fix, why_this_helps}`, verbatim ≤240 chars, between `BEGIN_JSON`/`END_JSON`. **Use straight ASCII quotes only in prompt JSON examples** (curly quotes break parsing).
- Tense rule: main-timeline narration = PRESENT; PAST only for genuinely prior events; flag both directions.

---

## Task 1: Rewrite the prompt set (Tense + Hooks; renumber)

**Files:**
- Modify/create/move under `prompts/`
- Test: `tests/test_prompts.py`

**Interfaces:** Produces prompts `1=Grammar … 5=Hooks` (each with `{script}`), `6=Facts` (`{script}`), `7=Aggregator` (`{evidence_json}`+`{script}`), `8=Preamble`. No `9.yaml`.

- [ ] **Step 1: Update the test first**

Replace `tests/test_prompts.py` contents with:
```python
import os

PROMPTS = "prompts"

def _content(n):
    with open(os.path.join(PROMPTS, f"{n}.yaml"), encoding="utf-8") as f:
        return f.read()

def test_specialist_prompts_have_script_placeholder():
    for n in (1, 2, 3, 4, 5, 6):
        assert "{script}" in _content(n), f"prompt {n} missing {{script}}"

def test_aggregator_has_placeholders():
    c = _content(7)
    assert "{evidence_json}" in c and "{script}" in c

def test_preamble_exists():
    assert os.path.exists(os.path.join(PROMPTS, "8.yaml"))

def test_no_stale_prompt_nine():
    assert not os.path.exists(os.path.join(PROMPTS, "9.yaml"))

def test_no_curly_quotes_in_prompts():
    for n in (1, 2, 3, 4, 5, 6):
        t = _content(n)
        assert "“" not in t and "”" not in t, f"prompt {n} has curly quotes"
```

- [ ] **Step 2: Run it, expect failure**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: FAIL (Facts is at 5, aggregator at 6, preamble at 7 currently).

- [ ] **Step 3: Renumber the existing prompts (in this order)**

Run:
```bash
git mv prompts/7.yaml prompts/8.yaml   # preamble 7 -> 8
git mv prompts/6.yaml prompts/7.yaml   # aggregator 6 -> 7
git mv prompts/5.yaml prompts/6.yaml   # facts 5 -> 6
```
Now `prompts/4.yaml` is still the old Style prompt and `prompts/5.yaml` no longer exists.

- [ ] **Step 4: Overwrite `prompts/4.yaml` with the Tense/Narrative prompt**

Write `prompts/4.yaml` (exact content; straight quotes only):
```yaml
content: |
    You are a narrative-tense editor for Mysterious 7 true-crime voiceover scripts.
    Evaluate ONLY narrative tense consistency. Ignore spelling, punctuation, hooks, grammar, and facts.

    THE RULE
    - The MAIN STORY TIMELINE is narrated in PRESENT tense for immediacy
      (e.g. "officers arrive", "she identifies the baby", "the body is pulled from the tub").
    - PAST tense is correct ONLY for events that happened BEFORE the main timeline -
      prior incidents, backstory, flashbacks
      (e.g. "Rhonda had picked up the baby at 8 a.m. and took her to the house").
    - Enforce BOTH directions:
      * Main-timeline narration written in PAST  -> flag; fix = rewrite in PRESENT.
      * A genuinely PRIOR event written in PRESENT -> flag; fix = rewrite in PAST.
    - Do NOT flag correct present (main timeline) or correct past (prior events).
    - Spoken dialogue inside quotation marks keeps its own tense - do not change quoted speech.

    GOLD-STANDARD EXAMPLES (correct - do NOT flag)
    - Present main timeline: "On April 19, 2024, officers arrive at Macclenny, Florida after receiving desperate calls."
    - Present main timeline: "She identifies her baby as Ariya Paige."
    - Present main timeline: "It all begins on May 1, 2019, when the Alvin Police Department receives a frantic call."
    - Past prior event:      "Babysitter Rhonda Jewell had picked up the 10-month-old around 8:00 a.m. and took her to residence."

    EXAMPLE FLAG
    - "Officers arrived and found the baby unconscious."  (main timeline in past)
      fix: "Officers arrive and find the baby unconscious."

    For each genuine tense error add an Area of Improvement:
      - quote_verbatim - the exact sentence/clause, <=240 chars, copied verbatim.
      - issue - which tense is wrong and why (main-timeline-should-be-present, or prior-event-should-be-past).
      - fix - the corrected sentence in the right tense.
      - why_this_helps - one short clause.

    Give a 1-10 score: 10 = tense consistent throughout, 1 = pervasive tense drift.
    No tense errors -> empty areas_of_improvement.

    HARD RULES
    - Never invent text. quote_verbatim must appear verbatim in the document.
    - Output must follow the JSON schema exactly, between the markers.

    Document:
    {script}

    Output (JSON ONLY between markers):
    BEGIN_JSON
    {
      "parameter_id": "tense",
      "score": 9,
      "explanation_bullets": ["Brief note on tense consistency."],
      "weakness": "Most impactful tense issue, or 'Not present'.",
      "suggestions": ["Optional fixes if score < 8."],
      "areas_of_improvement": [
        {"quote_verbatim": "Officers arrived and found the baby unconscious",
         "issue": "Main-timeline narration in past tense; should be present.",
         "fix": "Officers arrive and find the baby unconscious",
         "why_this_helps": "Present tense keeps the story immediate."}
      ],
      "summary": "One-line tense summary."
    }
    END_JSON
```

- [ ] **Step 5: Create `prompts/5.yaml` with the Hooks prompt**

Write `prompts/5.yaml` (exact content; straight quotes only):
```yaml
content: |
    You are an engagement editor for Mysterious 7 true-crime voiceover scripts.
    Evaluate ONLY hooks: the opening hook and the mini-cliffhangers between sections.
    Ignore tense, spelling, punctuation, grammar, and facts.

    WHAT TO CHECK
    - INTRO HOOK: does the opening tease the mystery and pose an unanswered question that
      makes the viewer need to keep watching?
    - MINI-CLIFFHANGERS: does each section end on a line that pulls the viewer forward
      (a teased reveal, a question, a "what happens next")? Flag flat section endings that
      only state facts with no forward pull.

    GOLD-STANDARD EXAMPLES (strong hooks)
    - Intro: "as the investigation unfolds, the suspicion begins to grow over whether the incident was truly an accident."
    - Intro: "everything takes a dark turn and the secrets that come out leave the officers stunned."
    - Mini-cliffhanger: "What they find next is truly gut-wrenching."
    - Mini-cliffhanger: "But the question remains: had she truly forgotten the child, or was it completely intentional?"
    - Mini-cliffhanger: "And just when the cops close in on their prime suspect, what he says flips the case."

    For each weak or missing hook add an Area of Improvement:
      - quote_verbatim - the exact flat line (or the opening line), <=240 chars, verbatim.
      - issue - why the hook is weak/missing (e.g. "section ends on a flat fact, no forward pull").
      - fix - a concrete stronger hook/cliffhanger rewrite in the channel's voice.
      - why_this_helps - one short clause on retention.

    Give a 1-10 score: 10 = strong intro hook and consistent cliffhangers, 1 = no hooks.
    No weak hooks -> empty areas_of_improvement.

    HARD RULES
    - Never invent text. quote_verbatim must appear verbatim in the document.
    - Output must follow the JSON schema exactly, between the markers.

    Document:
    {script}

    Output (JSON ONLY between markers):
    BEGIN_JSON
    {
      "parameter_id": "hooks",
      "score": 8,
      "explanation_bullets": ["Brief note on the intro hook and cliffhangers."],
      "weakness": "Weakest hook moment, or 'Not present'.",
      "suggestions": ["Optional fixes if score < 8."],
      "areas_of_improvement": [
        {"quote_verbatim": "The officers then went home for the day.",
         "issue": "Section ends on a flat fact with no forward pull.",
         "fix": "But what the officers discover the next morning changes everything.",
         "why_this_helps": "A forward-looking cliffhanger keeps viewers watching."}
      ],
      "summary": "One-line hooks summary."
    }
    END_JSON
```

- [ ] **Step 6: Tweak the aggregator weighting (`prompts/7.yaml`)**

In `prompts/7.yaml`, find the `overall_rating` instruction line that weighs categories
(it mentions "grammar, spelling, punctuation highest; style and facts next") and replace
that parenthetical with: `(for these VO scripts weigh tense/narrative consistency and hooks highest, then grammar, spelling, and punctuation; facts are reported separately)`. Leave the rest of the aggregator (including the `corrected_text` instruction) unchanged. If the exact wording differs, just ensure the weighting line no longer says "style" and mentions tense/hooks.

- [ ] **Step 7: Run the test, expect pass**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: PASS (5 tests).

- [ ] **Step 8: Commit**

```bash
git add prompts tests/test_prompts.py
git commit -m "feat: prompts for Tense/Narrative + Hooks (proofreader workflow); renumber"
```

---

## Task 2: Wire the new category set (engine, utils1, matching) + update tests

**Files:**
- Modify: `review_engine_multi.py`, `utils1.py`, `backend/matching.py`
- Test: `tests/test_utils1.py`, `tests/test_engine.py`, `tests/test_engine_include_facts.py`, `tests/test_matching.py`, `tests/test_backend_api.py`

**Interfaces:**
- `utils1.PARAM_ORDER == ["Tense/Narrative","Hooks","Grammar","Spelling","Punctuation","Facts"]`.
- `review_engine_multi.DISPLAY_BY_INDEX == {1:"Grammar",2:"Spelling",3:"Punctuation",4:"Tense/Narrative",5:"Hooks",6:"Facts"}`; specialist loop `last_specialist = 6 if include_facts else 5`; aggregator prompt loaded from index 7; preamble from index 8.
- `backend/matching.PARAM_COLORS` keys = the 5 writing categories.

- [ ] **Step 1: Update the unit tests first**

In `tests/test_utils1.py`, change the PARAM_ORDER assertion to:
```python
    assert utils1.PARAM_ORDER == [
        "Tense/Narrative", "Hooks", "Grammar", "Spelling", "Punctuation", "Facts",
    ]
```

In `tests/test_matching.py`, change the colors assertion to:
```python
def test_colors_are_writing_categories():
    assert set(matching.PARAM_COLORS.keys()) == {
        "Grammar", "Spelling", "Punctuation", "Tense/Narrative", "Hooks"}
```

In `tests/test_engine_include_facts.py`, update the specialist sequence and expectation
so the 5 writing categories run when `include_facts=False`:
- change the `seq` list to `[_specialist_json(p, 8) for p in ("grammar","spelling","punctuation","tense","hooks")]`
- change the prompt-load fake to treat index 7 as the aggregator:
  `monkeypatch.setattr(eng, "_load_prompt", lambda prefix, n: ("{evidence_json} {script}" if n == 7 else "{script}"))`
- change the final assertion to:
  `assert set(data["scores"].keys()) == {"Grammar","Spelling","Punctuation","Tense/Narrative","Hooks"}`
  and `assert "Facts" not in data["per_parameter"]`

In `tests/test_engine.py` (the default-path test), update so the default `include_facts=True`
builds the 6-category payload:
- `seq = [_specialist_json(p, 8) for p in ("grammar","spelling","punctuation","tense","hooks")]` (5 llm specialists; Facts comes from `grounded_generate`)
- keep `monkeypatch.setattr(eng, "grounded_generate", lambda prompt, temperature=0.0: _specialist_json("facts", 9))`
- prompt-load fake: aggregator at index 7 → `lambda prefix, n: ("{evidence_json} {script}" if n == 7 else "{script}")`
- final assertion:
  `assert set(data["scores"].keys()) == {"Grammar","Spelling","Punctuation","Tense/Narrative","Hooks","Facts"}`
  and `assert data["scores"]["Facts"] == 9` and `assert data["overall_rating"] == 7` and `assert data["corrected_text"] == "Corrected body."`

In `tests/test_backend_api.py`, in `_load_app`, change the stubbed review JSON `scores`
to the 5 writing categories and update the assertion:
- `"scores": {"Tense/Narrative": 8, "Hooks": 7, "Grammar": 8, "Spelling": 9, "Punctuation": 7}`
- assertion: `assert set(j["param_order"]) == {"Tense/Narrative","Hooks","Grammar","Spelling","Punctuation"}`
- (leave the `per_parameter` Grammar AOI and the span/Grammar checks as-is.)

- [ ] **Step 2: Run the tests, expect failures**

Run: `python -m pytest tests/test_utils1.py tests/test_matching.py tests/test_engine.py tests/test_engine_include_facts.py tests/test_backend_api.py -v`
Expected: FAIL (old category names/indices still in code).

- [ ] **Step 3: Update `utils1.PARAM_ORDER`**

In `utils1.py`:
```python
PARAM_ORDER: List[str] = [
    "Tense/Narrative",
    "Hooks",
    "Grammar",
    "Spelling",
    "Punctuation",
    "Facts",
]
```

- [ ] **Step 4: Update `review_engine_multi.py`**

Replace `DISPLAY_BY_INDEX` with:
```python
DISPLAY_BY_INDEX = {
    1: "Grammar",
    2: "Spelling",
    3: "Punctuation",
    4: "Tense/Narrative",
    5: "Hooks",
    6: "Facts",
    # 7 = aggregator, 8 = shared preamble
}
```
Change the specialist loop bound to:
```python
    last_specialist = 6 if include_facts else 5
    for i in range(1, last_specialist + 1):
```
Change the preamble load from index 7 to 8:
```python
        global_preamble = _load_prompt(prompts_dir, 8).strip()
```
Change the aggregator template load from index 6 to 7:
```python
    tmpl_agg = _load_prompt(prompts_dir, 7)
```
(Use the existing variable name for the aggregator template — only the index `6`→`7` changes. Keep the `_inject(..., evidence_json=..., script=...)` and the rest of the aggregator block unchanged.)

- [ ] **Step 5: Update `backend/matching.py` `PARAM_COLORS`**

```python
PARAM_COLORS: Dict[str, str] = {
    "Tense/Narrative": "#a78bfa",
    "Hooks":           "#14b8a6",
    "Grammar":         "#ff6b6b",
    "Spelling":        "#6b8cff",
    "Punctuation":     "#eab308",
}
```

- [ ] **Step 6: Run the updated tests, expect pass**

Run: `python -m pytest tests/test_utils1.py tests/test_matching.py tests/test_engine.py tests/test_engine_include_facts.py tests/test_backend_api.py -v`
Expected: PASS.

- [ ] **Step 7: Full suite**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add review_engine_multi.py utils1.py backend/matching.py tests/
git commit -m "feat: wire Tense/Narrative + Hooks categories (engine/utils1/matching + tests)"
```

---

## Task 3: Frontend copy + live verification + docs

**Files:**
- Modify: `frontend/src/App.jsx`, `README.md`

- [ ] **Step 1: Update loading copy in `App.jsx`**

Find the loading-screen line that lists the checks (currently "grammar, spelling,
punctuation & facts" or similar) and change it to read "tense, hooks, grammar, spelling,
punctuation & facts". No other frontend change is needed (pills/colors derive from
`param_order`/`param_colors`).

- [ ] **Step 2: Build the frontend**

Run: `cd /d/Grammerly/frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Live end-to-end (controller runs this; needs Vertex creds)**

Start the backend (`cd backend && uvicorn main:app --port 8013`, with PROMPTS_DIR pointing
at the repo `prompts/` by default). POST to `/api/analyze-text` a short VO script that
contains: (a) a correct present-tense main-timeline sentence, (b) a deliberate past-tense
main-timeline sentence ("Officers arrived and found the baby"), (c) a correct prior-event
past sentence ("Earlier that morning she had dropped the baby at daycare"), (d) a flat
section ending, and (e) a wrong fact. Confirm:
- `param_order` = the 5 writing categories in proofreader order.
- Tense/Narrative flags (b) and NOT (c).
- Hooks flags (d).
- Facts flags (e) with a correction.
Record the result.

- [ ] **Step 4: Update README**

In `README.md`, update the category description to the proofreader set (Tense/Narrative,
Hooks, Grammar, Spelling, Punctuation, + web-verified Facts), and note the present-tense
narrative rule (present for the main timeline, past only for prior events). Update the
manual-verification example to include the tense + hooks checks.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx README.md
git commit -m "feat: proofreader-workflow copy + docs (tense/hooks)"
```

---

## Self-Review Notes

- Coverage: Tense prompt (T1) ✓; Hooks prompt (T1) ✓; drop Style + renumber (T1) ✓;
  engine indices + include_facts bound (T2) ✓; PARAM_ORDER/COLORS (T2) ✓; all category
  tests updated (T2) ✓; frontend copy + live verify + docs (T3) ✓.
- Consistency: DISPLAY_BY_INDEX names (T2) == prompt categories (T1) == PARAM_ORDER names
  (T2) == PARAM_COLORS keys + Facts (T2). Aggregator at 7, preamble at 8 in both the
  prompt files (T1) and the engine loader indices (T2).
- Curly-quote guard re-applied in the prompt test (T1) so the new prompts stay parseable.
