from __future__ import annotations

from collections import Counter
import re

STOP = {
    "the", "and", "for", "with", "from", "this", "that", "you", "your",
    "are", "was", "were", "have", "has", "not", "but", "all", "file",
    "files", "image", "screen", "screenshot", "document", "page",
}

CODE_EXTS = {
    ".c", ".cc", ".cpp", ".css", ".go", ".h", ".hpp", ".html", ".java",
    ".js", ".json", ".jsx", ".kt", ".m", ".mm", ".php", ".py", ".rb",
    ".rs", ".scss", ".sh", ".swift", ".toml", ".ts", ".tsx", ".xml",
    ".yaml", ".yml",
}

DOC_EXTS = {
    ".csv", ".doc", ".docx", ".md", ".markdown", ".pages", ".pdf", ".rtf",
    ".rst", ".tsv", ".txt", ".xls", ".xlsx",
}

OCR_EXTS = {
    ".bmp", ".gif", ".jpeg", ".jpg", ".key", ".pdf", ".png", ".tif",
    ".tiff", ".webp",
}

MEDIA_EXTS = {
    ".aiff", ".heic", ".m4a", ".m4v", ".mov", ".mp3", ".mp4", ".wav",
}

PROJ_NAMES = {
    "cargo.toml", "go.mod", "package.json", "package.swift",
    "pyproject.toml", "readme.md",
}


def toks(txt: str) -> set[str]:
    out = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", txt.lower()):
        val = raw.strip("_-")
        if val not in STOP and len(val) > 2:
            out.add(val[:48])
    return out


def sig(rec: dict) -> set[str]:
    txt = " ".join([rec.get("path", ""), rec.get("text", "")])
    return toks(txt)


def summary(txt: str, lim: int) -> str:
    return re.sub(r"\s+", " ", txt).strip()[:lim]


def top_toks(txt: str, lim: int) -> list[tuple[str, int]]:
    vals = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", str(txt).lower())
    clean = [v.strip("_-")[:48] for v in vals]
    keep = [v for v in clean if v not in STOP and len(v) > 2]
    return Counter(keep).most_common(max(0, lim))


def ext_type(ext: str) -> str:
    val = str(ext).lower()
    if val in CODE_EXTS:
        return "code"
    if val in DOC_EXTS:
        return "doc"
    if val in OCR_EXTS:
        return "ocr"
    return "media" if val in MEDIA_EXTS else "other"


def is_code(rec: dict) -> bool:
    return ext_type(str(rec.get("ext", ""))) == "code"


def is_ocr(rec: dict) -> bool:
    return str(rec.get("ext", "")).lower() in OCR_EXTS


def is_project_name(name: str) -> bool:
    return str(name).lower() in PROJ_NAMES
