from __future__ import annotations

import time
from collections.abc import Callable


def run(fn: Callable[[], object], attempts: int, base: float) -> object:
    err = None
    for idx in range(attempts):
        try:
            return fn()
        except Exception as exc:
            err = exc
            time.sleep(base * (2 ** idx))
    if err:
        raise err
    raise RuntimeError("retry exhausted")

