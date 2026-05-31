from __future__ import annotations

import concurrent.futures as fut
import json
import os
import plistlib
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import cfg as cfgmod
from . import extract, fs, log, ollama, terms
from . import naming, refs


DOC = {".pdf", ".doc", ".docx", ".rtf", ".pages", ".md", ".txt"}
IMG = {".png", ".jpg", ".jpeg", ".heic", ".tif", ".tiff", ".webp"}
DATA = {".csv", ".tsv", ".json", ".xml", ".html", ".log"}
CODE = {".js", ".ts", ".tsx", ".py", ".rs", ".go", ".swift", ".cpp", ".h"}
ATTR = "com.apple.metadata:_kMDItemUserTags"


def plan(cfg: dict, run: str) -> list[dict]:
    cfg["_refs"] = refs.build(cfg)
    done = seen(cfg, run)
    rows = bounded([p for p in candidates(cfg) if str(p) not in done], cfg)
    out = drain(cfg, run, rows)
    log.info("deep_plan_done", run=run, count=len(out))
    return out


def apply(cfg: dict, run: str) -> list[dict]:
    rows = load(plan_path(cfg, run))
    out = [apply_one(rec) for rec in rows if applied_state(rec)]
    dump(applied_path(cfg, run), out)
    log.info("deep_apply_done", run=run, count=len(out))
    return out


def applied_state(rec: dict) -> bool:
    return rec["state"] in {"PLANNED", "REFERENCED_WAITING",
                            "WAITING_DATALess", "WAITING_DATALESS"}


def run(cfg: dict, run_id: str) -> list[dict]:
    if live_allowed(cfg, run_id):
        return live(cfg, run_id)
    plan(cfg, run_id)
    return apply(cfg, run_id)


def live_allowed(cfg: dict, run_id: str) -> bool:
    want = bool(cfg.get("deep_apply_live", False))
    guard = str(cfg.get("deep_live_guard", ""))
    ok = want and guard == run_id
    if want and not ok:
        log.info("deep_live_guarded", run=run_id)
    return ok


def live(cfg: dict, run_id: str) -> list[dict]:
    cfg["_refs"] = refs.build(cfg)
    done = seen(cfg, run_id)
    rows = bounded([p for p in candidates(cfg) if str(p) not in done], cfg)
    out = []
    for idx, path in enumerate(rows, 1):
        rec_ = one(cfg, run_id, path)
        append(plan_path(cfg, run_id), rec_)
        out.append(apply_one(rec_) if applied_state(rec_) else rec_)
        append(applied_path(cfg, run_id), out[-1])
        tick(run_id, idx, len(rows))
    return out


def tick(run_id: str, idx: int, total: int) -> None:
    if idx == 1 or idx % 25 == 0 or idx == total:
        log.info("deep_live_progress", run=run_id, done=idx, total=total)


def candidates(cfg: dict) -> list[Path]:
    out = []
    for root in roots(cfg):
        out.extend(p for p in files(root, cfg) if eligible(p))
    return sorted(set(out), key=lambda p: (prio(cfg, p), str(p)))


def prio(cfg: dict, path: Path) -> int:
    roots_ = [Path(p) for p in cfg.get("deep_focus_roots", [])]
    for idx, root in enumerate(roots_):
        if inside(path, root):
            return idx
    return len(roots_)


def roots(cfg: dict) -> list[Path]:
    vals = [Path(p) for p in cfg.get("sources", [])]
    vals.append(Path(cfg["home"]) / "Developer")
    return [p for p in vals if p.exists() and not fs.protected(str(p), cfg)]


def files(root: Path, cfg: dict):
    for base, dirs, names in os.walk(root):
        dirs[:] = keep_dirs(Path(base), dirs, cfg)
        for name in names:
            yield Path(base) / name


def keep_dirs(base: Path, dirs: list[str], cfg: dict) -> list[str]:
    skip = set(cfg.get("prune_dirs", [])) | {".git", "node_modules"}
    return [d for d in dirs if d not in skip and not pkg(base / d)]


def pkg(path: Path) -> bool:
    return path.suffix.lower() in {".photoslibrary", ".app", ".musiclibrary"}


def eligible(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in (DOC | IMG | DATA)


def bounded(rows: list[Path], cfg: dict) -> list[Path]:
    lim = int(cfg.get("deep_limit", 0) or 0)
    return rows[:lim] if lim else rows


def seen(cfg: dict, run: str) -> set[str]:
    applied = {r["src"] for r in load_safe(applied_path(cfg, run))}
    held = {r["src"] for r in load_safe(plan_path(cfg, run))
            if r["state"] != "PLANNED"}
    return applied | held


def drain(cfg: dict, run: str, rows: list[Path]) -> list[dict]:
    out = []
    with fut.ThreadPoolExecutor(max_workers=workers(cfg)) as pool:
        tasks = [pool.submit(one, cfg, run, p) for p in rows]
        for task in fut.as_completed(tasks):
            out.append(task.result())
            append(plan_path(cfg, run), out[-1])
    return out


def workers(cfg: dict) -> int:
    return max(1, int(cfg.get("deep_workers", 1)))


def one(cfg: dict, run: str, path: Path) -> dict:
    try:
        return planned(cfg, run, path)
    except Exception as exc:
        return rec(run, path, path, "DEAD_LETTER", err=str(exc)[:500])


def planned(cfg: dict, run: str, path: Path) -> dict:
    if ref_protected(cfg, run, path):
        return ref_row(cfg, run, path)
    txt = "" if dataless(path) else extract.extract(meta(path), cfg)
    if dataless(path):
        return wait_row(run, path)
    data = predecide(path, txt) or decide(cfg, path, txt, context(path, cfg))
    data["_txt"] = txt
    dst = target(cfg, path, data)
    return rec(run, path, dst, "PLANNED", text=terms.summary(txt, 900),
               tags=tags(data), why=str(data.get("reason", ""))[:300])


def ref_protected(cfg: dict, run: str, path: Path) -> bool:
    idx = cfg.get("_refs") or {}
    return refs.protected_file(path, cfg, idx)


def ref_row(cfg: dict, run: str, path: Path) -> dict:
    ev = refs.evidence(path, cfg.get("_refs") or {})
    why = "referenced by code: " + "; ".join(ev[:3])
    return rec(run, path, path, "REFERENCED_WAITING", why=why,
               tags=["referenced-code", "keep-name"])


def wait_row(run: str, path: Path) -> dict:
    why = "dataless iCloud/FileProvider placeholder"
    return rec(run, path, path, "WAITING_DATALESS", why=why,
               tags=["waiting-dataless"])


def meta(path: Path) -> dict:
    st = path.stat()
    return {"id": fs.item_id(str(path)), "path": str(path), "kind": "file",
            "size": st.st_size, "mtime": st.st_mtime,
            "ext": path.suffix.lower(), "state": "SCANNED"}


def decide(cfg: dict, path: Path, txt: str, ctx: str) -> dict:
    if not txt.strip() and not ctx.strip():
        return fallback(path)
    try:
        return ollama.gen(cfg, prompt(cfg, path, txt, ctx),
                          feature="deep")
    except Exception as exc:
        return dict(fallback(path), reason=f"fallback:{exc}")


def predecide(path: Path, txt: str) -> dict | None:
    if noisy(txt):
        return noisy_data(path, txt)
    if trivial_json(path, txt):
        return json_data(path, txt)
    if gcloud_log(path, txt):
        return gcloud_data(txt)
    if kimi_log(path, txt):
        return kimi_log_data(path)
    if openclaw_log(path, txt):
        return openclaw_log_data(path, txt)
    if claude_event(path, txt):
        return claude_data(path)
    if sensitive_json(path, txt):
        return sensitive_data(path, txt)
    if dev_inventory(path, txt):
        return dev_inventory_data(path, txt)
    if health_json(path, txt):
        return health_data(path)
    if agent_meta(path):
        return agent_data(path)
    return None


def kimi_log(path: Path, txt: str) -> bool:
    low = f"{path.name} {txt[:800]}".lower()
    return path.suffix.lower() == ".log" and "kimi_cli" in low


def kimi_log_data(path: Path) -> dict:
    return {"name": "kimi cli session log", "folder": "",
            "reason": f"Kimi CLI session log from {path.name}",
            "tags": ["kimi", "cli", "session", "log"]}


def openclaw_log(path: Path, txt: str) -> bool:
    low = f"{path.name} {txt[:800]}".lower()
    return path.suffix.lower() == ".log" and "openclaw" in low


def openclaw_log_data(path: Path, txt: str) -> dict:
    kind = "gateway error" if path.name.endswith(".err.log") else "gateway"
    return {"name": f"openclaw {kind} log", "folder": "",
            "reason": f"OpenClaw {kind} log from {path.name}",
            "tags": ["openclaw", "gateway", "log"]}


def claude_event(path: Path, txt: str) -> bool:
    if path.suffix.lower() != ".json":
        return False
    low = f"{path.name} {txt[:800]}".lower()
    return "1p_failed_events" in low or "claudecodeinternalevent" in low


def claude_data(path: Path) -> dict:
    return {"name": "claude code failed events json", "folder": "",
            "reason": f"Claude Code event log from filename {path.name}",
            "tags": ["claude", "code", "failed-events", "json"]}


def sensitive_json(path: Path, txt: str) -> bool:
    if path.suffix.lower() != ".json":
        return False
    low = f"{path.name} {txt[:1200]}".lower()
    vals = ("access_token", "refresh_token", "privatekeypem",
            "private_key", "device-auth", "exec-approvals.sock")
    return any(v in low for v in vals)


def sensitive_data(path: Path, txt: str) -> dict:
    name = sensitive_name(path, txt)
    return {"name": name, "folder": "",
            "reason": f"sensitive local auth/config JSON from {path.name}",
            "tags": ["auth", "config", "sensitive"]}


def sensitive_name(path: Path, txt: str) -> str:
    low = f"{path.name} {txt[:1200]}".lower()
    if "kimi" in low:
        return "kimi auth token config"
    if "exec-approvals" in low:
        return "exec approvals socket config"
    if "device" in low:
        return "device auth config"
    return "local auth token config"


def dev_inventory(path: Path, txt: str) -> bool:
    if path.suffix.lower() != ".json":
        return False
    low = f"{path.name} {txt[:1600]}".lower()
    vals = ("installed_plugins", "install-counts", "unique_installs",
            ".vscode/extensions", ".cursor/extensions")
    return any(v in low for v in vals)


def dev_inventory_data(path: Path, txt: str) -> dict:
    low = f"{path.name} {txt[:1600]}".lower()
    name = "claude plugin inventory" if "claude" in low else "vscode extension"
    return {"name": f"{name} metadata", "folder": "",
            "reason": f"developer tool inventory JSON from {path.name}",
            "tags": ["developer", "metadata", "json"]}


def health_json(path: Path, txt: str) -> bool:
    low = f"{path.name} {txt[:800]}".lower()
    return path.suffix.lower() == ".json" and "dead_letter" in low


def health_data(path: Path) -> dict:
    return {"name": "context organizer health report", "folder": "",
            "reason": f"Context Organizer health report from {path.name}",
            "tags": ["context-organizer", "health", "json"]}


def gcloud_log(path: Path, txt: str) -> bool:
    if path.suffix.lower() != ".log":
        return False
    low = txt.lower()
    return "gcloud" in low or "google cloud sdk" in low


def gcloud_data(txt: str) -> dict:
    cmd = gcloud_cmd(txt)
    return {"name": f"gcloud {cmd} log", "folder": "",
            "reason": f"Google Cloud CLI log for {cmd}",
            "tags": ["gcloud", *cmd.split()[:3], "log"]}


def gcloud_cmd(txt: str) -> str:
    hit = re.search(r"Running \[gcloud\.([^\]]+)\]", txt)
    if hit:
        return fs.safe_name(hit.group(1).replace(".", " "), "command")
    return "sdk version" if "google cloud sdk" in txt.lower() else "cli"


def agent_meta(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() == ".json" and name.startswith("agent-")


def agent_data(path: Path) -> dict:
    return {"name": "agent metadata json", "folder": "",
            "reason": f"agent metadata file from filename {path.name}",
            "tags": ["agent", "metadata", "json"]}


def trivial_json(path: Path, txt: str) -> bool:
    if path.suffix.lower() != ".json":
        return False
    return txt.strip() in {"[]", "{}", "null"}


def json_data(path: Path, txt: str) -> dict:
    kind = "empty agent json" if "agent" in path.name.lower() else "empty json"
    return {"name": kind, "folder": "",
            "reason": f"{txt.strip()} JSON payload with path context",
            "tags": json_tags(path), "_trivial": True}


def json_tags(path: Path) -> list[str]:
    vals = ["json", "empty"]
    if "agent" in path.name.lower():
        vals.append("agent")
    return vals


def noisy(txt: str) -> bool:
    sample = txt[:3000]
    if not sample:
        return False
    bad = sum(1 for ch in sample if ord(ch) < 32 and ch not in "\n\r\t")
    return bad / max(1, len(sample)) > 0.015


def noisy_data(path: Path, txt: str) -> dict:
    return {"name": noisy_name(path, txt), "folder": "",
            "reason": "control-heavy state file; classified from metadata",
            "tags": noisy_tags(path, txt), "_noisy": True}


def noisy_name(path: Path, txt: str) -> str:
    low = txt.lower()
    if "web_apps" in low or "chrome_default" in low:
        return "chrome web apps state"
    if "google.chrome" in low or "device_token" in low:
        return "google chrome device state"
    return f"binary {path.suffix.lower().strip('.') or 'file'} fragment"


def noisy_tags(path: Path, txt: str) -> list[str]:
    vals = ["binary", path.suffix.lower().strip(".") or "file"]
    if "chrome" in txt.lower() or "web_apps" in txt.lower():
        vals.append("browser")
    return vals


def prompt(cfg: dict, path: Path, txt: str, ctx: str) -> str:
    cats = ", ".join(cfg["categories"])
    body = terms.summary(txt, int(cfg.get("deep_text_chars", 2800)))
    return PROMPT.format(path=path, cats=cats, ctx=ctx[:2200], text=body)


def context(path: Path, cfg: dict) -> str:
    sibs = sorted(p.name for p in path.parent.iterdir())[:80]
    vals = [f"parent={path.parent}", "siblings=" + ", ".join(sibs)]
    vals.extend(read_local(path.parent, cfg))
    return "\n".join(v for v in vals if v)


def read_local(parent: Path, cfg: dict) -> list[str]:
    names = ["README.md", "package.json", "pyproject.toml", "go.mod"]
    return [read_one(parent / n, cfg) for n in names if (parent / n).exists()]


def read_one(path: Path, cfg: dict) -> str:
    return f"--- {path.name} ---\n{extract.read_text(path, cfg)[:1600]}"


def target(cfg: dict, path: Path, data: dict) -> Path:
    folder = folder_for(cfg, path, data)
    name = naming.name(path, data, str(data.get("_txt", "")))
    return unique(folder / name, path)


def folder_for(cfg: dict, path: Path, data: dict) -> Path:
    if force_default(cfg, path):
        return default_folder(cfg, path, data)
    rel = str(data.get("folder", "")).strip("/")
    base = Path(cfg["home"]) / rel if rel else path.parent
    if rel and fs.inside(str(base), cfg["home"]):
        return base
    return default_folder(cfg, path, data)


def force_default(cfg: dict, path: Path) -> bool:
    home = Path(cfg["home"])
    vals = [home / "Downloads" / "Inbox",
            home / "Documents" / "Research",
            home / "Developer" / "Code"]
    return any(inside(path, root) for root in vals)


def default_folder(cfg: dict, path: Path, data: dict) -> Path:
    home = Path(cfg["home"])
    ext = path.suffix.lower()
    if inside(path, home / "Developer" / "Code") and ext == ".js":
        return home / "Developer" / "Code" / "Zotero Translators"
    if inside(path, home / "Downloads" / "Inbox"):
        return inbox_folder(home, ext, data)
    if inside(path, home / "Documents" / "Research"):
        return research_folder(home, data, path)
    return path.parent


def inbox_folder(home: Path, ext: str, data: dict) -> Path:
    if ext in {".dmg", ".pkg", ".app"}:
        return home / "Downloads" / "Installers"
    if ext in {".log", ".jsonl", ".ndjson"}:
        return log_folder(home, ext, data)
    if sensitive_config(data):
        return home / "Documents" / "Archives" / "Sensitive Config"
    if json_log(data):
        return home / "Documents" / "Archives" / "Logs" / "Claude Code"
    if dev_metadata(data):
        return home / "Documents" / "Archives" / "Developer Metadata"
    if ext in {".json", ".csv", ".tsv", ".db", ".sqlite", ".xml"}:
        return home / "Documents" / "Archives" / "Data"
    if ext in CODE:
        return home / "Developer" / "Code" / "Fragments"
    if ext in DOC:
        return home / "Documents" / "Research"
    return home / "Downloads" / "Review"


def json_log(data: dict) -> bool:
    raw = json.dumps(data, sort_keys=True).lower()
    return "failed-events" in raw or "claude code event" in raw


def sensitive_config(data: dict) -> bool:
    raw = json.dumps(data, sort_keys=True).lower()
    return "sensitive" in raw or "auth token" in raw or "socket config" in raw


def dev_metadata(data: dict) -> bool:
    raw = json.dumps(data, sort_keys=True).lower()
    return "developer" in raw and "metadata" in raw


def log_folder(home: Path, ext: str, data: dict) -> Path:
    if data.get("_noisy") and ext == ".log":
        return home / "Documents" / "Archives" / "Logs" / "Binary State"
    raw = json.dumps(data, sort_keys=True).lower()
    if "gcloud" in raw or "google cloud" in raw:
        return home / "Documents" / "Archives" / "Logs" / "GCloud CLI"
    if "kimi" in raw:
        return home / "Documents" / "Archives" / "Logs" / "Kimi CLI"
    if "openclaw" in raw:
        return home / "Documents" / "Archives" / "Logs" / "OpenClaw"
    return home / "Documents" / "Archives" / "Logs"


def research_folder(home: Path, data: dict, path: Path) -> Path:
    dom = naming.parts(path, data, str(data.get("_txt", "")))["domain"]
    return home / "Documents" / "Research" / fs.safe_name(dom.title())


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def tags(data: dict) -> list[str]:
    vals = data.get("tags", [])
    return [fs.safe_name(str(v), "context") for v in vals[:8]]


def fallback(path: Path) -> dict:
    return {"name": path.name, "folder": "", "reason": "weak context",
            "tags": []}


def dataless(path: Path) -> bool:
    proc = subprocess.run(["stat", "-f", "%Sf", str(path)],
                          capture_output=True, text=True)
    return "dataless" in proc.stdout


def unique(dst: Path, src: Path) -> Path:
    if same(dst, src):
        return src
    if not dst.exists():
        return dst
    stem, suffix = dst.with_suffix(""), dst.suffix
    return unique_idx(stem, suffix)


def unique_idx(stem: Path, suffix: str) -> Path:
    idx = 2
    while True:
        cand = Path(f"{stem}-{idx}{suffix}")
        if not cand.exists():
            return cand
        idx += 1


def same(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def apply_one(rec_: dict) -> dict:
    try:
        if rec_["state"] != "PLANNED":
            err = tag_safe(rec_["src"], rec_.get("tags", []))
            return dict(rec_, tag_err=err, ts=time.time())
        move(rec_)
        err = tag_safe(rec_["dst"], rec_.get("tags", []))
        return dict(rec_, state="VERIFIED", tag_err=err, ts=time.time())
    except Exception as exc:
        return dict(rec_, state="DEAD_LETTER", err=str(exc)[:500])


def move(rec_: dict) -> None:
    src, dst = Path(rec_["src"]), Path(rec_["dst"])
    if same(src, dst):
        return
    if dst.exists():
        raise RuntimeError("destination exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)


def tag(path: str, tags_: list[str]) -> None:
    if not tags_ or not Path(path).exists():
        return
    vals = old_tags(path) + [f"Context:{v}" for v in tags_]
    set_tags(path, list(dict.fromkeys(vals)))


def tag_safe(path: str, tags_: list[str]) -> str:
    try:
        tag(path, tags_)
        return ""
    except Exception as exc:
        return str(exc)[:160]


def set_tags(path: str, vals: list[str]) -> None:
    raw = plistlib.dumps(vals)
    if hasattr(os, "setxattr"):
        os.setxattr(path, ATTR, raw)
        return
    subprocess.run(["xattr", "-wx", ATTR, raw.hex(), path], check=True)


def old_tags(path: str) -> list[str]:
    try:
        return [str(v) for v in plistlib.loads(tag_bytes(path))]
    except Exception:
        return []


def tag_bytes(path: str) -> bytes:
    if hasattr(os, "getxattr"):
        return os.getxattr(path, ATTR)
    proc = subprocess.run(["xattr", "-px", ATTR, path], capture_output=True,
                          text=True, check=True)
    return bytes.fromhex("".join(proc.stdout.split()))


def rec(run: str, src: Path, dst: Path, st: str, **vals: object) -> dict:
    out = {"run": run, "src": str(src), "dst": str(dst), "state": st}
    out.update(vals)
    return out


def append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def dump(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def load(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()]


def load_safe(path: Path) -> list[dict]:
    return load(path) if path.exists() else []


def plan_path(cfg: dict, run: str) -> Path:
    return cfgmod.state_dir(cfg, "deep") / f"{run}.ndjson"


def applied_path(cfg: dict, run: str) -> Path:
    return cfgmod.state_dir(cfg, "deep") / f"{run}.applied.ndjson"


PROMPT = """
Return strict JSON for a local filesystem rename.
Use OCR/document text plus sibling/project context. Keep real project names,
people, product names, institutions, invoice/course/research topics, and dates.

Schema:
{{
  "name": "semantic filename with extension if useful",
  "folder": "optional relative folder under one of: {cats}",
  "reason": "short evidence-based reason",
  "tags": ["short tag"]
}}

Rules:
- Preserve the original extension.
- Prefer concise academic/scientific names.
- Do not invent facts beyond path, OCR text, or sibling context.
- Use folder only when the evidence is strong; otherwise leave it empty.

path={path}
context:
{ctx}

ocr_or_text:
{text}
""".strip()
