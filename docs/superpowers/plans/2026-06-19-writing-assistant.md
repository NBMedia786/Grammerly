# Writing Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the existing "Viral Script Reviewer" Streamlit app into a Grammarly-style Writing Assistant that flags Grammar, Spelling, Punctuation, Style/Clarity, and web-verified Facts, with inline highlights, a grouped issue list, a 1–10 rating, and a downloadable corrected version.

**Architecture:** Reuse the existing JSON data contract (`per_parameter` → `areas_of_improvement: [{quote_verbatim, issue, fix, why_this_helps}]`) so the highlight engine, popup, history, and storage layers are untouched. Replace the 7 viral "parameters" with 5 writing categories, rewrite the prompt YAMLs, run the Facts specialist on a Google-Search-grounded Gemini call, and have the aggregator emit a full `corrected_text`.

**Tech Stack:** Python, Streamlit, `langchain-google-vertexai` (Gemini on Vertex AI), `vertexai` SDK (for Google Search grounding), `python-docx`, `boto3` (RunPod S3), `pytest` (tests).

## Global Constraints

- Category set and display order (verbatim): `Grammar`, `Spelling`, `Punctuation`, `Style/Clarity`, `Facts`.
- Model JSON is wrapped in `BEGIN_JSON … END_JSON`; specialists return `{score, explanation_bullets|explanation, weakness, suggestions, areas_of_improvement, summary}`; each AOI is exactly `{quote_verbatim, issue, fix, why_this_helps}` with `quote_verbatim` ≤ 240 chars, verbatim from the document, never invented.
- Overall rating is an integer 1–10.
- LLM calls use `temperature=0.0`.
- Vertex config via env: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (default `us-central1`), `GOOGLE_APPLICATION_CREDENTIALS`; model from `GEMINI_MODEL` or default `gemini-2.5-flash`.
- Prompts dir / S3 prefix base is `Scriptmodel/` (`Scriptmodel/prompts`, `Scriptmodel/outputs`, `Scriptmodel/scripts`).
- English-only grammar for MVP. No per-issue apply, no realtime checking (YAGNI).

---

## File Structure

- `utils1.py` — shared helpers. Change `PARAM_ORDER` to 5 categories; trim viral fields from `normalize_review_payload`; delete commented legacy block + viral DOCX exporter. **Pure functions — unit tested.**
- `review_engine_multi.py` — orchestrates specialists + aggregator. Change `DISPLAY_BY_INDEX`, loop 1–5, add grounded Facts call, change aggregator schema (`overall_rating`, `summary`, `corrected_text`). Delete commented legacy block. **Parsing/aggregation unit tested with a mocked LLM.**
- `facts_grounding.py` *(new)* — small isolated module wrapping a Google-Search-grounded Gemini call. One responsibility: take a prompt, return grounded text. **Smoke-tested live; import-tested in CI.**
- `prompts/1.yaml`–`6.yaml` + `prompts/7.yaml` — rewritten prompt set (5 specialists, aggregator, preamble).
- `app_grammarly_ui.py` — Streamlit UI. New colors/title, paste tab, relaxed heading suppression, category counts, corrected-text side-by-side + download. Delete commented legacy block. **Manually smoke-tested.**
- `tests/` *(new)* — `test_utils1.py`, `test_engine.py`, `test_facts_grounding.py`.

---

## Task 0: Project scaffolding (git + pytest)

**Files:**
- Create: `requirements-dev.txt`, `tests/__init__.py`, `pytest.ini`

**Interfaces:**
- Produces: a runnable `pytest` setup; a git repo for per-task commits.

- [ ] **Step 1: Initialize git (folder is not yet a repo)**

Run:
```bash
cd /d/Grammerly
git init
printf '%s\n' '__pycache__/' '*.pyc' '.env' '.pytest_cache/' 'outputs/' 'Scriptmodel/outputs/' > .gitignore
git add .gitignore && git commit -m "chore: init repo"
```

- [ ] **Step 2: Add dev deps + pytest config**

Create `requirements-dev.txt`:
```
pytest>=8.0
```
Create `pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
```
Create empty `tests/__init__.py` (no content).

- [ ] **Step 3: Install and verify pytest runs**

Run:
```bash
pip install -r requirements-dev.txt
pytest -q
```
Expected: pytest runs and reports `no tests ran` (exit 5) — confirms discovery works.

- [ ] **Step 4: Commit**

```bash
git add requirements-dev.txt pytest.ini tests/__init__.py
git commit -m "chore: add pytest scaffolding"
```

---

## Task 1: Switch shared contract to 5 categories (`utils1.py`)

**Files:**
- Modify: `utils1.py` (delete commented block lines ~1–570; change `PARAM_ORDER`; trim `normalize_review_payload`; delete `save_review_docx_claude_style_from_json`)
- Test: `tests/test_utils1.py`

**Interfaces:**
- Produces:
  - `PARAM_ORDER: List[str] == ["Grammar","Spelling","Punctuation","Style/Clarity","Facts"]`
  - `normalize_review_payload(data: dict) -> dict` — normalizes AOIs to the 4-field schema per category, sanitizes text fields, leaves `corrected_text` untouched, and no longer references `viral_quotient` / `drop_off_risks`.
  - Unchanged exports still used by the UI: `extract_review_json`, `load_script_file`, `sanitize_editor_text`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_utils1.py`:
```python
import utils1


def test_param_order_is_five_writing_categories():
    assert utils1.PARAM_ORDER == [
        "Grammar", "Spelling", "Punctuation", "Style/Clarity", "Facts",
    ]


def test_normalize_keeps_corrected_text_verbatim():
    payload = {
        "corrected_text": "Line one.\n\n\nLine two.",  # triple newline preserved
        "summary": "  Two typos fixed.  ",
        "per_parameter": {
            "Grammar": {
                "score": 7,
                "areas_of_improvement": [
                    {"quote": "he go", "issue": "agreement",
                     "edit_suggestion": "he goes", "why": "subject-verb"},
                ],
            }
        },
    }
    out = utils1.normalize_review_payload(payload)
    # corrected_text must NOT be whitespace-collapsed or bullet-stripped
    assert out["corrected_text"] == "Line one.\n\n\nLine two."
    # legacy alias keys are mapped into the canonical AOI schema
    aoi = out["per_parameter"]["Grammar"]["areas_of_improvement"][0]
    assert aoi == {
        "quote_verbatim": "he go",
        "issue": "agreement",
        "fix": "he goes",
        "why_this_helps": "subject-verb",
    }
    # viral keys are not introduced
    assert "viral_quotient" not in out
    assert "drop_off_risks" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_utils1.py -v`
Expected: FAIL — `PARAM_ORDER` still lists viral params and `corrected_text` is absent from handling.

- [ ] **Step 3: Delete the commented legacy block**

In `utils1.py`, delete the leading commented-out block (everything from the top down to the line `# utils1.py — helpers shared by ...`, i.e. the old `# from __future__ ...` through the final `# doc.save(out_path)`), leaving the active `from __future__ import annotations` as the first code line.

- [ ] **Step 4: Replace `PARAM_ORDER`**

In `utils1.py` change the list to:
```python
PARAM_ORDER: List[str] = [
    "Grammar",
    "Spelling",
    "Punctuation",
    "Style/Clarity",
    "Facts",
]
```

- [ ] **Step 5: Trim `normalize_review_payload`**

Replace the body of `normalize_review_payload` so it no longer sanitizes `viral_quotient` and keeps `corrected_text` verbatim:
```python
def normalize_review_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return data

    # General writing notes (optional lists)
    for k in ("strengths", "weaknesses", "suggestions"):
        if isinstance(data.get(k), list):
            data[k] = [sanitize_editor_text(x) for x in data[k]]

    if isinstance(data.get("summary"), str):
        data["summary"] = sanitize_editor_text(data["summary"])

    # corrected_text is intentionally left verbatim (no sanitizing / no ws-collapse)

    per = data.get("per_parameter") or {}
    if isinstance(per, dict):
        for _, block in per.items():
            if not isinstance(block, dict):
                continue
            block["areas_of_improvement"] = _coerce_aois(block)
            for fld in ("explanation", "weakness", "suggestion", "summary"):
                if isinstance(block.get(fld), str):
                    block[fld] = sanitize_editor_text(block[fld])
            for a in block.get("areas_of_improvement") or []:
                if not isinstance(a, dict):
                    continue
                for fld in ("quote_verbatim", "issue", "fix", "why_this_helps"):
                    if isinstance(a.get(fld), str):
                        a[fld] = sanitize_editor_text(a[fld])
    return data
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_utils1.py -v`
Expected: PASS (both tests).

- [ ] **Step 7: Commit**

```bash
git add utils1.py tests/test_utils1.py
git commit -m "feat: switch shared contract to 5 writing categories"
```

---

## Task 2: Rewrite prompt set (`prompts/1.yaml`–`7.yaml`)

**Files:**
- Modify/replace: `prompts/1.yaml`, `prompts/2.yaml`, `prompts/3.yaml`, `prompts/4.yaml`, `prompts/5.yaml`, `prompts/6.yaml`, `prompts/7.yaml`
- Delete: `prompts/8.yaml`, `prompts/9.yaml`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Produces 7 prompt files. Numbering relied on by Task 4:
  `1`=Grammar, `2`=Spelling, `3`=Punctuation, `4`=Style/Clarity, `5`=Facts, `6`=Aggregator, `7`=shared preamble.
- Each specialist prompt contains the literal token `{script}`. Aggregator contains `{evidence_json}` and `{script}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_prompts.py`:
```python
import os, re

PROMPTS = "prompts"

def _content(n):
    with open(os.path.join(PROMPTS, f"{n}.yaml"), encoding="utf-8") as f:
        return f.read()

def test_specialist_prompts_have_script_placeholder():
    for n in (1, 2, 3, 4, 5):
        assert "{script}" in _content(n), f"prompt {n} missing {{script}}"

def test_aggregator_has_placeholders():
    c = _content(6)
    assert "{evidence_json}" in c and "{script}" in c

def test_preamble_exists():
    assert os.path.exists(os.path.join(PROMPTS, "7.yaml"))

def test_old_viral_prompts_removed():
    assert not os.path.exists(os.path.join(PROMPTS, "8.yaml"))
    assert not os.path.exists(os.path.join(PROMPTS, "9.yaml"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_prompts.py -v`
Expected: FAIL — current prompts are viral-themed and `8/9.yaml` still exist.

- [ ] **Step 3: Write `prompts/1.yaml` (Grammar)**

```yaml
content: |
    You are a meticulous English grammar checker.
    Evaluate ONLY **grammar** in the document below: subject-verb agreement, verb
    tense consistency, articles, prepositions, pronoun agreement, and sentence
    structure (fragments, run-ons). Do NOT comment on spelling, punctuation, style,
    or facts — other checkers handle those.

    For every genuine grammar error, add an Area of Improvement:
      - quote_verbatim — the exact erroneous text, ≤240 chars, copied verbatim.
      - issue — what is grammatically wrong, in plain words.
      - fix — the corrected text (Replace/Add/Cut).
      - why_this_helps — one short clause on the rule.

    Give a 1–10 score: 10 = flawless grammar, 1 = pervasive errors.
    If there are no grammar errors, return an empty areas_of_improvement list.

    HARD RULES:
    - Never invent text. quote_verbatim must appear verbatim in the document.
    - Output must follow the JSON schema exactly, between the markers.

    Document:
    {script}

    Output (JSON ONLY between markers):
    BEGIN_JSON
    {
      "parameter_id": "grammar",
      "score": 9,
      "explanation_bullets": ["Brief note on overall grammar quality."],
      "weakness": "Most impactful grammar weakness, or 'Not present'.",
      "suggestions": ["Optional concrete fixes if score < 8."],
      "areas_of_improvement": [
        {"quote_verbatim": "they was late", "issue": "Subject-verb disagreement.",
         "fix": "they were late", "why_this_helps": "Plural subject takes 'were'."}
      ],
      "summary": "One-line grammar summary."
    }
    END_JSON
```

- [ ] **Step 4: Write `prompts/2.yaml` (Spelling)**

```yaml
content: |
    You are a precise spelling checker for English.
    Evaluate ONLY **spelling**: misspelled words and typos. Ignore grammar,
    punctuation, style, and facts. Proper nouns spelled plausibly are not errors.

    For each misspelling add an Area of Improvement:
      - quote_verbatim — the exact misspelled word or short phrase, ≤240 chars.
      - issue — "Misspelling" (+ the intended word if useful).
      - fix — the correctly spelled word.
      - why_this_helps — one short clause.

    Give a 1–10 score: 10 = no typos, 1 = riddled with them.
    No misspellings → empty areas_of_improvement.

    HARD RULES:
    - Never invent text. quote_verbatim must appear verbatim in the document.
    - Output must follow the JSON schema exactly, between the markers.

    Document:
    {script}

    Output (JSON ONLY between markers):
    BEGIN_JSON
    {
      "parameter_id": "spelling",
      "score": 9,
      "explanation_bullets": ["Brief note on spelling quality."],
      "weakness": "Most impactful issue, or 'Not present'.",
      "suggestions": ["Optional."],
      "areas_of_improvement": [
        {"quote_verbatim": "recieve", "issue": "Misspelling of 'receive'.",
         "fix": "receive", "why_this_helps": "'i before e except after c'."}
      ],
      "summary": "One-line spelling summary."
    }
    END_JSON
```

- [ ] **Step 5: Write `prompts/3.yaml` (Punctuation)**

```yaml
content: |
    You are a punctuation checker for English.
    Evaluate ONLY **punctuation**: commas, periods, apostrophes, quotation marks,
    colons/semicolons, hyphens, and run-on/comma-splice sentences. Ignore grammar,
    spelling, style, and facts.

    For each punctuation error add an Area of Improvement with
    quote_verbatim / issue / fix / why_this_helps (same rules as other checkers).

    Give a 1–10 score. No errors → empty areas_of_improvement.

    HARD RULES:
    - Never invent text. quote_verbatim must appear verbatim in the document.
    - Output must follow the JSON schema exactly, between the markers.

    Document:
    {script}

    Output (JSON ONLY between markers):
    BEGIN_JSON
    {
      "parameter_id": "punctuation",
      "score": 9,
      "explanation_bullets": ["Brief note on punctuation."],
      "weakness": "Most impactful issue, or 'Not present'.",
      "suggestions": ["Optional."],
      "areas_of_improvement": [
        {"quote_verbatim": "Its a long day", "issue": "Missing apostrophe in contraction.",
         "fix": "It's a long day", "why_this_helps": "'It's' = 'it is'."}
      ],
      "summary": "One-line punctuation summary."
    }
    END_JSON
```

- [ ] **Step 6: Write `prompts/4.yaml` (Style/Clarity)**

```yaml
content: |
    You are an editor improving **style and clarity** in English prose.
    Evaluate ONLY style/clarity: wordiness, passive voice where active is clearer,
    awkward phrasing, redundancy, and unclear tone. Ignore grammar, spelling,
    punctuation, and facts. Do not rewrite for personal taste — flag only changes
    that clearly improve readability.

    For each issue add an Area of Improvement with
    quote_verbatim / issue / fix / why_this_helps.

    Give a 1–10 score. No issues → empty areas_of_improvement.

    HARD RULES:
    - Never invent text. quote_verbatim must appear verbatim in the document.
    - Output must follow the JSON schema exactly, between the markers.

    Document:
    {script}

    Output (JSON ONLY between markers):
    BEGIN_JSON
    {
      "parameter_id": "style",
      "score": 8,
      "explanation_bullets": ["Brief note on clarity."],
      "weakness": "Most impactful issue, or 'Not present'.",
      "suggestions": ["Optional."],
      "areas_of_improvement": [
        {"quote_verbatim": "due to the fact that", "issue": "Wordy phrase.",
         "fix": "because", "why_this_helps": "Tighter and clearer."}
      ],
      "summary": "One-line style summary."
    }
    END_JSON
```

- [ ] **Step 7: Write `prompts/5.yaml` (Facts — grounded)**

```yaml
content: |
    You are a fact-checker with access to Google Search results.
    Verify ONLY **factual claims** in the document: dates, named people, places,
    events, numbers, and definitions. Use the search results provided/grounding to
    confirm or refute each claim. Ignore grammar, spelling, punctuation, and style.

    For each claim that is FALSE or unverifiable-and-doubtful, add an Area of
    Improvement:
      - quote_verbatim — the exact claim text, ≤240 chars, verbatim.
      - issue — what is factually wrong (state the correct fact).
      - fix — the corrected claim text.
      - why_this_helps — cite the source/basis for the correction.

    Do NOT flag claims that are correct. If a claim cannot be verified, only flag it
    if it is specific and likely wrong; otherwise leave it.

    Give a 1–10 score: 10 = all checkable facts correct, 1 = many false claims.
    No false facts → empty areas_of_improvement.

    HARD RULES:
    - Never invent quotes. quote_verbatim must appear verbatim in the document.
    - Output must follow the JSON schema exactly, between the markers.

    Document:
    {script}

    Output (JSON ONLY between markers):
    BEGIN_JSON
    {
      "parameter_id": "facts",
      "score": 9,
      "explanation_bullets": ["Brief note on factual accuracy."],
      "weakness": "Most impactful false claim, or 'Not present'.",
      "suggestions": ["Optional."],
      "areas_of_improvement": [
        {"quote_verbatim": "World War II ended in 1946",
         "issue": "WWII ended in 1945, not 1946.",
         "fix": "World War II ended in 1945",
         "why_this_helps": "Japan surrendered Sept 2, 1945 (per multiple sources)."}
      ],
      "summary": "One-line factual-accuracy summary."
    }
    END_JSON
```

- [ ] **Step 8: Write `prompts/6.yaml` (Aggregator)**

```yaml
content: |
    You are the senior editor producing the final writing report.
    You are given per-category findings as JSON and the original document.

    Per-category evidence:
    {evidence_json}

    Original document:
    {script}

    Produce a final assessment:
    - overall_rating: integer 1–10 for overall writing quality (weigh grammar,
      spelling, punctuation highest; style and facts next).
    - strengths / weaknesses / suggestions: short bullet lists (plain English).
    - summary: 1–2 sentence overall note.
    - corrected_text: the FULL document rewritten with all grammar, spelling, and
      punctuation errors fixed and clearly-false facts corrected. Preserve the
      author's wording, paragraph breaks, and line breaks everywhere no change is
      needed. Do NOT add commentary — return only the corrected document text.

    Return the fields requested by the structured schema.
```

- [ ] **Step 9: Write `prompts/7.yaml` (shared preamble)**

```yaml
content: |
    Global rules for all checkers:
    - Be precise and conservative: only flag genuine errors.
    - quote_verbatim is copied EXACTLY from the document (≤240 chars). Never paraphrase it.
    - Output strictly valid JSON between BEGIN_JSON and END_JSON. No prose outside the markers.
    - If a category has no issues, return an empty areas_of_improvement list and a high score.
```

- [ ] **Step 10: Delete old viral prompts**

Run:
```bash
git rm prompts/8.yaml prompts/9.yaml
```

- [ ] **Step 11: Run test to verify it passes**

Run: `pytest tests/test_prompts.py -v`
Expected: PASS (all four tests).

- [ ] **Step 12: Commit**

```bash
git add prompts tests/test_prompts.py
git commit -m "feat: rewrite prompts for grammar/spelling/punctuation/style/facts"
```

---

## Task 3: Google-Search-grounded Facts call (`facts_grounding.py`)

**Files:**
- Create: `facts_grounding.py`
- Test: `tests/test_facts_grounding.py`

**Interfaces:**
- Produces: `grounded_generate(prompt: str, temperature: float = 0.0) -> str`
  — runs a Gemini call on Vertex with the Google Search grounding tool and returns
  the model's text. On any grounding/SDK error it falls back to an ungrounded
  Vertex call (so the pipeline never hard-fails on Facts).
- Consumes env: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GEMINI_MODEL`.

- [ ] **Step 1: Write the failing import/structure test**

Create `tests/test_facts_grounding.py`:
```python
import facts_grounding


def test_module_exposes_grounded_generate():
    assert hasattr(facts_grounding, "grounded_generate")


def test_falls_back_to_ungrounded_on_grounding_error(monkeypatch):
    calls = {"grounded": 0, "ungrounded": 0}

    def fake_grounded(prompt, temperature):
        calls["grounded"] += 1
        raise RuntimeError("grounding tool unavailable")

    def fake_ungrounded(prompt, temperature):
        calls["ungrounded"] += 1
        return "FALLBACK_TEXT"

    monkeypatch.setattr(facts_grounding, "_grounded_call", fake_grounded)
    monkeypatch.setattr(facts_grounding, "_ungrounded_call", fake_ungrounded)

    out = facts_grounding.grounded_generate("check this", temperature=0.0)
    assert out == "FALLBACK_TEXT"
    assert calls["grounded"] == 1 and calls["ungrounded"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_facts_grounding.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the module**

Create `facts_grounding.py`:
```python
"""Google-Search-grounded Gemini call on Vertex AI, with an ungrounded fallback.

Isolated here so the rest of the engine never imports Vertex grounding internals.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def _model_name() -> str:
    return os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"


def _project() -> str | None:
    return os.getenv("GOOGLE_CLOUD_PROJECT") or None


def _location() -> str:
    return os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"


def _grounded_call(prompt: str, temperature: float) -> str:
    """Vertex Gemini with Google Search grounding. Raises if the SDK path is unavailable."""
    import vertexai
    from vertexai.generative_models import GenerativeModel, Tool, grounding, GenerationConfig

    vertexai.init(project=_project(), location=_location())
    tool = Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())
    model = GenerativeModel(_model_name())
    resp = model.generate_content(
        prompt,
        tools=[tool],
        generation_config=GenerationConfig(temperature=temperature),
    )
    return getattr(resp, "text", "") or ""


def _ungrounded_call(prompt: str, temperature: float) -> str:
    """Plain Vertex Gemini via langchain (same path as other specialists)."""
    from langchain_google_vertexai import ChatVertexAI

    llm = ChatVertexAI(
        model=_model_name(),
        temperature=temperature,
        top_p=0.0,
        top_k=1,
        project=_project(),
        location=_location(),
    )
    resp = llm.invoke(prompt)
    return getattr(resp, "content", "") or ""


def grounded_generate(prompt: str, temperature: float = 0.0) -> str:
    """Try grounded; on any failure, fall back to ungrounded so Facts never blocks the run."""
    try:
        return _grounded_call(prompt, temperature)
    except Exception:
        return _ungrounded_call(prompt, temperature)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_facts_grounding.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Live grounding smoke test (manual; the key risk)**

Run (requires Vertex creds in `.env`):
```bash
python -c "import facts_grounding as f; print(f._grounded_call('Did World War II end in 1945? Answer yes or no and cite a source.', 0.0))"
```
Expected: a short grounded answer mentioning 1945. If this raises an SDK/import
error, note the exact error: the fallback keeps the app working, but adjust the
`_grounded_call` import path to match the installed `vertexai`/`google-cloud-aiplatform`
version (e.g. `from vertexai.preview.generative_models import ...`). Re-run until the
grounded path returns text.

- [ ] **Step 6: Commit**

```bash
git add facts_grounding.py tests/test_facts_grounding.py
git commit -m "feat: grounded facts call with ungrounded fallback"
```

---

## Task 4: Rewire engine to 5 categories + corrected_text (`review_engine_multi.py`)

**Files:**
- Modify: `review_engine_multi.py` (delete commented block ~1–361; new `DISPLAY_BY_INDEX`; loop 1–5; Facts uses `facts_grounding`; new aggregator schema; preamble from `7.yaml`, aggregator from `6.yaml`)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `facts_grounding.grounded_generate` (Task 3); prompts `1`–`7` (Task 2); `utils1.normalize_review_payload`, `PARAM_ORDER` (Task 1).
- Produces: `run_review_multi(script_text, prompts_dir="Scriptmodel/prompts", temperature=0.0) -> str` returning a `BEGIN_JSON…END_JSON` payload whose dict has keys `scores`, `per_parameter`, `overall_rating`, `strengths`, `weaknesses`, `suggestions`, `summary`, `corrected_text`.
- Produces: `AggregatorAll` pydantic model with fields `overall_rating: int(1..10)`, `strengths: List[str]`, `weaknesses: List[str]`, `suggestions: List[str]`, `summary: str`, `corrected_text: str`.

- [ ] **Step 1: Write the failing test (mocked LLM + grounding)**

Create `tests/test_engine.py`:
```python
import json
import review_engine_multi as eng


class _Resp:
    def __init__(self, content): self.content = content


def _specialist_json(pid, score):
    return (
        "BEGIN_JSON\n"
        + json.dumps({
            "parameter_id": pid, "score": score,
            "explanation_bullets": ["ok"], "weakness": "Not present",
            "suggestions": [], "areas_of_improvement": [], "summary": "ok",
        })
        + "\nEND_JSON"
    )


def test_run_review_multi_builds_five_category_payload(monkeypatch):
    # 4 grammar-family specialists go through the langchain llm
    seq = [_specialist_json(p, 8) for p in ("grammar", "spelling", "punctuation", "style")]

    class _LLM:
        def invoke(self, prompt): return _Resp(seq.pop(0))

    monkeypatch.setattr(eng, "_make_llm", lambda t: _LLM())
    # Facts specialist goes through grounded path
    monkeypatch.setattr(eng, "grounded_generate",
                        lambda prompt, temperature=0.0: _specialist_json("facts", 9))
    # prompt loading -> trivial templates with required placeholders
    def fake_load(prefix, n):
        if n == 6: return "{evidence_json} {script}"
        return "{script}"
    monkeypatch.setattr(eng, "_load_prompt", fake_load)
    monkeypatch.setattr(eng, "_require_vertex_config", lambda: None)

    # Aggregator structured output
    class _Agg:
        overall_rating = 7
        strengths = ["clear"]; weaknesses = ["typos"]; suggestions = ["proofread"]
        summary = "Solid draft."
        corrected_text = "Corrected body."

    class _StructLLM:
        def invoke(self, prompt): return _Agg()

    class _AggLLM:
        def with_structured_output(self, schema): return _StructLLM()

    # second _make_llm call (aggregator) -> object with with_structured_output
    calls = {"n": 0}
    def make_llm(t):
        calls["n"] += 1
        return _LLM() if calls["n"] == 1 else _AggLLM()
    monkeypatch.setattr(eng, "_make_llm", make_llm)

    out = eng.run_review_multi("Some text.", prompts_dir="x", temperature=0.0)
    data = json.loads(out.split("BEGIN_JSON")[1].split("END_JSON")[0])

    assert set(data["scores"].keys()) == {
        "Grammar", "Spelling", "Punctuation", "Style/Clarity", "Facts"}
    assert data["scores"]["Facts"] == 9
    assert data["overall_rating"] == 7
    assert data["corrected_text"] == "Corrected body."
    assert "viral_quotient" not in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_engine.py -v`
Expected: FAIL — engine still uses 7 viral params and old aggregator schema.

- [ ] **Step 3: Delete the commented legacy block**

In `review_engine_multi.py`, delete the leading commented-out block (the `# from __future__ ...` through `# return f"{_BEGIN}\n{json.dumps(...)}\n{_END}\n"`), leaving the active `# run_review_multi.py — S3-first prompt loader ...` comment and `from __future__ import annotations` as the start.

- [ ] **Step 4: Import grounding + update display map**

Near the other imports add:
```python
from facts_grounding import grounded_generate
```
Replace `DISPLAY_BY_INDEX` with:
```python
DISPLAY_BY_INDEX = {
    1: "Grammar",
    2: "Spelling",
    3: "Punctuation",
    4: "Style/Clarity",
    5: "Facts",
    # 6 = aggregator, 7 = shared preamble
}
```

- [ ] **Step 5: Replace the aggregator schema**

Replace class `AggregatorAll` with:
```python
class AggregatorAll(BaseModel):
    overall_rating: conint(ge=1, le=10)
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]
    summary: str
    corrected_text: str
```

- [ ] **Step 6: Rewrite `run_review_multi` body**

Replace the function body with (preamble now `7.yaml`, loop `1..5`, Facts grounded, aggregator `6.yaml`):
```python
def run_review_multi(
    script_text: str,
    prompts_dir: str = "Scriptmodel/prompts",
    temperature: float = 0.0,
    include_commentary: bool = False,  # kept for API parity; ignored
) -> str:
    _require_vertex_config()
    llm = _make_llm(temperature)

    # Shared preamble (7.yaml) if present
    try:
        global_preamble = _load_prompt(prompts_dir, 7).strip()
        if global_preamble:
            global_preamble += "\n\n"
    except FileNotFoundError:
        global_preamble = ""

    scores: Dict[str, int] = {}
    per_parameter: Dict[str, Dict[str, Any]] = {}

    for i in range(1, 5 + 1):
        name = DISPLAY_BY_INDEX[i]
        tmpl = _load_prompt(prompts_dir, i)
        prompt_body = _inject(tmpl, script=script_text)
        prompt = f"{global_preamble}{prompt_body}"

        try:
            if name == "Facts":
                raw_text = grounded_generate(prompt, temperature=temperature)
            else:
                resp = _invoke_with_retries(llm, prompt)
                raw_text = getattr(resp, "content", "") or ""
            data = _parse_json(raw_text)
        except Exception as e:
            short = (str(e) or "unknown").strip()
            raise RuntimeError(f"JSON parse failed on prompt {i} ({name}). Error: {short}")

        block = _to_legacy_param_block(data)
        scores[name] = int(block.get("score", 0))
        per_parameter[name] = block

    evidence = {"scores": scores, "per_parameter": per_parameter}
    evidence_json = json.dumps(evidence, ensure_ascii=False)

    tmpl6 = _load_prompt(prompts_dir, 6)
    prompt6_body = _inject(tmpl6, evidence_json=evidence_json, script=script_text)
    prompt6 = f"{global_preamble}{prompt6_body}"

    try:
        llm_aggr = _make_llm(temperature).with_structured_output(AggregatorAll)
        agg: AggregatorAll = llm_aggr.invoke(prompt6)
    except Exception as e:
        short = (str(e) or "unknown").strip()
        raise RuntimeError(f"Aggregator failed on prompt 6. Error: {short}")

    final_payload: Dict[str, Any] = {
        "scores": scores,
        "per_parameter": per_parameter,
        "overall_rating": int(agg.overall_rating),
        "strengths": agg.strengths,
        "weaknesses": agg.weaknesses,
        "suggestions": agg.suggestions,
        "summary": agg.summary,
        "corrected_text": agg.corrected_text,
    }

    final_payload = normalize_review_payload(final_payload)
    return _wrap_json(final_payload)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_engine.py -v`
Expected: PASS.

- [ ] **Step 8: Run the full suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add review_engine_multi.py tests/test_engine.py
git commit -m "feat: engine runs 5 writing categories + grounded facts + corrected_text"
```

---

## Task 5: UI — categories, counts, paste, corrected view, relaxed headings (`app_grammarly_ui.py`)

**Files:**
- Modify: `app_grammarly_ui.py` (delete commented block ~1–1206; colors; title; paste tab; relax heading suppression; right-panel counts; corrected-text panel + download)

**Interfaces:**
- Consumes: `st.session_state.data["corrected_text"]`, `["summary"]`, `["scores"]`, `per_parameter` (Task 4); `utils1.PARAM_ORDER` (Task 1).
- Produces: no new exports (Streamlit app). Behavioral deliverable only.

- [ ] **Step 1: Delete the commented legacy block**

Delete the leading commented-out block in `app_grammarly_ui.py` (lines from the top through the `# //////...` divider near line 1206), leaving the active `import os, re, glob, ...` as the first code line.

- [ ] **Step 2: Replace `PARAM_COLORS` and title**

Replace `PARAM_COLORS` with:
```python
PARAM_COLORS: Dict[str, str] = {
    "Grammar":       "#ff6b6b",
    "Spelling":      "#6b8cff",
    "Punctuation":   "#eab308",
    "Style/Clarity": "#a78bfa",
    "Facts":         "#10b981",
}
```
In `render_app_title`, change the `<h1>` text from `Viral Script Reviewer` to `Writing Assistant`. Change `st.set_page_config(page_title=...)` to `page_title="Writing Assistant"`.

- [ ] **Step 3: Relax heading suppression**

In `build_spans_by_param`, delete the two lines that skip heading-context/heading-range matches so errors in titles are still highlighted:
```python
            if heading_ranges and _overlaps_any(s, e, heading_ranges): continue
            if _is_heading_context(script_text, s, e): continue
```
Also remove the `_is_heading_like(clean)` early-continue in the same loop (single-word spelling fixes must not be dropped):
```python
            if _is_heading_like(clean): continue
```
Leave the helper functions defined (still imported elsewhere); we just stop calling them here.

- [ ] **Step 4: Re-add a Paste tab in `render_home`**

In `render_home`, change the tabs line and add a paste branch. Replace:
```python
    (tab_upload,) = st.tabs(["Upload file"])
    uploaded_file = None
    uploaded_name = None
    uploaded_key  = None
```
with:
```python
    tab_upload, tab_paste = st.tabs(["Upload file", "Paste text"])
    uploaded_file = None
    uploaded_name = None
    uploaded_key  = None
    pasted_text = None
```
After the existing `with tab_upload:` block, add:
```python
    with tab_paste:
        pasted_text = st.text_area("Paste your text here", height=300)
```
Then in the `if st.button("🚀 Run Review", ...)` handler, after the `if uploaded_file:` / `else:` branch that currently calls `st.warning(...)`, change the trailing `else` to also accept pasted text. Replace:
```python
        else:
            st.warning("Please upload a script first.")
            st.stop()
```
with:
```python
        elif pasted_text and pasted_text.strip():
            base_stem = "pasted_text"
            script_text = pasted_text.strip()
            source_docx_path = None
        else:
            st.warning("Please upload a file or paste some text first.")
            st.stop()
```

- [ ] **Step 5: Add issue counts to the category chips (right panel)**

In `render_review`, inside `with right:`, replace the chip loop:
```python
        for p in [p for p in PARAM_ORDER if p in scores]:
            if st.button(p, key=f"chip_{p}", help="Show inline AOI highlights for this parameter"):
                st.session_state.param_choice = p
```
with a version that shows per-category counts:
```python
        data_per = (data or {}).get("per_parameter", {}) or {}
        for p in [p for p in PARAM_ORDER if p in scores]:
            n_issues = len((data_per.get(p) or {}).get("areas_of_improvement") or [])
            if st.button(f"{p} · {n_issues}", key=f"chip_{p}",
                         help="Show inline highlights for this category"):
                st.session_state.param_choice = p
```

- [ ] **Step 6: Replace the left-panel viral lists with writing summary**

In `render_review` `with left:`, the block currently builds `strengths` from scores and renders `_bullets("Weaknesses"...)`, `"Suggestions"`, `"Drop-off Risks"`, and `"Viral Quotient"`. Replace everything from the `strengths = (data or {}).get("strengths") or []` line through the `st.markdown("**Viral Quotient**"); ...` line with:
```python
        def _bullets(title: str, items):
            st.markdown(f"**{title}**")
            for s in (items or []):
                if isinstance(s, str) and s.strip():
                    st.write("• " + _sanitize_editor_text(s))
            if not items:
                st.write("• —")

        _bullets("Strengths", data.get("strengths"))
        _bullets("Weaknesses", data.get("weaknesses"))
        _bullets("Suggestions", data.get("suggestions"))
        st.markdown("**Summary**")
        st.write(_sanitize_editor_text(data.get("summary", "—")))
```

- [ ] **Step 7: Add the corrected-text panel + download**

In `render_review`, at the end of the function (after the `with center:` block), add a full-width corrected-version section:
```python
    corrected = (data or {}).get("corrected_text") or ""
    if corrected:
        st.divider()
        st.subheader("Corrected version")
        col_o, col_c = st.columns(2)
        with col_o:
            st.caption("Original")
            st.text_area("original_ro", script_text, height=400,
                         label_visibility="collapsed")
        with col_c:
            st.caption("Corrected")
            st.text_area("corrected_ro", corrected, height=400,
                         label_visibility="collapsed")
        st.download_button(
            "⬇ Download corrected text",
            data=corrected.encode("utf-8"),
            file_name=f"{st.session_state.get('base_stem','document')}_corrected.txt",
            mime="text/plain",
        )
```

- [ ] **Step 8: Manual smoke test — paste flow end to end**

Run:
```bash
streamlit run app_grammarly_ui.py
```
In the browser: open the **Paste text** tab, paste a few sentences containing a
deliberate grammar error ("They was late"), a typo ("recieve"), and a wrong fact
("World War II ended in 1946"). Click **Run Review**. Verify:
- Five category chips appear with counts (e.g. `Grammar · 1`, `Spelling · 1`, `Facts · 1`).
- Clicking a chip highlights the matching text inline; clicking a highlight opens the popup with Issue/Fix.
- The **Corrected version** panel shows fixes and the download button works.
Note any failures and fix before committing.

- [ ] **Step 9: Commit**

```bash
git add app_grammarly_ui.py
git commit -m "feat: writing-assistant UI (categories, counts, paste, corrected view)"
```

---

## Task 6: End-to-end verification + docs

**Files:**
- Modify: `README.md` (create if absent) — describe the Writing Assistant.

- [ ] **Step 1: Full test suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Upload-flow smoke test**

Run `streamlit run app_grammarly_ui.py`, upload a `.docx` containing known errors,
confirm inline highlights land on the right words, Facts flags a wrong date with a
cited correction, and the corrected `.docx`/text downloads. Confirm a previously
reviewed run still opens from **Recents**.

- [ ] **Step 3: Write/refresh README**

Create or update `README.md` with: what the app does (grammar/spelling/punctuation/
style + web-verified facts), required env vars (`GOOGLE_CLOUD_PROJECT`,
`GOOGLE_APPLICATION_CREDENTIALS`, optional `RUNPOD_S3_*`), and run command
`streamlit run app_grammarly_ui.py`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document the Writing Assistant"
```

---

## Self-Review Notes

- **Spec coverage:** grammar/spelling/punctuation/style (Tasks 2,4,5) ✓; web-verified facts (Tasks 2,3,4) ✓; list + inline highlights (Task 5) ✓; 1–10 rating (Task 4) ✓; corrected side-by-side + download (Tasks 4,5) ✓; relaxed heading suppression (Task 5) ✓; paste tab (Task 5) ✓; dead-code deletion (Tasks 1,4,5) ✓; reuse storage/history (untouched) ✓.
- **Risk:** grounding-tool wiring (Task 3, Step 5) — validated live with an explicit fallback already coded.
- **Type consistency:** `AggregatorAll` fields (Task 4) match the payload keys consumed by the UI (Task 5: `corrected_text`, `summary`, `strengths/weaknesses/suggestions`). `PARAM_ORDER` (Task 1) matches `DISPLAY_BY_INDEX` values (Task 4) and `PARAM_COLORS` keys (Task 5).
