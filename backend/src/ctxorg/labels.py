from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import time
from pathlib import Path

from . import cfg as cfgmod
from . import db, fs, state as stmod


ATTR = "com.apple.metadata:_kMDItemUserTags"
MAC_DIRS = {
    "Applications", "Desktop", "Documents", "Downloads", "Library",
    "Movies", "Music", "Pictures", "Public", "Sites",
}


def plan(conn, cfg: dict, run_id: str) -> list[dict]:
    rows = rows_for(conn, cfg, run_id)
    out = [make(rec) for rec in rows]
    db.json_dump(path(cfg, run_id), out)
    return out


def rows_for(conn, cfg: dict, run_id: str) -> list[dict]:
    moves = db.plan_rows(conn, run_id)
    if moves:
        return [move_row(r) for r in moves if r["state"] == stmod.PLANNED]
    return item_rows(conn, cfg)


def move_row(rec: dict) -> dict:
    return {"id": rec["id"], "path": rec["src"],
            "dst": rec["dst"], "area": rel_area(rec["dst"]),
            "cluster": rec["cluster"], "why": rec["why"]}


def item_rows(conn, cfg: dict) -> list[dict]:
    rows = db.rows(conn, "SELECT * FROM items WHERE state='EXTRACTED'")
    lim = int(cfg.get("label_item_limit", 2000))
    return [{"id": r["id"], "path": r["path"], "area": "NeedsReview",
             "cluster": r["cluster"], "why": "context graph"}
            for r in rows[:lim]]


def make(rec: dict) -> dict:
    tags = ["ContextOrganizer", area_tag(rec), folder_tag(rec),
            cluster_tag(rec)]
    return {"id": rec["id"], "path": rec["path"], "tags": clean(tags),
            "dst": rec.get("dst", ""), "area": rec.get("area", ""),
            "why": rec.get("why", ""), "state": "LABEL_PLANNED"}


def area_tag(rec: dict) -> str:
    return "Area:" + fs.safe_name(rec.get("area", "NeedsReview"))


def folder_tag(rec: dict) -> str:
    area = str(rec.get("area", "NeedsReview")).split("/", 1)[0]
    return "Folder:" + fs.safe_name(area, "NeedsReview")


def cluster_tag(rec: dict) -> str:
    cid = str(rec.get("cluster", ""))[:8] or "unknown"
    return "Cluster:" + cid


def clean(tags: list[str]) -> list[str]:
    vals = [tag_safe(t) for t in tags]
    return list(dict.fromkeys(vals))


def tag_safe(tag: str) -> str:
    val = str(tag).replace("/", " ")
    return " ".join(val.split())[:96] or "ContextOrganizer"


def apply(cfg: dict, run_id: str) -> int:
    rows = load(path(cfg, run_id))
    out = [apply_one(rec) for rec in rows]
    db.json_dump(applied_path(cfg, run_id), out)
    return len(out)


def apply_one(rec: dict) -> dict:
    try:
        target = tag_path(rec)
        before, had = tag_meta(target)
        after = list(dict.fromkeys(before + rec["tags"]))
        set_tags(target, after)
        return dict(rec, before=before, after=after,
                    before_exists=had, applied_path=target,
                    state="LABELED", ts=time.time())
    except Exception as exc:
        return dict(rec, state="LABEL_DEAD", err=str(exc)[:500])


def rollback(cfg: dict, run_id: str) -> int:
    rows = load(applied_path(cfg, run_id))
    return sum(rollback_one(r) for r in rows)


def rollback_one(rec: dict) -> int:
    if "before" not in rec:
        return 0
    target = rollback_path(rec)
    if not Path(target).exists():
        return 0
    restore_tags(target, rec)
    return 1


def read_tags(path_: str) -> list[str]:
    return tag_meta(path_)[0]


def can_xattr() -> bool:
    return hasattr(os, "setxattr") or shutil.which("xattr") is not None


def tag_meta(path_: str) -> tuple[list[str], bool]:
    try:
        raw = tag_bytes(path_)
        vals = plistlib.loads(raw)
        return [str(v) for v in vals if str(v)], True
    except (OSError, subprocess.CalledProcessError):
        return [], False
    except plistlib.InvalidFileException:
        return [], True


def tag_bytes(path_: str) -> bytes:
    if hasattr(os, "getxattr"):
        return os.getxattr(path_, ATTR)
    proc = subprocess.run(["xattr", "-px", ATTR, path_],
                          capture_output=True, text=True, check=True)
    return bytes.fromhex("".join(proc.stdout.split()))


def set_tags(path_: str, tags: list[str]) -> None:
    raw = plistlib.dumps(tags)
    if hasattr(os, "setxattr"):
        os.setxattr(path_, ATTR, raw)
        return
    subprocess.run(["xattr", "-wx", ATTR, raw.hex(), path_], check=True)


def tag_path(rec: dict) -> str:
    for key in ("path", "dst"):
        val = rec.get(key)
        if val and Path(val).exists():
            return str(val)
    return str(rec["path"])


def rollback_path(rec: dict) -> str:
    vals = [rec.get("applied_path"), rec.get("dst"), rec.get("path")]
    for val in vals:
        if val and Path(val).exists():
            return str(val)
    return str(rec.get("applied_path") or rec["path"])


def restore_tags(path_: str, rec: dict) -> None:
    if rec.get("before_exists", True):
        set_tags(path_, rec["before"])
        return
    try:
        remove_tags(path_)
    except (OSError, subprocess.CalledProcessError):
        return


def remove_tags(path_: str) -> None:
    if hasattr(os, "removexattr"):
        os.removexattr(path_, ATTR)
        return
    subprocess.run(["xattr", "-d", ATTR, path_], check=True)


def load(path_: Path) -> list[dict]:
    txt = path_.read_text(encoding="utf-8")
    return [json.loads(x) for x in txt.splitlines() if x.strip()]


def path(cfg: dict, run_id: str) -> Path:
    return cfgmod.state_dir(cfg, "labels") / f"{run_id}.ndjson"


def applied_path(cfg: dict, run_id: str) -> Path:
    return cfgmod.state_dir(cfg, "labels") / f"{run_id}.applied.ndjson"


def rel_area(dst: str) -> str:
    parts = Path(dst).parts
    for idx, part in enumerate(parts):
        if part in MAC_DIRS:
            return "/".join(area_parts(parts, idx)) or part
    return "NeedsReview"


def area_parts(parts: tuple[str, ...], idx: int) -> tuple[str, ...]:
    vals = parts[idx:idx + 2]
    if len(vals) < 2:
        return vals
    if Path(vals[1]).suffix:
        return vals[:1]
    return vals
