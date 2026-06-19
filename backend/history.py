"""VPS-disk review history: one JSON file per review, with a byte quota."""
from __future__ import annotations

import os
import re
import json
import uuid
import glob
import datetime
from typing import Any, Dict, List, Optional

_GB = 1024 ** 3
_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")  # safe ids only (no path separators)


def _history_dir() -> str:
    d = os.getenv("HISTORY_DIR", "Scriptmodel/outputs/_history")
    os.makedirs(d, exist_ok=True)
    return d


def _quota_bytes() -> int:
    try:
        gb = float(os.getenv("HISTORY_QUOTA_GB", "50"))
    except ValueError:
        gb = 50.0
    return int(gb * _GB)


def _file_for(rid: str) -> Optional[str]:
    if not rid or not _ID_RE.match(rid):
        return None
    p = os.path.join(_history_dir(), rid + ".json")
    # ensure the resolved path stays inside the history dir
    base = os.path.realpath(_history_dir())
    full = os.path.realpath(p)
    if os.path.dirname(full) != base:
        return None
    return p


def storage_usage() -> Dict[str, Any]:
    d = _history_dir()
    files = glob.glob(os.path.join(d, "*.json"))
    used = sum(os.path.getsize(f) for f in files if os.path.exists(f))
    quota = _quota_bytes()
    percent = (used / quota * 100.0) if quota > 0 else 100.0
    return {"used_bytes": used, "quota_bytes": quota, "percent": round(percent, 2), "count": len(files)}


def save_review(payload: Dict[str, Any], title: str) -> Dict[str, Any]:
    usage = storage_usage()
    if usage["used_bytes"] >= usage["quota_bytes"]:
        return {"saved": False, "id": None, "reason": "storage_full"}
    rid = uuid.uuid4().hex
    now = datetime.datetime.now().replace(microsecond=0)
    record = dict(payload)
    record["id"] = rid
    record["title"] = title or "untitled"
    record["created_at"] = now.isoformat()
    if "overall_rating" not in record:
        record["overall_rating"] = payload.get("overall_rating", "")
    path = os.path.join(_history_dir(), rid + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)
    return {"saved": True, "id": rid, "reason": None}


def list_reviews() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in glob.glob(os.path.join(_history_dir(), "*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                j = json.load(fh)
        except Exception:
            continue
        out.append({
            "id": j.get("id") or os.path.splitext(os.path.basename(f))[0],
            "title": j.get("title", "untitled"),
            "created_at": j.get("created_at", ""),
            "overall_rating": j.get("overall_rating", ""),
            "size_bytes": os.path.getsize(f),
        })
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return out


def load_review(rid: str) -> Optional[Dict[str, Any]]:
    path = _file_for(rid)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def delete_review(rid: str) -> Dict[str, Any]:
    path = _file_for(rid)
    deleted = False
    if path and os.path.exists(path):
        try:
            os.remove(path)
            deleted = True
        except OSError:
            deleted = False
    return {"deleted": deleted, **storage_usage()}
