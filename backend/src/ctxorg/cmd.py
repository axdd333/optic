from __future__ import annotations

import shutil
import subprocess


def has(name: str) -> bool:
    return shutil.which(name) is not None


def run(argv: list[str], timeout: int) -> str:
    proc = subprocess.run(
        argv,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )
    if proc.returncode:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout

