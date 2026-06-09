from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from . import cmd, db, fs


def report(conn, cfg: dict) -> dict:
    return {
        "ok": ok(conn, cfg),
        "free_gb": round(fs.free_gb(cfg["target"]), 2),
        "model": cfg["model"],
        "tools": tools(),
        "metrics": db.metric_rows(conn),
        "state_dir": cfg["state_dir"],
        "disk": disk_report(cfg),
    }


def disk_report(cfg: dict) -> dict:
    """Return disk usage breakdown of the state directory for /api/health."""
    state_dir = Path(cfg["state_dir"])
    if not state_dir.is_dir():
        return {"error": "state_dir not found", "path": str(state_dir)}

    import shutil

    free_bytes = shutil.disk_usage(state_dir).free
    free_mb = free_bytes // (1024 * 1024)
    critical_mb = int(os.environ.get("OPTIC_DISK_CRITICAL_MB", "500"))
    warn_mb = int(os.environ.get("OPTIC_DISK_WARN_MB", "2000"))

    result: dict = {
        "free_mb": free_mb,
        "free_human": f"{free_mb}M",
        "critical": free_mb < critical_mb,
        "warning": free_mb < warn_mb,
        "threshold_critical_mb": critical_mb,
        "threshold_warn_mb": warn_mb,
        "dirs": {},
        "total_state_mb": 0.0,
    }

    dirs = ["dead", "extracts", "graphs", "backups", "exports",
            "edits", "scans", "plans", "atlas", "applied",
            "integrations", "labels"]
    for name in dirs:
        d = state_dir / name
        if not d.is_dir():
            continue
        files = [f for f in d.iterdir() if f.is_file()]
        sz = sum((f.stat().st_size for f in files), start=0) / (1024 * 1024)
        result["dirs"][name] = {
            "size_mb": round(sz, 1),
            "file_count": len(files),
        }
        result["total_state_mb"] += sz

    result["total_state_mb"] = round(result["total_state_mb"], 1)
    return result


def ok(conn, cfg: dict) -> bool:
    return fs.free_gb(cfg["target"]) >= float(cfg["min_free_gb"])


def tools() -> dict:
    names = ["ollama", "tesseract", "pdftotext", "pdftoppm", "textutil"]
    return {name: cmd.has(name) for name in names}


def write(conn, cfg: dict) -> Path:
    path = Path(cfg["state_dir"]) / "health.json"
    path.write_text(json.dumps(report(conn, cfg), indent=2), encoding="utf-8")
    return path


def ollama_models() -> str:
    proc = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else proc.stderr

