from __future__ import annotations

import json
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
    }


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

