"""One-off migration: repair source links in saved history.

- Resolves grounding-redirect URLs in `fact_check.sources` to their permanent final URLs.
- Clears the old per-card `aoi[*].sources` (truncated model URLs that 404'd).

Run from the repo root or backend/:  python backend/migrate_history.py
"""
import os
import sys
import json
import glob

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)                       # backend/
sys.path.insert(0, os.path.join(_HERE, ".."))   # repo root

from facts_grounding import resolve_url  # noqa: E402

try:
    from history import _history_dir  # noqa: E402
    HIST_DIR = _history_dir()
except Exception:
    HIST_DIR = os.getenv("HISTORY_DIR") or os.path.join(_HERE, "..", "Scriptmodel", "outputs", "_history")


def migrate() -> None:
    files = glob.glob(os.path.join(HIST_DIR, "*.json"))
    print(f"history dir: {HIST_DIR}")
    print(f"files: {len(files)}")
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                j = json.load(fh)
        except Exception as e:
            print(f"  skip {os.path.basename(f)}: {e}")
            continue

        changed = False
        resolved = 0

        fc = j.get("fact_check")
        if isinstance(fc, dict):
            srcs = fc.get("sources") or []
            for s in srcs:
                if isinstance(s, dict) and "vertexaisearch" in (s.get("uri") or ""):
                    final = resolve_url(s["uri"])
                    if final and final != s["uri"]:
                        s["uri"] = final
                        resolved += 1
                        changed = True

        # clear old broken per-card source lists
        cleared = 0
        for v in (j.get("aoi") or {}).values():
            if isinstance(v, dict) and v.get("sources"):
                v["sources"] = []
                cleared += 1
                changed = True

        if changed:
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(j, fh, ensure_ascii=False)
        print(f"  {j.get('title', os.path.basename(f))}: resolved {resolved} link(s), cleared {cleared} broken card source(s)")


if __name__ == "__main__":
    migrate()
    print("done.")
