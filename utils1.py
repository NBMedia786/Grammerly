from __future__ import annotations

import os, re, json, zipfile, xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Iterable

# Optional PDF support
try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None  # type: ignore

# DOCX helpers
from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.text.paragraph import Paragraph
from docx.table import Table

# -------------------- UI order for parameters -------------------- #
PARAM_ORDER: List[str] = [
    "Grammar",
    "Spelling",
    "Punctuation",
    "Style/Clarity",
    "Facts",
]

# -------------------- Sanitizers -------------------- #
_EMOJI_RE = re.compile(
    r'[\U0001F1E0-\U0001F6FF\U0001F900-\U0001FAFF\U00002700-\U000027BF\U0001F300-\U0001F5FF]',
    flags=re.UNICODE
)

def sanitize_editor_text(s: Optional[str]) -> str:
    if not s:
        return ""
    t = str(s)
    t = re.sub(r'\bDecision\s*:\s*', '', t, flags=re.I)
    t = re.sub(r'\bScore\s*[:\-]?\s*\d+(\.\d+)?\b', '', t, flags=re.I)
    t = re.sub(r'^\s*(\(?\d+[\)\.]|\-|\•|\*)\s*', '', t, flags=re.M)
    t = _EMOJI_RE.sub('', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

def _strip_bom(s: str) -> str:
    return s.lstrip("﻿") if s and s.startswith("﻿") else s

def _normalize_text(s: str) -> str:
    if not s:
        return ""
    s = _strip_bom(s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\xa0", " ")
    return s.strip()

# -------------------- DOCX extraction -------------------- #
def _iter_block_items(document: Document):
    parent = document.element.body
    for child in parent.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)

def _paragraph_text_with_breaks(p: Paragraph) -> str:
    parts: List[str] = []
    for run in p.runs:
        if run.text:
            parts.append(run.text)
        for _ in run._r.xpath(".//w:br"):
            parts.append("\n")
    txt = "".join(parts)
    txt = re.sub(r'\n{3,}', '\n\n', txt)
    return txt

def _text_from_paragraph(p: Paragraph) -> str:
    return _paragraph_text_with_breaks(p) or ""

def _text_from_table(tbl: Table) -> str:
    lines: List[str] = []
    for row in tbl.rows:
        row_cells: List[str] = []
        for cell in row.cells:
            cell_bits: List[str] = []
            for para in cell.paragraphs:
                cell_bits.append(_paragraph_text_with_breaks(para))
            for nt in cell._tc.iterchildren():
                if isinstance(nt, CT_Tbl):
                    t = Table(nt, cell._parent)
                    nested = _text_from_table(t)
                    if nested:
                        cell_bits.append(nested)
            row_cells.append("\n".join([cl for cl in cell_bits if cl]))
        line = "  ".join([c for c in row_cells if c])
        lines.append(line)
    return "\n".join([ln for ln in lines if ln.strip()])

def _extract_docx_in_order(docx_path: str) -> str:
    doc = Document(docx_path)
    chunks: List[str] = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            t = _text_from_paragraph(block)
            if t is not None:
                chunks.append(t)
        elif isinstance(block, Table):
            t = _text_from_table(block)
            if t is not None:
                chunks.append(t)
    text = "\n".join(chunks)
    return _normalize_text(text)

def _extract_textboxes_from_docx(docx_path: str) -> str:
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml = z.read("word/document.xml")
    except Exception:
        return ""
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    bits: List[str] = []
    for txbx in root.findall(".//w:txbxContent", ns):
        paras = txbx.findall(".//w:p", ns)
        p_texts: List[str] = []
        for p in paras:
            texts: List[str] = []
            for t in p.findall(".//w:t", ns):
                texts.append(t.text or "")
            p_texts.append("".join(texts))
        if p_texts:
            bits.append("\n".join(p_texts))
    return _normalize_text("\n\n".join(bits))

# -------------------- PDF extraction -------------------- #
def _load_pdf_text(path: str) -> str:
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(path)
        pages_text: List[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            pages_text.append(t)
        return _normalize_text("\n\n".join(pages_text))
    except Exception:
        return ""

# -------------------- Public file loader -------------------- #
def load_script_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return _normalize_text(f.read())
    if ext == ".docx":
        main = _extract_docx_in_order(path)
        tbx = _extract_textboxes_from_docx(path)
        if tbx and tbx not in main:
            main = (main + ("\n\n" if main else "") + tbx).strip()
        return main
    if ext == ".pdf":
        return _load_pdf_text(path)
    return ""

# -------------------- JSON extraction helpers -------------------- #
BEGIN_JSON_TOKEN = "BEGIN_JSON"
END_JSON_TOKEN = "END_JSON"

def _extract_between_tokens(text: str, start_token: str, end_token: str) -> Optional[str]:
    if not text:
        return None
    i = text.find(start_token)
    j = text.rfind(end_token)
    if i == -1 or j == -1 or j <= i:
        return None
    return text[i + len(start_token) : j].strip()

def _extract_fenced_block(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(.*?)\s*```", text, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    return None

def _extract_balanced_json(text: str) -> Optional[str]:
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None

def extract_review_json(model_output: str) -> Optional[Dict[str, Any]]:
    if not model_output:
        return None
    candidates: List[str] = []
    between = _extract_between_tokens(model_output, BEGIN_JSON_TOKEN, END_JSON_TOKEN)
    if between:
        candidates.append(between)
    fenced = _extract_fenced_block(model_output)
    if fenced:
        candidates.append(fenced)
    balanced = _extract_balanced_json(model_output)
    if balanced:
        candidates.append(balanced)
    for s in candidates:
        try:
            return json.loads(s)
        except Exception:
            s2 = re.sub(r",\s*([\]}])", r"\1", s)
            try:
                return json.loads(s2)
            except Exception:
                continue
    return None

# -------------------- AOI normalization for UI -------------------- #
AOI_KEYS: List[str] = ["quote_verbatim", "issue", "fix", "why_this_helps"]

def _clean_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()

def _coerce_aois(block: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = block.get("areas_of_improvement") or []
    if not isinstance(raw, Iterable):
        return []
    out: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        q = _clean_str(item.get("quote_verbatim") or item.get("quote") or item.get("line") or "")
        issue = _clean_str(item.get("issue") or "")
        fix = _clean_str(item.get("fix") or item.get("edit_suggestion") or "")
        why = _clean_str(item.get("why_this_helps") or item.get("why") or "")
        if not (q or issue or fix or why):
            continue
        out.append({
            "quote_verbatim": q[:240] if q else "",
            "issue": issue,
            "fix": fix,
            "why_this_helps": why,
        })
    return out

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
