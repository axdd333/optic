from __future__ import annotations

from . import fs, health


def check(cfg: dict) -> dict:
    tools = health.tools()
    free = fs.free_gb(cfg["target"])
    return {
        "ok": all(tools.values()) and free >= float(cfg["min_free_gb"]),
        "free_gb": round(free, 2),
        "need_free_gb": cfg["min_free_gb"],
        "tools": tools,
        "models": health.ollama_models(),
    }

