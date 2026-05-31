from __future__ import annotations

import re
import datetime as dt
from pathlib import Path

from . import cfg as cfgmod
from . import db, fs, state
from . import terms


DOC_EXTS = {".pdf", ".doc", ".docx", ".rtf", ".pages", ".md", ".txt"}
DOC_EXTS |= {".numbers", ".key"}
IMG_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff",
            ".heic", ".photoslibrary"}
VID_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".webm"}
VID_EXTS |= {".imovielibrary"}
AUD_EXTS = {".mp3", ".m4a", ".wav", ".aiff", ".flac", ".aac"}
AUD_EXTS |= {".logicx", ".band"}
ARC_EXTS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".swift", ".java"}
CACHE = {".cache", "__pycache__", ".next", "dist", "build", ".build"}
VENDOR = {"node_modules", ".venv", "venv", ".pnpm-store", ".npm"}
TOOLS = {"google-cloud-sdk", ".rustup", ".cargo", ".local", "site-packages"}
SYS = {".git", ".DS_Store", ".Trash", "Library", ".ollama", ".codex"}
MARKERS = {"package.json", "pyproject.toml", "Cargo.toml", "go.mod"}
PKG_EXTS = {".app", ".pages", ".key", ".numbers", ".photoslibrary",
            ".xcodeproj", ".xcworkspace", ".playground", ".rtfd",
            ".imovielibrary", ".logicx", ".band"}
NAME_STOP = {"ahmedm", "users", "organized_life", "organized", "life",
             "archives", "archive", "legacy", "imported", "ultimate"}


def run(conn, cfg: dict, run_id: str) -> list[dict]:
    rows = db.items(conn)
    units = grouped(rows)
    plans = dedupe([plan_unit(cfg, src, vals) for src, vals in units.items()])
    save(conn, cfg, run_id, plans)
    return plans


def grouped(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for rec in rows:
        out.setdefault(unit_key(rec), []).append(rec)
    return drop_nested(out)


def unit_key(rec: dict) -> str:
    path = Path(rec["path"])
    if rec["kind"] == "dir":
        return str(path)
    root = rooted(path, PKG_EXTS, by_suffix=True)
    if root:
        return str(root)
    root = rooted(path, CACHE | VENDOR | TOOLS, by_suffix=False)
    return str(root or path)


def rooted(path: Path, vals: set[str], by_suffix: bool) -> Path | None:
    for part in [path, *path.parents]:
        key = part.suffix.lower() if by_suffix else part.name
        if key in vals:
            return part
    return None


def drop_nested(units: dict[str, list[dict]]) -> dict[str, list[dict]]:
    kept: dict[str, list[dict]] = {}
    for key in sorted(units, key=lambda p: len(Path(p).parts)):
        if has_parent(key, kept):
            continue
        kept[key] = units[key]
    return kept


def has_parent(key: str, vals: dict[str, list[dict]]) -> bool:
    path = Path(key)
    return any(parent in vals for parent in map(str, path.parents))


def plan_unit(cfg: dict, src: str, vals: list[dict]) -> dict:
    if len(vals) == 1 and vals[0]["path"] == src:
        return plan(cfg, vals[0])
    return plan(cfg, synth(src, vals))


def synth(src: str, vals: list[dict]) -> dict:
    rec = vals[0]
    text = " ".join(v.get("text", "") for v in vals[:8])
    return {"id": fs.item_id(src), "path": src, "kind": "dir",
            "size": sum(int(v.get("size", 0)) for v in vals),
            "mtime": max(float(v.get("mtime", 0)) for v in vals),
            "ext": Path(src).suffix.lower() or dominant_ext(vals),
            "state": rec.get("state", ""),
            "text": text, "cluster": rec.get("cluster", "")}


def dominant_ext(vals: list[dict]) -> str:
    names = [Path(v["path"]).suffix.lower() for v in vals]
    counts = {ext: names.count(ext) for ext in set(names) if ext}
    if counts:
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return ""


def plan(cfg: dict, rec: dict) -> dict:
    if is_protected(rec, cfg):
        return mark(rec, "protected path")
    if is_pruned_noise(rec, cfg):
        return mark(rec, "delete candidate or ignored noise")
    dst, why = choose(cfg, rec)
    if same_place(rec["path"], str(dst)):
        return rec_plan(rec, str(dst), state.VERIFIED, "already in place")
    return rec_plan(rec, str(dst), state.PLANNED, why)


def is_protected(rec: dict, cfg: dict) -> bool:
    vals = cfg.get("protected", [])
    return bool(vals) and fs.protected(rec["path"], cfg)


def is_pruned_noise(rec: dict, cfg: dict) -> bool:
    pruned = set(cfg.get("prune_dirs", [])) - CACHE - VENDOR - SYS
    parts = set(path_parts(rec))
    return bool(parts & pruned) or bool(parts & CACHE)


def mark(rec: dict, why: str) -> dict:
    return rec_plan(rec, rec["path"], state.DEAD, why)


def rec_plan(rec: dict, dst: str, st: str, why: str) -> dict:
    return {"id": rec["id"], "src": rec["path"], "dst": dst,
            "state": st, "why": why[:160], "cluster": rec.get("cluster", "")}


def choose(cfg: dict, rec: dict) -> tuple[Path, str]:
    rel, why = route(cfg, rec)
    name = item_name(rec)
    dst = safe_dst(cfg, rel) / name
    return dst, why


def route(cfg: dict, rec: dict) -> tuple[str, str]:
    hook = model_hook(cfg, rec)
    if hook:
        return hook
    if tooling(rec):
        return tool_route(rec)
    if rec.get("ext") in IMG_EXTS | VID_EXTS | AUD_EXTS | DOC_EXTS:
        return content_route(rec)
    if project(rec):
        return "Developer/Projects", "project metadata"
    return content_route(rec)


def model_hook(cfg: dict, rec: dict) -> tuple[str, str] | None:
    hooks = cfg.get("bulkplan_rules", {})
    key = norm_text(rec)
    for word, rel in sorted(hooks.items()):
        if str(word).lower() in key:
            return str(rel), f"rule:{word}"
    return None


def tooling(rec: dict) -> bool:
    parts = set(path_parts(rec)) | {Path(rec["path"]).name}
    return bool(parts & (CACHE | VENDOR | SYS | TOOLS))


def tool_route(rec: dict) -> tuple[str, str]:
    parts = set(path_parts(rec))
    if parts & VENDOR:
        return "Developer/Tools/Dependencies", "vendor dependency cache"
    if parts & CACHE:
        return "Developer/Tools/Caches", "tool cache artifact"
    if parts & TOOLS:
        return "Developer/Tools", "local toolchain"
    return "Documents/Archives/System Metadata", "system metadata"


def project(rec: dict) -> bool:
    parts = set(path_parts(rec)) | {Path(rec["path"]).name}
    return rec["kind"] == "dir" or bool(parts & MARKERS)


def content_route(rec: dict) -> tuple[str, str]:
    ext = rec.get("ext") or Path(rec["path"]).suffix.lower()
    text = norm_text(rec)
    if ext in IMG_EXTS:
        return img_route(rec)
    if ext in VID_EXTS:
        return dated("Movies/Imported", rec), "video extension"
    if ext in AUD_EXTS:
        return dated("Music/Imported", rec), "audio extension"
    if ext in ARC_EXTS:
        return dated("Documents/Archives", rec), "archive extension"
    if ext in CODE_EXTS:
        return "Developer/Code", "code extension"
    return doc_route(ext, text)


def img_route(rec: dict) -> tuple[str, str]:
    text = norm_text(rec)
    if "screenshot" in text or "screen shot" in text:
        return dated("Pictures/Screenshots", rec), "screenshot"
    return dated("Pictures/Imported", rec), "image extension"


def doc_route(ext: str, text: str) -> tuple[str, str]:
    if "invoice" in text or "receipt" in text:
        return "Documents/Finance", "finance text"
    if "resume" in text or "interview" in text:
        return "Documents/Career", "career text"
    if "trading" in text or "market" in text:
        return "Documents/Notes/Trading", "market text"
    if "meeting" in text or "client" in text:
        return "Documents/Work", "work text"
    if "course" in text or "lesson" in text:
        return "Documents/Learning", "learning text"
    if ext in DOC_EXTS:
        return "Documents/Research", "document extension"
    return "Downloads/Inbox", "unclassified metadata"


def safe_dst(cfg: dict, rel: str) -> Path:
    dst = Path(cfg["target"]) / Path(str(rel).strip("/"))
    if fs.inside(str(dst), cfg["target"]):
        return dst
    return Path(cfg["target"]) / "Temporary" / "NeedsReview"


def item_name(rec: dict) -> str:
    path = Path(rec["path"])
    name = semantic_name(rec)
    return with_ext(name, path.suffix, rec["kind"])


def semantic_name(rec: dict) -> str:
    path = Path(rec["path"])
    stem = fs.safe_name(path.stem or path.name, "Item")
    if not generic(stem):
        return fs.safe_name(path.name, "Item")
    ctx = "-".join(name_terms(rec)[:5])
    date = year(rec)
    base = "-".join(x for x in (date, ctx, stem) if x)
    return fs.safe_name(base, stem)


def generic(stem: str) -> bool:
    low = stem.lower()
    vals = ("untitled", "screen shot", "screenshot", "img_", "dsc")
    if low.startswith(vals) or low in {"doc", "document", "image", "new"}:
        return True
    return bool(re.match(r"^new[ _-]*(project|folder|file|document)?\d*$",
                         low))


def name_terms(rec: dict) -> list[str]:
    vals = terms.toks(" ".join([rec.get("text", ""), rec.get("path", "")]))
    vals = {v for v in vals if v not in NAME_STOP}
    return sorted(vals, key=lambda x: (-score_term(x, rec), x))


def score_term(tok: str, rec: dict) -> int:
    text = rec.get("text", "").lower()
    path = rec.get("path", "").lower()
    return text.count(tok) * 3 + path.count(tok)


def with_ext(name: str, ext: str, kind: str) -> str:
    if kind == "dir" or not ext or name.lower().endswith(ext.lower()):
        return name
    return name + ext


def dedupe(rows: list[dict]) -> list[dict]:
    used: set[str] = set()
    for rec in rows:
        rec["dst"] = unique(Path(rec["dst"]), used)
        used.add(rec["dst"])
    return rows


def unique(path: Path, used: set[str]) -> str:
    if str(path) not in used and not path.exists():
        return str(path)
    stem, suffix = path.with_suffix(""), path.suffix
    return unique_idx(stem, suffix, used)


def unique_idx(stem: Path, suffix: str, used: set[str]) -> str:
    idx = 2
    while True:
        cand = Path(f"{stem}-{idx}{suffix}")
        if str(cand) not in used and not cand.exists():
            return str(cand)
        idx += 1


def path_parts(rec: dict) -> list[str]:
    return [p for p in Path(rec["path"]).parts if p]


def norm_text(rec: dict) -> str:
    vals = [rec.get("path", ""), rec.get("text", ""), rec.get("cluster", "")]
    return re.sub(r"\s+", " ", " ".join(vals)).lower()


def dated(root: str, rec: dict) -> str:
    return f"{root}/{year(rec)}"


def year(rec: dict) -> str:
    ts = max(0, int(float(rec.get("mtime", 0))))
    return str(dt.datetime.fromtimestamp(ts).year) if ts else ""


def same_place(src: str, dst: str) -> bool:
    try:
        return Path(src).resolve() == Path(dst).resolve()
    except OSError:
        return src == dst


def save(conn, cfg: dict, run_id: str, rows: list[dict]) -> None:
    conn.execute("DELETE FROM plans WHERE run=?", (run_id,))
    for rec in rows:
        db.add_plan(conn, run_id, rec)
    db.json_dump(cfgmod.state_dir(cfg, "plans") / f"{run_id}.ndjson", rows)
    conn.commit()
