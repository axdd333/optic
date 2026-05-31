from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path


BAD = re.compile(r"[^A-Za-z0-9._ -]+")
PKG_EXTS = {".app", ".photoslibrary", ".musiclibrary", ".pages",
            ".numbers", ".key", ".rtfd"}


def item_id(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:24]


def safe_name(name: str, default: str = "Item") -> str:
    clean = BAD.sub(" ", name).strip(" ._-")
    clean = re.sub(r"\s+", " ", clean)
    return clean[:96] or default


def inside(path: str, root: str) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def protected(path: str, cfg: dict) -> bool:
    if allowed(path, cfg):
        return False
    return any(inside(path, p) or same(path, p) for p in cfg["protected"])


def allowed(path: str, cfg: dict) -> bool:
    vals = cfg.get("protected_allow", [])
    return any(inside(path, p) or same(path, p) for p in vals)


def same(a: str, b: str) -> bool:
    return Path(a).resolve() == Path(b).resolve()


def project_dir(path: str, cfg: dict) -> bool:
    try:
        names = {p.name for p in Path(path).iterdir()}
    except OSError:
        return False
    return bool(names.intersection(cfg.get("project_markers", [])))


def walk(cfg: dict) -> list[dict]:
    rows = []
    for root in cfg["sources"]:
        rows.extend(walk_root(root, cfg))
        if full(rows, cfg):
            break
    return rows


def walk_root(root: str, cfg: dict) -> list[dict]:
    if not Path(root).exists() or protected(root, cfg):
        return []
    if Path(root).is_file():
        return [stat_item(root, cfg, "file")]
    return walk_tree(root, cfg)


def walk_tree(root: str, cfg: dict) -> list[dict]:
    rows = []
    for base, dirs, files in os.walk(root):
        rows.extend(packages(base, dirs, cfg))
        dirs[:] = keep_dirs(base, dirs, cfg)
        if base != root and project_dir(base, cfg):
            rows.append(stat_item(base, cfg, "dir"))
            dirs[:] = []
            continue
        rows.extend(stat_item(str(Path(base) / f), cfg, "file") for f in files)
        if full(rows, cfg):
            break
    return [r for r in rows if r]


def full(rows: list, cfg: dict) -> bool:
    cap = int(cfg.get("max_scan_items", 0) or 0)
    return cap > 0 and len(rows) >= cap


def keep_dirs(base: str, dirs: list[str], cfg: dict) -> list[str]:
    skip = set(cfg.get("skip_names", [])) | set(cfg.get("prune_dirs", []))
    out = []
    for name in dirs:
        path = str(Path(base) / name)
        if name not in skip and not package(path) and not protected(path, cfg):
            out.append(name)
    return out


def packages(base: str, dirs: list[str], cfg: dict) -> list[dict]:
    rows = []
    for name in dirs:
        path = str(Path(base) / name)
        if package(path) and not protected(path, cfg):
            rows.append(stat_item(path, cfg, "dir"))
    return [r for r in rows if r]


def package(path: str) -> bool:
    return Path(path).suffix.lower() in PKG_EXTS


def stat_item(path: str, cfg: dict, kind: str) -> dict | None:
    if Path(path).name in cfg.get("skip_names", []):
        return None
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return item(path, kind, st.st_size, st.st_mtime)


def item(path: str, kind: str, sz: int, mtime: float) -> dict:
    ext = Path(path).suffix.lower() if kind == "file" else ""
    return {"id": item_id(path), "path": path, "kind": kind,
            "size": sz, "mtime": mtime, "ext": ext}


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.with_suffix(""), path.suffix
    idx = 2
    while True:
        cand = Path(f"{stem}-{idx}{suffix}")
        if not cand.exists():
            return cand
        idx += 1


def free_gb(path: str) -> float:
    usage = shutil.disk_usage(path)
    return usage.free / 1024 / 1024 / 1024
