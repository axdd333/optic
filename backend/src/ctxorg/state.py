from __future__ import annotations

SCANNED = "SCANNED"
EXTRACTED = "EXTRACTED"
LINKED = "LINKED"
CLUSTERED = "CLUSTERED"
PLANNED = "PLANNED"
MOVING = "MOVING"
MOVED = "MOVED"
VERIFIED = "VERIFIED"
RETRY_WAIT = "RETRY_WAIT"
DEAD = "DEAD_LETTER"
ROLLED_BACK = "ROLLED_BACK"

FLOW = {
    SCANNED: {EXTRACTED, DEAD},
    EXTRACTED: {LINKED, CLUSTERED, PLANNED, DEAD},
    LINKED: {CLUSTERED, DEAD},
    CLUSTERED: {PLANNED, DEAD},
    PLANNED: {MOVING, DEAD},
    MOVING: {MOVED, RETRY_WAIT, DEAD},
    RETRY_WAIT: {MOVING, DEAD},
    MOVED: {VERIFIED, DEAD},
    VERIFIED: {ROLLED_BACK},
}


def can(src: str, dst: str) -> bool:
    return dst in FLOW.get(src, set())


def require(src: str, dst: str) -> None:
    if src and not can(src, dst) and src != dst:
        raise ValueError(f"bad state transition {src}->{dst}")

