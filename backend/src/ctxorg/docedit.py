from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

from . import cfg as cfgmod
from . import db, fs, ollama, terms


def plan(conn, cfg: dict, run_id: str) -> list[dict]:
    rows = db.rows(conn, "SELECT * FROM items WHERE state='EXTRACTED'")
    out = [make_plan(cfg, r) for r in rows if editable(cfg, r)]
    out = [r for r in out if r]
    db.json_dump(cfgmod.state_dir(cfg, "edits") / f"{run_id}.ndjson", out)
    return out


def editable(cfg: dict, rec: dict) -> bool:
    exts = set(cfg.get("edit_text_exts", [])) | set(cfg.get("sidecar_exts", []))
    return rec["kind"] == "file" and rec["ext"] in exts


def make_plan(cfg: dict, rec: dict) -> dict:
    data = doc_meta(cfg, rec)
    return {
        "id": rec["id"], "path": rec["path"], "kind": edit_kind(cfg, rec),
        "title": fs.safe_name(data.get("title", Path(rec["path"]).stem)),
        "summary": str(data.get("summary", ""))[:900],
        "tags": list(data.get("tags", []))[:12],
        "state": "EDIT_PLANNED", "hash": digest(rec.get("text", "")),
    }


def doc_meta(cfg: dict, rec: dict) -> dict:
    if not rec.get("text", "").strip():
        return fallback(rec)
    try:
        return ollama.gen(cfg, prompt(rec), feature="docedit")
    except Exception:
        return fallback(rec)


def prompt(rec: dict) -> str:
    txt = terms.summary(rec.get("text", ""), 3600)
    return DOC_PROMPT.format(path=rec["path"], text=txt)


DOC_PROMPT = """
Return strict JSON for a document cleanup edit:
{{"title":"semantic title","summary":"1 sentence","tags":["tag"]}}
Use the surrounding path plus document text. Name the document by its actual
project, person, course, account, invoice, idea, or research topic.

path={path}
text={text}
""".strip()


def fallback(rec: dict) -> dict:
    return {"title": Path(rec["path"]).stem, "summary": "", "tags": []}


def edit_kind(cfg: dict, rec: dict) -> str:
    if rec["ext"] in cfg.get("edit_text_exts", []):
        return "rewrite"
    return "sidecar"


def digest(txt: str) -> str:
    return hashlib.sha256(txt.encode()).hexdigest()[:16]


def apply(conn, cfg: dict, run_id: str) -> int:
    rows = load(cfg, run_id)
    out = [apply_one(cfg, rec) for rec in rows]
    db.json_dump(cfgmod.state_dir(cfg, "edits") / f"{run_id}.applied.ndjson",
                 out)
    return len(out)


def load(cfg: dict, run_id: str) -> list[dict]:
    path = cfgmod.state_dir(cfg, "edits") / f"{run_id}.ndjson"
    return [__import__("json").loads(x) for x in path.read_text().splitlines()]


def apply_one(cfg: dict, rec: dict) -> dict:
    try:
        return rewrite(cfg, rec) if rec["kind"] == "rewrite" else sidecar(rec)
    except Exception as exc:
        return dict(rec, state="EDIT_DEAD", err=str(exc)[:500])


def rewrite(cfg: dict, rec: dict) -> dict:
    path = Path(rec["path"])
    backup = backup_path(cfg, rec)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup)
    txt = path.read_text(encoding="utf-8", errors="ignore")
    path.write_text(frontmatter(rec) + strip_frontmatter(txt), encoding="utf-8")
    return dict(rec, state="EDITED", backup=str(backup), ts=time.time())


def sidecar(rec: dict) -> dict:
    path = Path(rec["path"] + ".context.md")
    path.write_text(frontmatter(rec), encoding="utf-8")
    return dict(rec, state="SIDECAR_WRITTEN", sidecar=str(path))


def backup_path(cfg: dict, rec: dict) -> Path:
    name = fs.safe_name(Path(rec["path"]).name)
    return cfgmod.state_dir(cfg, "backups") / rec["id"] / name


def frontmatter(rec: dict) -> str:
    tags = ", ".join(str(t) for t in rec.get("tags", []))
    lines = ["---", f"title: {rec['title']}", f"tags: [{tags}]"]
    lines.append(f"summary: {rec['summary']}")
    lines.extend(["---", "", f"# {rec['title']}", ""])
    return "\n".join(lines)


def strip_frontmatter(txt: str) -> str:
    if not txt.startswith("---"):
        return txt
    parts = txt.split("---", 2)
    return parts[2].lstrip() if len(parts) == 3 else txt


def rollback(cfg: dict, run_id: str) -> int:
    path = cfgmod.state_dir(cfg, "edits") / f"{run_id}.applied.ndjson"
    rows = [__import__("json").loads(x) for x in path.read_text().splitlines()]
    return sum(rollback_one(r) for r in rows)


def rollback_one(rec: dict) -> int:
    if rec.get("backup"):
        shutil.copy2(rec["backup"], rec["path"])
        return 1
    if rec.get("sidecar") and Path(rec["sidecar"]).exists():
        Path(rec["sidecar"]).unlink()
        return 1
    return 0
