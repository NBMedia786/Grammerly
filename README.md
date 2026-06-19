# Writing Assistant

A Grammarly-style writing checker built with Python, Streamlit, and Google Gemini on Vertex AI.

## What it does

Paste or upload any English document and the app runs five specialist checks in parallel:

| Category | What is checked |
|---|---|
| **Grammar** | Subject-verb agreement, verb tense, articles, prepositions, pronouns, fragments, run-ons |
| **Spelling** | Misspelled words and typos |
| **Punctuation** | Commas, apostrophes, quotation marks, colons/semicolons, hyphens, comma splices |
| **Style/Clarity** | Wordiness, passive voice, awkward phrasing, redundancy |
| **Facts** | Dates, named people/places/events, numbers — verified live via Google Search grounding |

Results surface as:

- **Inline highlights** in the document view — click any highlight to see the Issue and suggested Fix.
- **Category chips** in the right panel, each showing a count of flagged issues (e.g. `Grammar · 2`).
- **Grouped issue list** per category with quote, issue description, fix, and explanation.
- **1–10 overall rating** with strengths, weaknesses, and suggestions.
- **Corrected version** — a side-by-side view of the original and fully corrected text, plus a one-click download as a `.txt` file.

No realtime checking; no per-issue "apply" button — corrections are presented as a whole corrected document.

---

## Requirements

### Environment variables

Copy `.env` and fill in your values (the repo's `.env` ships with placeholder values):

```ini
# Required
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1          # default; any region where Gemini is available
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json  # MUST be a real file

# Optional — model override (default: gemini-2.5-flash)
GEMINI_MODEL=gemini-2.5-flash

# Optional — RunPod S3 cloud storage
# Without these the app falls back to local Scriptmodel/ folders.
RUNPOD_S3_ENDPOINT=https://s3api-eu-ro-1.runpod.io/
RUNPOD_S3_BUCKET=your-bucket-name
RUNPOD_S3_REGION=eu-ro-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

> **Note:** `GOOGLE_APPLICATION_CREDENTIALS` in the repo's `.env` is a placeholder path.
> Replace it with the absolute path to a real Google Cloud service-account JSON before running.

### Python dependencies

```bash
pip install -r requirements.txt        # runtime
pip install -r requirements-dev.txt    # tests only (adds pytest)
```

---

## Run

```bash
streamlit run app_grammarly_ui.py
```

The app opens in your browser at `http://localhost:8501`.

---

## Architecture

```
app_grammarly_ui.py          (Streamlit UI — file upload + paste tab, highlights, chips,
                              corrected-text panel, Recents sidebar)
        |
        v
review_engine_multi.run_review_multi()
        |
        |-- prompts/7.yaml  (shared preamble — hard rules for all specialists)
        |
        |-- prompts/1.yaml → Gemini on Vertex  (Grammar specialist)
        |-- prompts/2.yaml → Gemini on Vertex  (Spelling specialist)
        |-- prompts/3.yaml → Gemini on Vertex  (Punctuation specialist)
        |-- prompts/4.yaml → Gemini on Vertex  (Style/Clarity specialist)
        |-- prompts/5.yaml → facts_grounding.grounded_generate()
        |                       └─ Vertex Gemini + Google Search grounding tool
        |                          (falls back to ungrounded Gemini on any SDK error)
        |
        |-- prompts/6.yaml → Gemini on Vertex with structured output
                              (Aggregator: overall_rating, summary, corrected_text)
        |
        v
utils1.py   (shared helpers: PARAM_ORDER, normalize_review_payload, extract_review_json,
             load_script_file, sanitize_editor_text)
```

Prompt files `1`–`5` are specialist prompts (one per writing category); `6` is the aggregator; `7` is the shared preamble injected before every specialist call.

Results are stored as JSON under `Scriptmodel/outputs/` (local) or under the configured S3 bucket, enabling the **Recents** sidebar to reopen past reviews without re-running the model.

---

## Manual verification (real Vertex environment)

The smoke test below requires a working Vertex AI environment (real service-account credentials, `GOOGLE_CLOUD_PROJECT` set, `langchain-google-vertexai` importable without a torch/CUDA error). Run these steps after configuring your `.env`:

1. **Start the app**
   ```bash
   streamlit run app_grammarly_ui.py
   ```

2. **Paste test** — open the **Paste text** tab and paste:
   ```
   They was late to the meating. World War II ended in 1946. The recieve was confirmed.
   ```
   Click **Run Review**.

3. **Verify category chips** — the right panel should show five chips. Expected examples:
   - `Grammar · 1` (flags "They was late")
   - `Spelling · 2` (flags "meating", "recieve")
   - `Facts · 1` (flags "ended in 1946" with correction to 1945 and a cited source)
   - `Punctuation · 0` and `Style/Clarity · 0` (or low counts)

4. **Inline highlights** — click a chip; the matching text in the document view should be highlighted in the category's colour. Click a highlight to confirm the popup shows the Issue and Fix fields.

5. **Facts grounding** — the Facts chip's AOI for "World War II ended in 1946" should include a `why_this_helps` field citing a source (e.g. "Japan surrendered Sept 2, 1945").

6. **Corrected version** — scroll below the document view; confirm the side-by-side panel shows the original and a corrected version with the errors fixed. Click **Download corrected text** and verify the `.txt` file contains the corrected content.

7. **Recents** — refresh the page (or navigate to the sidebar). The just-completed review should appear in **Recents** and open when clicked.

---

## Known limitations

- **English only** — all prompts and the highlight engine are tuned for English text.
- **No per-issue apply button** — clicking a highlight shows the suggested fix in a popup but does not apply it in place. Use the full corrected-text download instead.
- **No realtime checking** — the review runs on demand when you click **Run Review**, not as you type.

## Notes on the Google SDKs

- **Facts grounding uses `google-genai`.** Gemini 2.x requires the new `google_search` tool;
  the older `vertexai` `google_search_retrieval` tool is rejected by `gemini-2.5-flash`.
  `facts_grounding.py` therefore uses the `google-genai` client (`Client(vertexai=True, ...)`)
  for both the grounded and ungrounded Facts calls. Verified live: WWII→1945, Titanic→1912.
- **`transformers`/`torch` are disabled at import.** `langchain_google_vertexai` (used by the
  four non-Facts specialists and the aggregator) pulls in `transformers`, which imports `torch`
  by default and crashes on machines with a broken/GPU-only torch build. The app only needs
  tokenizers, so `review_engine_multi.py` sets `USE_TORCH=0`/`USE_TF=0`/`USE_FLAX=0` **before**
  importing langchain. No code change needed on your end.
