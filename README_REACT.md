# Viral Script Reviewer — FastAPI + React

A Grammarly-style UX for reviewing video scripts. The Python AI/parsing pipeline
is reused unchanged; a FastAPI service exposes it as an API, and a React frontend
renders inline highlights with **Apply / Copy / Dismiss** on each suggestion.

```
repo/
├── utils1.py                 # (existing) file parsing + JSON extraction
├── review_engine_multi.py    # (existing) Gemini-on-Vertex pipeline
├── prompts/                  # (existing) 1..9 prompt YAMLs
├── backend/
│   ├── main.py               # FastAPI app  ->  POST /api/analyze
│   ├── matching.py           # quote -> character-span matcher (reused logic)
│   └── requirements.txt
└── frontend/                 # React (Vite) single-page app
```

## How it works
1. **Upload** a `.docx` / `.pdf` / `.txt`.
2. Backend extracts the plain text, runs the 8 Gemini passes, and maps each
   flagged quote to a character span **in that same text** (so highlights can’t
   drift — there’s only one linearization, unlike the old DOCX renderer).
3. Frontend draws the highlights and a sidebar of suggestion cards. For each one
   you can **Apply** (replaces the text inline, in green), **Copy fix**, or
   **Dismiss** — then **Copy / Download the edited script**.

---

## 1) Backend setup

From the repo root:

```bash
# install shared AI/parsing deps + backend deps
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

Make sure your `.env` (repo root) is filled in for **Vertex AI**:

```
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
GEMINI_MODEL=gemini-2.5-flash
```

Prompts: by default the backend loads them from the local `prompts/` folder.
To load from RunPod S3 instead, set `PROMPTS_DIR=Scriptmodel/prompts`.

Run the API (from the `backend/` directory so it finds the prompts path):

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Check it: open http://localhost:8000/api/health → `{"status":"ok"}`.

## 2) Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server proxies `/api/*` to the backend
on port 8000, so there are no CORS issues in development.

## Fact check (web-grounded)
Every analysis also runs a **fact check** ([factcheck.py](factcheck.py)): it extracts
checkable claims — especially **dates/years**, names, events, and stats — and verifies
them against the web using **Gemini + Google Search grounding** on Vertex AI.

- Wrong claims are highlighted **red**, unverifiable ones **amber**, with a 🔎 **Fact Check**
  filter in the sidebar. Each card shows the claim, the correction, an explanation, and
  source links — and **Apply correction** swaps the wrong fact (e.g. a bad year) inline.
- A banner shows whether results were **web-verified** or fell back to the model's own
  knowledge (when the installed Vertex SDK has no Search-grounding tool).
- Requirements: Vertex AI must be enabled (it already is for the main review), and your
  region/model must support Google Search grounding. No extra API key is needed.

## Production notes
- Build the frontend with `npm run build` (outputs `frontend/dist/`) and serve it
  behind any static host or via FastAPI’s `StaticFiles`.
- Lock down CORS: set `CORS_ORIGINS=https://your-domain` for the backend.
- The `.env` secrets should move to your platform’s secret manager (not committed).
