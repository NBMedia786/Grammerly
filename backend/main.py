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
from dotenv import load_dotenv

from utils1 import load_script_file, extract_review_json, PARAM_ORDER
from review_engine_multi import run_review_multi
from matching import build_spans_by_param, locate_quote, PARAM_COLORS
from factcheck import run_fact_check

# Document-highlight colors for fact-check verdicts.
FACT_COLORS = {"incorrect": "#ef4444", "unverifiable": "#f59e0b", "correct": "#22c55e"}

load_dotenv()

# Local "prompts" dir by default; set PROMPTS_DIR=Scriptmodel/prompts to use S3.
PROMPTS_DIR = os.getenv("PROMPTS_DIR", "prompts")
ALLOWED_EXT = {".docx", ".pdf", ".txt"}

app = FastAPI(title="Viral Script Reviewer API", version="1.0.0")

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
            tmp.write(raw)
            tmp_path = tmp.name
        script_text = load_script_file(tmp_path)
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    if len((script_text or "").strip()) < 50:
        raise HTTPException(status_code=422, detail="Extracted text looks too short. Check the file.")

    # --- Run the AI review (8 Gemini calls via Vertex). Surface failures cleanly. ---
    try:
        review_text = run_review_multi(script_text=script_text, prompts_dir=PROMPTS_DIR, temperature=0.0)
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
    for param in PARAM_ORDER:
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

    return {
        "script_text": script_text,
        "scores": data.get("scores", {}),
        "overall_rating": data.get("overall_rating", ""),
        "strengths": data.get("strengths", []),
        "weaknesses": data.get("weaknesses", []),
        "suggestions": data.get("suggestions", []),
        "drop_off_risks": data.get("drop_off_risks", []),
        "viral_quotient": data.get("viral_quotient", ""),
        "param_order": PARAM_ORDER,
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
