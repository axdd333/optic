from __future__ import annotations

import os
import re
from pathlib import Path


CODE = {
    ".js", ".jsx", ".ts", ".tsx", ".py", ".go", ".rs", ".swift",
    ".java", ".kt", ".c", ".cc", ".cpp", ".h", ".hpp", ".m", ".mm",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".md", ".html",
    ".css", ".scss", ".xml", ".plist",
}
SKIP = {".git", "node_modules", ".venv", "venv", "dist", "build"}
MARKERS = {"package.json", "pyproject.toml", "Cargo.toml", "go.mod"}
REF_RE = re.compile(
    r"(?<![A-Za-z0-9._-])"
    r"([A-Za-z0-9][A-Za-z0-9._/-]{0,120}\."
    r"(?:png|jpg|jpeg|heic|svg|pdf|md|txt|json|csv|db|sqlite|log|"
    r"jsonl|ndjson|js|ts|tsx|py|rs|go|swift|css))"
    r"(?![A-Za-z0-9._/-])"
)


def build(cfg: dict) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for root in roots(cfg):
        for path in files(root):
            add_refs(idx, path)
    return idx


def roots(cfg: dict) -> list[Path]:
    if cfg.get("code_roots"):
        return [Path(p) for p in cfg["code_roots"] if Path(p).exists()]
    home = Path(cfg["home"])
    vals = [home / "Developer" / "Projects",
            home / "Organized_Life" / "Projects",
            home / "Documents" / "Codex"]
    return [p for p in vals if p.exists()]


def files(root: Path):
    for base, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if keep_dir(d, Path(base) / d)]
        for name in names:
            path = Path(base) / name
            if path.suffix.lower() in CODE and safe_size(path):
                yield path


def keep_dir(name: str, path: Path) -> bool:
    if name in SKIP:
        return False
    return path.suffix.lower() not in {".app", ".photoslibrary"}


def safe_size(path: Path) -> bool:
    try:
        return path.stat().st_size <= 2_000_000
    except OSError:
        return False


def add_refs(idx: dict[str, list[str]], path: Path) -> None:
    try:
        txt = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for tok in refs(txt):
        idx.setdefault(tok, []).append(str(path))


def refs(txt: str) -> set[str]:
    return {clean(m.group(1)) for m in REF_RE.finditer(txt)}


def clean(val: str) -> str:
    raw = val.strip(" '\"`()[]{}:,;")
    return Path(raw).name


def referenced(path: Path, idx: dict[str, list[str]]) -> bool:
    keys = {path.name}
    return any(key in idx for key in keys)


def protected_file(path: Path, cfg: dict, idx: dict[str, list[str]]) -> bool:
    if not referenced(path, idx):
        return False
    return project_file(path) or code_file(path, cfg)


def code_file(path: Path, cfg: dict) -> bool:
    return any(inside(path, root) for root in roots(cfg))


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def project_file(path: Path) -> bool:
    for parent in [path.parent, *path.parents]:
        if any((parent / marker).exists() for marker in MARKERS):
            return True
    return False


def evidence(path: Path, idx: dict[str, list[str]]) -> list[str]:
    keys = [path.name]
    vals = []
    for key in keys:
        vals.extend(idx.get(key, [])[:5])
    return list(dict.fromkeys(vals))[:8]
