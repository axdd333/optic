from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from . import cfg as cfgmod


IMG = {".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff", ".webp"}
TAGS = "com.apple.metadata:_kMDItemUserTags"
SETTLED = "SETTLED"
PLANNED = "PLANNED"
WAITING = "WAITING_DATALess"
STOP = {
    "screenshot", "screenshots", "screen", "shot", "capture", "media",
    "png", "jpg", "jpeg", "desktop", "archive", "personal", "assets",
    "cursor", "project", "projects", "image", "images", "imported",
    "organized", "life", "users", "ahmedm", "am", "pm", "at",
}


def plan(cfg: dict, run: str) -> list[dict]:
    rows = rows_for(cfg, run)
    dump(root(cfg) / f"{run}.ndjson", rows)
    return rows


def apply(cfg: dict, run: str) -> list[dict]:
    rows = load(root(cfg) / f"{run}.ndjson")
    out = [apply_one(rec) for rec in rows]
    dump(root(cfg) / f"{run}.applied.ndjson", out)
    return out


def rollback(cfg: dict, run: str) -> list[dict]:
    rows = list(reversed(load(root(cfg) / f"{run}.applied.ndjson")))
    out = [roll_one(rec) for rec in rows if rec["state"] == "VERIFIED"]
    dump(root(cfg) / f"{run}.rollback.ndjson", out)
    return out


def rows_for(cfg: dict, run: str) -> list[dict]:
    used: set[str] = set()
    return [row(cfg, run, p, used) for p in candidates(cfg)]


def candidates(cfg: dict) -> list[Path]:
    vals = []
    for base in scan_roots(cfg):
        vals.extend(p for p in files(base) if is_screen(p))
    return sorted(set(vals))


def files(base: Path):
    for root, dirs, names in os.walk(base):
        dirs[:] = [d for d in dirs if not package(Path(root) / d)]
        for name in names:
            yield Path(root) / name


def package(path: Path) -> bool:
    return path.suffix.lower() in {".photoslibrary", ".app", ".musiclibrary"}


def scan_roots(cfg: dict) -> list[Path]:
    home = Path(cfg["home"])
    vals = [home / "Desktop", home / "Downloads", home / "Pictures"]
    return [p for p in vals if p.exists()]


def is_screen(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in IMG:
        return False
    name = path.name.lower()
    return "screenshot" in name or "screen shot" in name or xattr_screen(path)


def xattr_screen(path: Path) -> bool:
    proc = subprocess.run(["xattr", str(path)], capture_output=True,
                          text=True)
    return "kMDItemIsScreenCapture" in proc.stdout


def row(cfg: dict, run: str, path: Path, used: set[str]) -> dict:
    dst = dst_for(cfg, path, used)
    used.add(str(dst))
    st = state(cfg, path, dst)
    return {"run": run, "src": str(path), "dst": str(dst),
            "state": st, "why": why(path)}


def dst_for(cfg: dict, path: Path, used: set[str]) -> Path:
    if in_screens(cfg, path) and semantic(path):
        return path
    return unique(dest(cfg, path), used, path)


def state(cfg: dict, path: Path, dst: Path) -> str:
    if dataless(path):
        return WAITING
    if settled(cfg, path, dst):
        return SETTLED
    return PLANNED


def settled(cfg: dict, path: Path, dst: Path) -> bool:
    return in_screens(cfg, path) and same(path, dst)


def in_screens(cfg: dict, path: Path) -> bool:
    base = Path(cfg["home"]) / "Pictures" / "Screenshots"
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def dest(cfg: dict, path: Path) -> Path:
    if in_screens(cfg, path) and semantic(path):
        return path
    year = stamp(path)[:4]
    return Path(cfg["home"]) / "Pictures" / "Screenshots" / year / name(path)


def semantic(path: Path) -> bool:
    name = path.stem.lower()
    return bool(re.match(r"20\d\d-\d\d-\d\d-.+-screenshot(-\d+)?$", name))


def name(path: Path) -> str:
    base = "-".join([stamp(path), slug(path), "screenshot"])
    return f"{base}{path.suffix.lower()}"


def slug(path: Path) -> str:
    toks = [t for t in tokens(path.stem) if keep(t)]
    return "-".join(toks[:7]) or "screen-capture"


def tokens(txt: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9]+", txt)]


def keep(tok: str) -> bool:
    if tok in STOP or tok.isdigit() or re.fullmatch(r"[0-9a-f]{8,}", tok):
        return False
    return len(tok) > 2 and not re.fullmatch(r"20\d\d", tok)


def stamp(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def why(path: Path) -> str:
    return "screen capture xattr" if xattr_screen(path) else "screenshot name"


def unique(dst: Path, used: set[str], src: Path) -> Path:
    if str(dst) not in used and same_or_free(dst, src):
        return renamed(dst, src)
    return unique_idx(dst.with_suffix(""), dst.suffix, used, src)


def same_or_free(dst: Path, src: Path) -> bool:
    return not dst.exists() or same(dst, src)


def renamed(dst: Path, src: Path) -> Path:
    if same(dst, src):
        return dst.with_name(dst.stem + "-renamed" + dst.suffix)
    return dst


def same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def unique_idx(stem: Path, suffix: str, used: set[str], src: Path) -> Path:
    idx = 2
    while True:
        cand = Path(f"{stem}-{idx}{suffix}")
        if str(cand) not in used and same_or_free(cand, src):
            return renamed(cand, src)
        idx += 1


def apply_one(rec: dict) -> dict:
    try:
        if rec["state"] == SETTLED:
            return done(rec, SETTLED)
        if rec["state"] == WAITING:
            mark_waiting(Path(rec["src"]))
            return done(rec, WAITING)
        move(rec)
        return done(rec, "VERIFIED")
    except Exception as exc:
        return done(rec, "DEAD_LETTER", err=str(exc)[:500])


def move(rec: dict) -> None:
    src, dst = Path(rec["src"]), Path(rec["dst"])
    if dataless(src):
        raise RuntimeError("dataless iCloud/FileProvider placeholder")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)


def dataless(path: Path) -> bool:
    proc = subprocess.run(["stat", "-f", "%Sf", str(path)],
                          capture_output=True, text=True)
    return "dataless" in proc.stdout


def mark_waiting(path: Path) -> None:
    tags = ["ContextOrganizer", "Area:Pictures Screenshots",
            "State:WaitingDataless"]
    set_tags(path, merged_tags(path, tags))


def set_tags(path: Path, tags: list[str]) -> None:
    raw = plistlib.dumps(tags)
    if hasattr(os, "setxattr"):
        os.setxattr(path, TAGS, raw)
        return
    subprocess.run(["xattr", "-wx", TAGS, raw.hex(), str(path)], check=True)


def merged_tags(path: Path, tags: list[str]) -> list[str]:
    vals = existing_tags(path)
    return list(dict.fromkeys(vals + tags))


def existing_tags(path: Path) -> list[str]:
    try:
        raw = tag_bytes(path)
        return [str(v) for v in plistlib.loads(raw) if str(v)]
    except (OSError, plistlib.InvalidFileException,
            subprocess.CalledProcessError):
        return []


def tag_bytes(path: Path) -> bytes:
    if hasattr(os, "getxattr"):
        return os.getxattr(path, TAGS)
    proc = subprocess.run(["xattr", "-px", TAGS, str(path)],
                          capture_output=True, text=True, check=True)
    return bytes.fromhex("".join(proc.stdout.split()))


def roll_one(rec: dict) -> dict:
    try:
        shutil.move(rec["dst"], rec["src"])
        return done(rec, "ROLLED_BACK")
    except Exception as exc:
        return done(rec, "DEAD_LETTER", err=str(exc)[:500])


def done(rec: dict, st: str, **vals: object) -> dict:
    out = dict(rec, state=st, ts=time.time())
    out.update(vals)
    return out


def root(cfg: dict) -> Path:
    return cfgmod.state_dir(cfg, "screenshots")


def dump(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")


def load(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
