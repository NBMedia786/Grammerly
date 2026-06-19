# main.py — FastAPI service wrapping the existing AI/parsing pipeline.
#
# Reuses, unchanged:
#   utils1.load_script_file / extract_review_json / PARAM_ORDER
#   review_engine_multi.run_review_multi  (Gemini via Vertex AI)
#   matching.build_spans_by_param         (quote -> character spans)
#
# Run:  uvicorn main:app --reload --port 8000   (from the backend/ dir)

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Make the repo-root modules (utils1, review_engine_multi) importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from utils1 import load_script_file, extract_review_json, PARAM_ORDER
from review_engine_multi import run_review_multi
from matching import build_spans_by_param, locate_quote, PARAM_COLORS
from factcheck import run_fact_check
from plagiarism import run_plagiarism_check
from ai_detect import run_ai_detection
import history as history_store

# Document-highlight colors for fact-check verdicts.
FACT_COLORS = {"incorrect": "#ef4444", "unverifiable": "#f59e0b", "correct": "#22c55e"}
PLAGIARISM_COLOR = "#f97316"

load_dotenv()

# Default to the repo-root prompts/ folder (absolute, so it resolves no matter what
# directory uvicorn is launched from). Set PROMPTS_DIR=Scriptmodel/prompts to load from S3.
_REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = os.getenv("PROMPTS_DIR", str(_REPO_ROOT / "prompts"))
ALLOWED_EXT = {".docx", ".pdf", ".txt"}

# A relative GOOGLE_APPLICATION_CREDENTIALS in .env (e.g. ./credentials/key.json) is meant
# relative to the repo root; resolve it to an absolute path so Vertex auth works regardless
# of which directory uvicorn is launched from.
_cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if _cred and not os.path.isabs(_cred):
    _cred_abs = (_REPO_ROOT / _cred).resolve()
    if _cred_abs.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_cred_abs)

app = FastAPI(title="Writing Assistant API", version="1.0.0")

# Dev CORS: allow the Vite dev server. Tighten allow_origins for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


def _analyze_text(script_text: str, title: str) -> dict:
    """Run the full AI review pipeline and return the response dict."""
    # --- Run the AI review (Gemini calls via Vertex). Surface failures cleanly. ---
    try:
        review_text = run_review_multi(script_text=script_text, prompts_dir=PROMPTS_DIR,
                                       temperature=0.0, include_facts=False)
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=f"Configuration error: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI review failed: {e}")

    data = extract_review_json(review_text)
    if not data:
        raise HTTPException(status_code=502, detail="Could not parse the AI's JSON output.")

    # --- Map each flagged quote to a character span in script_text ---
    spans_map, aoi_ranges = build_spans_by_param(script_text, data)

    spans = [
        {"start": s, "end": e, "color": color, "aid": aid, "param": param}
        for param, items in spans_map.items()
        for (s, e, color, aid) in items
    ]

    per = (data.get("per_parameter") or {})
    aoi = {}
    param_order = [p for p in PARAM_ORDER if p != "Facts"]
    for param in param_order:
        blk = per.get(param) or {}
        for i, item in enumerate(blk.get("areas_of_improvement") or [], start=1):
            aid = f"{param.replace(' ', '_')}-AOI-{i}"
            rng = aoi_ranges.get(aid)
            line = script_text[rng[0]:rng[1]] if rng else (item.get("quote_verbatim", "") or "")
            aoi[aid] = {
                "param": param,
                "matched": bool(rng),  # False => quote couldn't be located in the text
                "line": line,
                "issue": (item.get("issue", "") or ""),
                "fix": (item.get("fix", "") or ""),
                "why": (item.get("why_this_helps", "") or ""),
            }

    # --- Fact check: verify claims (dates/names/events/stats) against the web ---
    fc = run_fact_check(script_text)
    fact_counts = {"incorrect": 0, "unverifiable": 0, "correct": 0}
    for i, c in enumerate(fc.get("claims", []), start=1):
        aid = f"FACT-{i}"
        verdict = c.get("verdict", "unverifiable")
        fact_counts[verdict] = fact_counts.get(verdict, 0) + 1
        rng = locate_quote(script_text, c.get("quote_verbatim", ""))
        matched = bool(rng)
        line = script_text[rng[0]:rng[1]] if rng else (c.get("quote_verbatim", "") or "")
        aoi[aid] = {
            "param": "Fact Check",
            "kind": "fact",
            "matched": matched,
            "verdict": verdict,
            "line": line,
            "issue": c.get("claim", ""),
            "fix": c.get("correction", ""),   # drop-in correction -> "Apply" replaces the wrong fact
            "why": c.get("explanation", ""),
            "sources": c.get("sources", []),
        }
        # Highlight only claims that need attention (wrong or unverifiable).
        if rng and verdict in ("incorrect", "unverifiable"):
            spans.append({
                "start": rng[0], "end": rng[1],
                "color": FACT_COLORS.get(verdict, "#f59e0b"),
                "aid": aid, "param": "Fact Check",
            })

    # per_parameter minus the AOI arrays (those are delivered via `aoi`/`spans`)
    per_clean = {
        k: {kk: vv for kk, vv in (v or {}).items() if kk != "areas_of_improvement"}
        for k, v in per.items()
    }

    param_colors = dict(PARAM_COLORS)
    param_colors["Fact Check"] = FACT_COLORS["incorrect"]

    response = {
        "script_text": script_text,
        "scores": data.get("scores", {}),
        "overall_rating": data.get("overall_rating", ""),
        "strengths": data.get("strengths", []),
        "weaknesses": data.get("weaknesses", []),
        "suggestions": data.get("suggestions", []),
        "summary": data.get("summary", ""),
        "param_order": param_order,
        "param_colors": param_colors,
        "per_parameter": per_clean,
        "spans": spans,
        "aoi": aoi,
        "fact_check": {
            "web_grounded": fc.get("web_grounded", False),
            "counts": fact_counts,
            "error": fc.get("error"),
        },
    }

    save = history_store.save_review(response, title)
    response["saved"] = save["saved"]
    response["save_error"] = save["reason"]
    response["id"] = save["id"]  # history id of this run (None if storage full) — lets the UI highlight it
    return response


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    filename = file.filename or "uploaded"
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Please upload a .docx, .pdf, or .txt file.")
    raw = await file.read()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw); tmp_path = tmp.name
        script_text = load_script_file(tmp_path)
    finally:
        if tmp_path:
            try: os.remove(tmp_path)
            except OSError: pass
    if len((script_text or "").strip()) < 50:
        raise HTTPException(status_code=422, detail="Extracted text looks too short. Check the file.")
    return _analyze_text(script_text, os.path.splitext(os.path.basename(filename))[0] or "uploaded")


class TextIn(BaseModel):
    text: str


@app.post("/api/analyze-text")
def analyze_text(body: TextIn):
    script_text = (body.text or "").strip()
    if len(script_text) < 50:
        raise HTTPException(status_code=422, detail="Please paste at least 50 characters of text.")
    return _analyze_text(script_text, "pasted-text")


@app.get("/api/history")
def get_history():
    return history_store.list_reviews()


@app.get("/api/history/{rid}")
def get_history_item(rid: str):
    rec = history_store.load_review(rid)
    if rec is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    return rec


class RenameIn(BaseModel):
    title: str


@app.patch("/api/history/{rid}")
def rename_history_item(rid: str, body: RenameIn):
    res = history_store.rename_review(rid, body.title)
    if not res["renamed"]:
        raise HTTPException(status_code=400, detail="Could not rename that review.")
    return res


@app.delete("/api/history/{rid}")
def delete_history_item(rid: str):
    return history_store.delete_review(rid)


@app.get("/api/storage")
def get_storage():
    return history_store.storage_usage()


class OriginalityIn(BaseModel):
    text: str


@app.post("/api/originality")
def originality(body: OriginalityIn):
    text = (body.text or "").strip()
    if len(text) < 50:
        raise HTTPException(status_code=422, detail="Need at least 50 characters to check.")

    try:
        ai = run_ai_detection(text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI detection failed: {e}")
    ai["disclaimer"] = ("Rough estimate — automated AI detection is unreliable. "
                        "Treat this as a signal, not a verdict.")

    try:
        plag = run_plagiarism_check(text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Plagiarism check failed: {e}")

    spans = []
    aoi = {}
    for i, m in enumerate(plag.get("matches", []), start=1):
        aid = f"PLAG-{i}"
        rng = locate_quote(text, m.get("quote_verbatim", ""))
        matched = bool(rng)
        line = text[rng[0]:rng[1]] if rng else (m.get("quote_verbatim", "") or "")
        aoi[aid] = {
            "param": "Plagiarism", "kind": "plagiarism", "matched": matched,
            "line": line, "issue": "Appears on the web" + (f" — {m['note']}" if m.get("note") else ""),
            "fix": "", "why": "Best-effort verbatim web match. Paraphrasing is not detected — verify manually.",
            "sources": m.get("sources", []),
        }
        if rng:
            spans.append({"start": rng[0], "end": rng[1], "color": PLAGIARISM_COLOR,
                          "aid": aid, "param": "Plagiarism"})

    return {
        "ai_detection": ai,
        "plagiarism": {"web_grounded": plag.get("web_grounded", False), "count": plag.get("count", 0)},
        "spans": spans,
        "aoi": aoi,
    }
