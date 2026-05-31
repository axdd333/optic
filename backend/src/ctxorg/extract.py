from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import cmd

TEXT = {".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".log"}
IMG = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}
DOC = {".doc", ".docx", ".rtf", ".pages"}


def extract(rec: dict, cfg: dict) -> str:
    path = Path(rec["path"])
    if rec["kind"] == "dir":
        return dir_text(path, cfg)
    ext = rec["ext"]
    if ext in TEXT:
        return read_text(path, cfg)
    if ext == ".pdf":
        return pdf_text(path, cfg)
    if ext in IMG:
        return ocr_img(path, cfg)
    if ext in DOC:
        return office_text(path, cfg)
    return meta_text(path)


def cap(txt: str, cfg: dict) -> str:
    return txt.replace("\x00", "")[: int(cfg["max_text_chars"])]


def read_text(path: Path, cfg: dict) -> str:
    lim = int(cfg["max_read_mb"]) * 1024 * 1024
    with path.open("rb") as fh:
        buf = fh.read(lim)
    return cap(buf.decode("utf-8", "ignore"), cfg)


def pdf_text(path: Path, cfg: dict) -> str:
    txt = cmd.run(["pdftotext", str(path), "-"], int(cfg["cmd_timeout_sec"]))
    if len(txt.strip()) > 160:
        return cap(txt, cfg)
    return cap(txt + "\n" + ocr_pdf(path, cfg), cfg)


def ocr_pdf(path: Path, cfg: dict) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "page")
        pages = str(int(cfg["ocr_pdf_pages"]))
        cmd.run(["pdftoppm", "-f", "1", "-l", pages, "-png",
                 str(path), base], int(cfg["cmd_timeout_sec"]))
        imgs = sorted(Path(tmp).glob("*.png"))
        return "\n".join(ocr_img(p, cfg) for p in imgs)


def ocr_img(path: Path, cfg: dict) -> str:
    txt = cmd.run(["tesseract", str(path), "stdout", "-l", "eng"],
                  int(cfg["cmd_timeout_sec"]))
    return cap(txt, cfg)


def office_text(path: Path, cfg: dict) -> str:
    txt = cmd.run(["textutil", "-convert", "txt", "-stdout", str(path)],
                  int(cfg["cmd_timeout_sec"]))
    return cap(txt, cfg)


def dir_text(path: Path, cfg: dict) -> str:
    names = project_files()
    parts = [f"folder: {path.name}", git_remote(path)]
    parts.extend(read_child(path / name, cfg) for name in names)
    parts.append(package_summary(path))
    return cap("\n".join(p for p in parts if p), cfg)


def project_files() -> list[str]:
    return [
        "README.md", "package.json", "pyproject.toml", "Cargo.toml",
        "go.mod", "Package.swift", ".git/config",
    ]


def git_remote(path: Path) -> str:
    cfg = path / ".git" / "config"
    if not cfg.exists():
        return ""
    txt = cfg.read_text(encoding="utf-8", errors="ignore")
    lines = [x.strip() for x in txt.splitlines() if "url =" in x]
    return "\n".join(f"git_remote: {x}" for x in lines[:4])


def package_summary(path: Path) -> str:
    pkg = path / "package.json"
    if not pkg.exists():
        return ""
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    vals = {k: data.get(k) for k in ("name", "description", "version")}
    return "package_summary: " + json.dumps(vals, sort_keys=True)


def read_child(path: Path, cfg: dict) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return f"\n--- {path.name} ---\n{read_text(path, cfg)}"


def meta_text(path: Path) -> str:
    return f"name: {path.name}\npath: {path}\next: {path.suffix}"
