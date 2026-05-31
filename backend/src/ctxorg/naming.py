from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import fs


STOP = {
    "file", "document", "image", "screenshot", "screen", "shot",
    "untitled", "copy", "final", "new", "page", "scan", "img",
    "binary", "fragment", "log", "debug", "root",
    "context", "from", "with", "showing",
    "json", "data", "medium", "high", "low",
    "reference",
}
WEAK = {"", "context", "item", "file", "document", "log"}
DATA = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".xml", ".db",
        ".sqlite"}


def name(path: Path, data: dict, txt: str) -> str:
    schema = parts(path, data, txt)
    vals = visible(schema)
    return ext(fs.safe_name("-".join(v for v in vals if v), path.stem),
               path.suffix.lower())


def parts(path: Path, data: dict, txt: str) -> dict:
    body = "" if data.get("_noisy") else txt[:1600]
    raw = raw_context(path, data, body)
    sub = subject(subject_raw(path, data, raw))
    return {"date": date(path), "domain": domain(path, raw),
            "subject": sub, "kind": kind(path, raw),
            "confidence": confidence(data, txt)}


def visible(schema: dict) -> list[str]:
    vals = [schema["date"], schema["domain"], schema["subject"]]
    if schema["kind"] not in schema["subject"].split("-"):
        vals.append(schema["kind"])
    return vals


def raw_context(path: Path, data: dict, body: str) -> str:
    tags = " ".join(str(v) for v in data.get("tags", []))
    vals = [path.stem, str(data.get("name", "")), tags, body]
    return " ".join(v for v in vals if v)


def subject_raw(path: Path, data: dict, raw: str) -> str:
    name = str(data.get("name", "")).strip()
    if useful_name(name):
        return name
    vals = data.get("tags", [])
    if vals:
        return " ".join([*map(str, vals), str(data.get("reason", ""))])
    return raw


def useful_name(name: str) -> bool:
    if name.lower() in WEAK:
        return False
    vals = [t for tok in raw_toks(name) for t in subject_parts(tok)]
    return bool(vals)


def date(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def domain(path: Path, raw: str) -> str:
    vals = {
        "invoice": "finance", "receipt": "finance", "resume": "career",
        "cv": "career", "meeting": "work", "client": "work",
        "course": "learning", "lesson": "learning", "research": "research",
        "screenshot": "screenshot", "screen shot": "screenshot",
        "chrome": "browser", "web apps": "browser", "browser": "browser",
        "gcloud": "cloud", "google cloud": "cloud", "agent": "automation",
        "claude": "ai", "kimi": "ai", "zotero": "research",
        "auth": "auth", "token": "auth", "private key": "auth",
        "openclaw": "automation", "gateway": "automation",
        "vscode": "developer", "extension": "developer",
        "plugin": "developer", "telemetry": "telemetry",
        "failed event": "telemetry", "event log": "telemetry",
        "health": "telemetry", "lighthouse": "developer",
    }
    low = raw.lower()
    for key, val in vals.items():
        if key in low:
            return val
    return folder_domain(path)


def folder_domain(path: Path) -> str:
    parts_ = [p.lower() for p in path.parts]
    for val in ("projects", "research", "finance", "career", "work"):
        if val in parts_:
            return val.rstrip("s")
    return "reference"


def subject(raw: str) -> str:
    vals = []
    for tok in raw_toks(raw):
        vals.extend(subject_parts(tok))
    vals = list(dict.fromkeys(vals))
    return "-".join(vals[:5]) or "context"


def raw_toks(txt: str) -> list[str]:
    vals = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", txt.lower())
    return [v.strip("_-")[:48] for v in vals if len(v.strip("_-")) > 2]


def subject_parts(tok: str) -> list[str]:
    if keep_tok(tok):
        return [tok]
    return [part for part in tok.split("-") if keep_tok(part)]


def keep_tok(tok: str) -> bool:
    if tok in STOP or re.fullmatch(r"\d+", tok):
        return False
    if hex_id(tok):
        return False
    if len(tok) > 28:
        return False
    if re.match(r"[a-f0-9]{6,}-[a-f0-9-]{4,}", tok):
        return False
    return not re.fullmatch(r"[a-f0-9]{4,}-[a-f0-9-]{8,}", tok)


def hex_id(tok: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{4,}", tok) and re.search(r"\d", tok))


def kind(path: Path, raw: str) -> str:
    low = raw.lower()
    if "screenshot" in low or "screen shot" in low:
        return "screenshot"
    if config_like(low):
        return "config"
    if telemetry_like(low):
        return "telemetry"
    if path.suffix.lower() == ".log":
        return "log"
    if path.suffix.lower() in {".pdf", ".doc", ".docx", ".pages"}:
        return "document"
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".heic"}:
        return "image"
    if path.suffix.lower() in {".md", ".txt"}:
        return "note"
    if path.suffix.lower() in DATA:
        return "data"
    return path.suffix.lower().strip(".") or "item"


def config_like(low: str) -> bool:
    vals = ("config", "token", "privatekey", "private key", "publickey",
            "socket", "device auth", "preferences")
    return any(v in low for v in vals)


def telemetry_like(low: str) -> bool:
    vals = ("failed event", "event_type", "telemetry", "install counts",
            "health report", "update check")
    return any(v in low for v in vals)


def confidence(data: dict, txt: str) -> str:
    reason = str(data.get("reason", ""))
    if len(txt.strip()) > 300 or len(reason) > 40:
        return "high"
    if txt.strip() or reason:
        return "medium"
    return "low"


def ext(name_: str, suffix: str) -> str:
    return name_ if name_.lower().endswith(suffix) else name_ + suffix
