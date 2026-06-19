# Writing Assistant

A Grammarly-style writing assistant. Upload or paste text and it checks **grammar,
spelling, punctuation, style/clarity**, and **real-world facts** (dates, names, events —
verified live against Google Search). Issues appear as inline highlights and as a sidebar
of suggestion cards with **Apply / Copy / Dismiss**; applying a fix edits the script
inline, and you can copy or download the edited result. Every analysis is saved to a
**review history** on the server, with a 50 GB storage budget and a permanent delete.

## Architecture

```
React (Vite) SPA  ──/api/*──▶  FastAPI (backend/main.py)
                                 ├─ utils1.py              file parsing + JSON extraction
                                 ├─ review_engine_multi    Gemini on Vertex AI — 4 writing
                                 │                          categories (include_facts=False)
                                 ├─ backend/matching.py    quote → character-span matcher
                                 ├─ factcheck.py           web-grounded facts
                                 │                          (google-genai + Google Search)
                                 └─ backend/history.py     VPS-disk review history + quota
```

The four writing categories are **Grammar, Spelling, Punctuation, Style/Clarity**. Facts
are handled by the dedicated `factcheck.py` (red/amber/green verdicts + source links), so
the engine's own "Facts" pass is skipped via `include_facts=False`.

## Setup

### 1. Backend (FastAPI)

From the repo root:

```bash
pip install -r requirements.txt
pip install -r backend/requirements.txt

cd backend
uvicorn main:app --reload --port 8000
```

Health check: http://localhost:8000/api/health → `{"status":"ok"}`.

### 2. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api/*` to the backend on
port 8000 (no CORS setup needed in development).

## Environment (`.env` in repo root)

```
# Vertex AI (Gemini)
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=./credentials/your-service-account.json
GEMINI_MODEL=gemini-2.5-flash          # optional, this is the default

# Review history (VPS disk)
HISTORY_DIR=Scriptmodel/outputs/_history   # optional, this is the default
HISTORY_QUOTA_GB=50                        # optional, this is the default

# Optional: load prompts from RunPod S3 instead of the local prompts/ folder
# PROMPTS_DIR=Scriptmodel/prompts
# RUNPOD_S3_ENDPOINT=... RUNPOD_S3_BUCKET=... RUNPOD_S3_REGION=... AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
```

The service account needs the **Vertex AI User** role. Facts grounding uses Vertex's
Google Search tool — no extra API key required.

## Review history & storage

- Each analysis is saved as one JSON file under `HISTORY_DIR` on the server (the plain
  script text + spans + suggestions are enough to re-render — the original upload is not
  stored).
- The **History** view lists saved reviews; click one to reopen it.
- A **storage progress bar** shows usage against the `HISTORY_QUOTA_GB` (default 50 GB)
  budget and turns red near full.
- When the budget is full, **new saves are blocked** (a banner tells you to delete old
  reviews) — nothing is ever auto-deleted.
- **Delete is permanent** — it removes the file from the server disk immediately.

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/analyze` | Analyze an uploaded `.docx` / `.pdf` / `.txt` |
| POST | `/api/analyze-text` | Analyze pasted text (`{"text": "..."}`, min 50 chars) |
| GET | `/api/history` | List saved reviews |
| GET | `/api/history/{id}` | Load a saved review |
| DELETE | `/api/history/{id}` | Permanently delete a saved review |
| GET | `/api/storage` | Storage usage (`used_bytes`, `quota_bytes`, `percent`, `count`) |
| GET | `/api/health` | Health check |

## Manual verification

With both servers running and Vertex credentials configured:

1. Open http://localhost:5173 → **Paste text** and enter:
   `They was late too the meetng. World War II ended in 1946.`
2. Click **Analyze text**. Expect:
   - 4 category pills (Grammar / Spelling / Punctuation / Style) with counts, plus a 🔎 **Fact Check** pill.
   - Inline highlights on "They was" and "meetng"; clicking a card's **Apply** edits the text inline.
   - Fact Check flags "ended in 1946" → **1945** with a source link.
3. Open **📁 History** → the run is listed; the storage bar shows usage.
4. Click **Delete** → the review is permanently removed (list empties, bar drops).

## Known limitations

- **English only** — prompts and the matcher are tuned for English.
- **No auth / multi-user** — a single shared history store on the server.
- **Live fact-checking** requires working Vertex credentials; without them the fact-check
  falls back to the model's own knowledge and flags the result as not web-verified.
- Editing is via inline **Apply/Dismiss** then Copy/Download of the edited script (no
  realtime as-you-type checking).

## Tests

```bash
python -m pytest -q
```

Covers the engine flag, the fact-check seams, the span matcher, the history store
(roundtrip / quota / permanent delete / path-safety), and the backend API (analyze-text +
history endpoints). Frontend is verified with `npm run build` + the manual checklist above.
