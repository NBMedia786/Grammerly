# matching.py — script-quote → character-span matcher (extracted from the
# Streamlit app, de-coupled from Streamlit/session_state so the API can reuse it).
#
# Highlights are computed against the SAME plain text that is rendered in the
# frontend, so character offsets cannot desync (no second DOCX linearization).

from __future__ import annotations

import re
import difflib
from typing import Dict, Any, List, Tuple, Optional

from utils1 import PARAM_ORDER, sanitize_editor_text

# ---------- Colors (per parameter) ----------
PARAM_COLORS: Dict[str, str] = {
    "Suspense Building":              "#ff6b6b",
    "Language/Tone":                  "#6b8cff",
    "Intro + Main Hook/Cliffhanger":  "#ffb86b",
    "Story Structure + Flow":         "#a78bfa",
    "Pacing":                         "#f43f5e",
    "Mini-Hooks (30–60s)":            "#eab308",
    "Outro (Ending)":                 "#8b5cf6",
}

STRICT_MATCH_ONLY = False

_BRIDGE_CHARS = set("​‌‍⁠﻿\xa0­")


def _normalize_keep_len(s: str) -> str:
    trans = {
        "“": '"', "”": '"', "‘": "'", "’": "'",
        "–": "-", "—": "-",
        "\xa0": " ",
        "​": " ", "‌": " ", "‍": " ", "⁠": " ",
        "﻿": " ", "­": " ",
    }
    return (s or "").translate(str.maketrans(trans))


def _tokenize(s: str) -> List[str]:
    return re.findall(r"\w+", (s or "").lower())


def _iter_sentences_with_spans(text: str) -> List[Tuple[int, int, str]]:
    spans = []
    for m in re.finditer(r'[^.!?]+[.!?]+|\Z', text, flags=re.S):
        s, e = m.start(), m.end()
        seg = text[s:e]
        if seg.strip():
            spans.append((s, e, seg))
    return spans


def _squash_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _clean_quote_for_match(q: str) -> str:
    if not q:
        return ""
    q = _normalize_keep_len(q).strip()
    q = re.sub(r'^[\'"“”‘’\[\(\{<…\-\–\—\s]+', '', q)
    q = re.sub(r'[\'"“”‘’\]\)\}>…\-\–\—\s]+$', '', q)
    return _squash_ws(q)


def _snap_and_bridge_to_word(text: str, start: int, end: int, max_bridge: int = 2) -> Tuple[int, int]:
    n = len(text)
    s, e = max(0, start), max(start, end)

    def _is_inv(ch: str) -> bool:
        return ch in _BRIDGE_CHARS

    while s > 0:
        prev = text[s - 1]
        cur = text[s] if s < n else ""
        if prev.isalnum() and cur.isalnum():
            s -= 1
            continue
        j = s
        brid = 0
        while j < n and _is_inv(text[j]):
            brid += 1
            j += 1
        if brid and (s - 1) >= 0 and text[s - 1].isalnum() and (j < n and text[j].isalnum()):
            s -= 1
            continue
        break

    while e < n:
        prev = text[e - 1] if e > 0 else ""
        nxt = text[e]
        if prev.isalnum() and nxt.isalnum():
            e += 1
            continue
        j = e
        brid = 0
        while j < n and _is_inv(text[j]):
            brid += 1
            j += 1
        if brid and (e - 1) >= 0 and text[e - 1].isalnum() and (j < n and text[j].isalnum()):
            e = j + 1
            continue
        break

    while e < n and text[e] in ',"”’\')]}':
        e += 1
    return s, e


def _heal_split_word_left(text: str, start: int) -> int:
    i = start
    if i <= 1 or i >= len(text):
        return start
    if text[i - 1] != " ":
        return start
    j = i - 2
    while j >= 0 and text[j].isalpha():
        j -= 1
    prev_token = text[j + 1:i - 1]
    if len(prev_token) == 1:
        return i - 2
    return start


def _overlaps_any(s: int, e: int, ranges: List[Tuple[int, int]]) -> bool:
    for rs, re_ in ranges:
        if e > rs and s < re_:
            return True
    return False


def _fuzzy_window_span(tl: str, nl: str, start: int, w: int) -> Tuple[float, Optional[Tuple[int, int]]]:
    window = tl[start:start + w]
    sm = difflib.SequenceMatcher(a=nl, b=window)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
    if not blocks:
        return 0.0, None
    coverage = sum(b.size for b in blocks) / max(1, len(nl))
    first_b = min(blocks, key=lambda b: b.b)
    last_b = max(blocks, key=lambda b: b.b + b.size)
    s = start + first_b.b
    e = start + last_b.b + last_b.size
    return coverage, (s, e)


def find_span_smart(text: str, needle: str) -> Optional[Tuple[int, int]]:
    if not text or not needle:
        return None
    t_orig = text
    t_norm = _normalize_keep_len(text)
    n_norm = _clean_quote_for_match(needle)
    if not n_norm:
        return None
    tl = t_norm.lower()
    nl = n_norm.lower()

    i = tl.find(nl)
    if i != -1:
        s, e = _snap_and_bridge_to_word(t_orig, i, i + len(nl))
        s = _heal_split_word_left(t_orig, s)
        return (s, e)

    m = re.search(re.escape(nl).replace(r"\ ", r"\s+"), tl, flags=re.IGNORECASE)
    if m:
        s, e = _snap_and_bridge_to_word(t_orig, m.start(), m.end())
        s = _heal_split_word_left(t_orig, s)
        return (s, e)

    if not STRICT_MATCH_ONLY and len(nl) >= 12:
        w = max(60, min(240, len(nl) + 80))
        best_cov, best_span = 0.0, None
        step = max(1, w // 2)
        for start in range(0, max(1, len(tl) - w + 1), step):
            cov, se = _fuzzy_window_span(tl, nl, start, w)
            if cov > best_cov:
                best_cov, best_span = cov, se
        if best_span and best_cov >= 0.65:
            s, e = _snap_and_bridge_to_word(t_orig, best_span[0], best_span[1])
            if s > 0 and t_orig[s - 1:s + 1].lower() in {" the", " a", " an"}:
                s -= 1
            s = _heal_split_word_left(t_orig, s)
            return (s, e)

    if not STRICT_MATCH_ONLY:
        keys = [w for w in _tokenize(nl) if len(w) >= 4][:8]
        if len(keys) >= 2:
            kset = set(keys)
            best_score, best_span = 0.0, None
            for s, e, seg in _iter_sentences_with_spans(t_norm):
                toks = set(_tokenize(seg))
                ov = len(kset & toks)
                if ov == 0:
                    continue
                score = ov / max(2, len(kset))
                length_pen = min(1.0, 120 / max(20, e - s))
                score *= (0.6 + 0.4 * length_pen)
                if score > best_score:
                    best_score, best_span = score, (s, min(e, s + 400))
            if best_span and best_score >= 0.35:
                s, e = _snap_and_bridge_to_word(t_orig, best_span[0], best_span[1])
                s = _heal_split_word_left(t_orig, s)
                return (s, e)
    return None


def _is_heading_like(q: str) -> bool:
    if not q:
        return True
    s = q.strip()
    if not re.search(r'[.!?]', s):
        words = re.findall(r"[A-Za-z]+", s)
        if 1 <= len(words) <= 7:
            caps = sum(1 for w in words if w and w[0].isupper())
            if caps / max(1, len(words)) >= 0.8:
                return True
        if s.lower() in {"introduction", "voiceover", "outro", "epilogue", "prologue",
                         "credits", "title", "hook", "horrifying discovery", "final decision"}:
            return True
        if len(s) <= 3:
            return True
    return False


def _is_heading_context(script_text: str, s: int, e: int) -> bool:
    left = script_text.rfind("\n", 0, s) + 1
    right = script_text.find("\n", e)
    right = len(script_text) if right == -1 else right
    line = script_text[left:right].strip()
    if len(line) <= 70 and not re.search(r'[.!?]', line):
        words = re.findall(r"[A-Za-z]+", line)
        if 1 <= len(words) <= 8:
            caps = sum(1 for w in words if w and w[0].isupper())
            if caps / max(1, len(words)) >= 0.7:
                return True
    return False


def _tighten_to_quote(script_text: str, span: Tuple[int, int], quote: str) -> Tuple[int, int]:
    if not span or not quote:
        return span
    s, e = span
    if e <= s or s < 0 or e > len(script_text):
        return span
    window = script_text[s:e]
    win_norm = _normalize_keep_len(window).lower()
    q_norm = _clean_quote_for_match(quote).lower()
    if not q_norm:
        return span
    i = win_norm.find(q_norm)
    if i == -1:
        m = re.search(re.escape(q_norm).replace(r"\ ", r"\s+"), win_norm, flags=re.IGNORECASE)
        if not m:
            return span
        i, j = m.start(), m.end()
    else:
        j = i + len(q_norm)
    s2, e2 = s + i, s + j
    s2, e2 = _snap_and_bridge_to_word(script_text, s2, e2)
    s2 = _heal_split_word_left(script_text, s2)
    if s2 >= s and e2 <= e and e2 > s2:
        return (s2, e2)
    return span


def locate_quote(script_text: str, quote: str) -> Optional[Tuple[int, int]]:
    """Find a single quote's character span in script_text (same matcher as AOIs)."""
    if not quote:
        return None
    cleaned = re.sub(r"^[•\-\d\.\)\s]+", "", sanitize_editor_text(quote)).strip()
    clean = _clean_quote_for_match(cleaned)
    if not clean or _is_heading_like(clean):
        return None
    pos = find_span_smart(script_text, clean)
    if not pos:
        return None
    return _tighten_to_quote(script_text, pos, quote)


def build_spans_by_param(
    script_text: str,
    data: dict,
    heading_ranges: Optional[List[Tuple[int, int]]] = None,
) -> Tuple[Dict[str, List[Tuple[int, int, str, str]]], Dict[str, Tuple[int, int]]]:
    """
    Returns (spans_by_param, aoi_match_ranges).
      spans_by_param: {param: [(start, end, color, aid), ...]}
      aoi_match_ranges: {aid: (start, end)}
    """
    heading_ranges = heading_ranges or []
    raw = (data or {}).get("per_parameter", {}) or {}
    per: Dict[str, Dict[str, Any]] = {k: (v or {}) for k, v in raw.items()}
    spans_map: Dict[str, List[Tuple[int, int, str, str]]] = {p: [] for p in PARAM_ORDER}
    aoi_match_ranges: Dict[str, Tuple[int, int]] = {}

    for p in spans_map.keys():
        color = PARAM_COLORS.get(p, "#ffd54f")
        blk = per.get(p, {}) or {}
        aois = blk.get("areas_of_improvement") or []
        for idx, item in enumerate(aois, start=1):
            raw_q = (item or {}).get("quote_verbatim", "") or ""
            q = sanitize_editor_text(raw_q)
            clean = _clean_quote_for_match(re.sub(r"^[•\-\d\.\)\s]+", "", q).strip())
            if not clean:
                continue
            if _is_heading_like(clean):
                continue
            pos = find_span_smart(script_text, clean)
            if not pos:
                continue
            pos = _tighten_to_quote(script_text, pos, raw_q)
            s, e = pos
            if heading_ranges and _overlaps_any(s, e, heading_ranges):
                continue
            if _is_heading_context(script_text, s, e):
                continue
            aid = f"{p.replace(' ', '_')}-AOI-{idx}"
            spans_map[p].append((s, e, color, aid))
            aoi_match_ranges[aid] = (s, e)
    return spans_map, aoi_match_ranges
