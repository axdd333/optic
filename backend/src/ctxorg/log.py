from __future__ import annotations

import json
import sys
import time


def emit(level: str, event: str, **data: object) -> None:
    rec = {"ts": time.time(), "level": level, "event": event}
    rec.update(data)
    print(json.dumps(rec, sort_keys=True), file=sys.stderr)


def info(event: str, **data: object) -> None:
    emit("info", event, **data)


def warn(event: str, **data: object) -> None:
    emit("warn", event, **data)


def err(event: str, **data: object) -> None:
    emit("err", event, **data)

