from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from . import cfg as cfgmod
from . import fs, log


CACHE_DIRS = {
    ".cache", ".next", ".pytest_cache", ".ruff_cache", ".turbo",
    ".venv", "__pycache__", "build", "dist", "node_modules", "venv",
}
CACHE_FILES = {".DS_Store", ".localized"}
SCAFFOLD_DIRS = {
    "Archives", "Documents", "Downloads", "Movies", "Music",
    "Pictures", "Projects", "System", "Timeline",
}


def plan(cfg: dict, run: str) -> list[dict]:
    rows = scan(cfg, run)
    path = root(cfg) / f"{run}.ndjson"
    dump(path, rows)
    log.info("cleanup_plan_done", run=run, count=len(rows))
    return rows


def apply(cfg: dict, run: str) -> list[dict]:
    rows = load(root(cfg) / f"{run}.ndjson")
    out = [apply_one(cfg, run, rec) for rec in rows]
    dump(root(cfg) / f"{run}.applied.ndjson", out)
    log.info("cleanup_apply_done", run=run, count=len(out))
    return out


def rollback(cfg: dict, run: str) -> list[dict]:
    rows = list(reversed(load(root(cfg) / f"{run}.applied.ndjson")))
    out = [rollback_one(rec) for rec in rows if rec.get("trash")]
    dump(root(cfg) / f"{run}.rollback.ndjson", out)
    log.info("cleanup_rollback_done", run=run, count=len(out))
    return out


def scan(cfg: dict, run: str) -> list[dict]:
    rows: list[dict] = []
    for src in cfg.get("sources", []):
        rows.extend(scan_root(Path(src), cfg, run))
    return sorted(dedupe(rows), key=lambda r: r["path"])


def scan_root(src: Path, cfg: dict, run: str) -> list[dict]:
    if skip(src, cfg):
        return []
    if src.is_symlink():
        return link_row(src, run)
    if src.is_file():
        return file_row(src, cfg, run)
    if src.is_dir():
        return scan_dir(src, cfg, run)
    return []


def scan_dir(src: Path, cfg: dict, run: str) -> list[dict]:
    rows: list[dict] = []
    for base, dirs, files in os.walk(src, topdown=True, followlinks=False):
        rows.extend(scan_base(Path(base), dirs, files, cfg, run))
    return rows


def scan_base(base: Path, dirs: list[str], files: list[str],
              cfg: dict, run: str) -> list[dict]:
    rows = row_for_dir(base, cfg, run)
    dirs[:] = keep_dirs(base, dirs, cfg, rows, run)
    rows.extend(file_rows(base, files, cfg, run))
    return rows


def keep_dirs(base: Path, dirs: list[str], cfg: dict,
              rows: list[dict], run: str = "") -> list[str]:
    keep = []
    for name in dirs:
        path = base / name
        if add_pruned_dir(path, cfg, rows, run):
            continue
        keep.append(name)
    return keep


def add_pruned_dir(path: Path, cfg: dict, rows: list[dict],
                   run: str) -> bool:
    if skip(path, cfg):
        return True
    if path.is_symlink():
        rows.extend(link_row(path, run))
        return True
    rec = dir_row(path, cfg, run)
    if not rec:
        return False
    rows.append(rec)
    return True


def row_for_dir(path: Path, cfg: dict, run: str) -> list[dict]:
    rec = dir_row(path, cfg, run)
    return [rec] if rec else []


def dir_row(path: Path, cfg: dict, run: str) -> dict | None:
    if cache_dir(path, cfg):
        return rec(path, "trash", "cache_dir", run)
    if empty_scaffold(path, cfg):
        return rec(path, "trash", "empty_scaffold", run)
    if empty_dir(path, cfg):
        return rec(path, "trash", "empty_dir", run)
    return None


def file_rows(base: Path, files: list[str], cfg: dict,
              run: str) -> list[dict]:
    rows = []
    for name in files:
        rows.extend(scan_root(base / name, cfg, run))
    return rows


def file_row(path: Path, cfg: dict, run: str) -> list[dict]:
    if cache_file(path, cfg):
        return [rec(path, "trash", "cache_file", run)]
    return []


def link_row(path: Path, run: str) -> list[dict]:
    if path.exists():
        return []
    return [rec(path, "trash", "broken_link", run)]


def cache_dir(path: Path, cfg: dict) -> bool:
    names = set(cfg.get("cleanup_cache_dirs", CACHE_DIRS))
    return path.name in names


def cache_file(path: Path, cfg: dict) -> bool:
    names = set(cfg.get("cleanup_cache_files", CACHE_FILES))
    return path.name in names or path.suffix == ".pyc"


def empty_scaffold(path: Path, cfg: dict) -> bool:
    names = set(cfg.get("cleanup_scaffold_dirs", SCAFFOLD_DIRS))
    org = Path(cfg.get("organized_root", Path.home() / "Organized_Life"))
    return under(path, org) and path.name in names and empty_dir(path, cfg)


def empty_dir(path: Path, cfg: dict) -> bool:
    if not path.is_dir() or path.is_symlink():
        return False
    if not allow_empty(path, cfg):
        return False
    try:
        return not any(path.iterdir())
    except OSError:
        return False


def allow_empty(path: Path, cfg: dict) -> bool:
    if fs.protected(str(path), cfg):
        return False
    roots = [Path(p) for p in cfg.get("sources", [])]
    return any(under(path, root) and path != root for root in roots)


def skip(path: Path, cfg: dict) -> bool:
    names = cfg.get("skip_names", [])
    return fs.protected(str(path), cfg) or path.name in names


def rec(path: Path, act: str, why: str, run: str) -> dict:
    return {"id": fs.item_id(str(path)), "run": run, "path": str(path),
            "action": act, "why": why, "state": "PLANNED"}


def dedupe(rows: list[dict]) -> list[dict]:
    out = {}
    for rec_ in rows:
        out[rec_["path"]] = rec_
    return list(out.values())


def apply_one(cfg: dict, run: str, rec_: dict) -> dict:
    try:
        trash = trash_path(cfg, run, rec_["path"])
        move_to_trash(rec_["path"], trash)
        return done(rec_, "VERIFIED", trash=str(trash))
    except Exception as exc:
        return done(rec_, "DEAD_LETTER", err=str(exc))


def rollback_one(rec_: dict) -> dict:
    try:
        restore(rec_["trash"], rec_["path"])
        return done(rec_, "ROLLED_BACK")
    except Exception as exc:
        return done(rec_, "DEAD_LETTER", err=str(exc))


def move_to_trash(src: str, dst: Path) -> None:
    if not Path(src).exists() and not Path(src).is_symlink():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)


def restore(src: str, dst: str) -> None:
    if Path(dst).exists() or Path(dst).is_symlink():
        raise FileExistsError(dst)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)


def trash_path(cfg: dict, run: str, src: str) -> Path:
    base = Path(cfg.get("trash_dir", Path.home() / ".Trash"))
    path = base / f"ctxorg-{run}" / Path(src).name
    return unique(path)


def unique(path: Path) -> Path:
    if not path.exists() and not path.is_symlink():
        return path
    stem, suffix = path.with_suffix(""), path.suffix
    return unique(Path(f"{stem}-{int(time.time() * 1000)}{suffix}"))


def done(rec_: dict, st: str, **vals: object) -> dict:
    out = dict(rec_, state=st, ts=time.time())
    out.update(vals)
    return out


def root(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg, "cleanup")


def dump(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec_ in rows:
            fh.write(json.dumps(rec_, sort_keys=True) + "\n")


def load(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.expanduser().resolve())
        return True
    except ValueError:
        return False
