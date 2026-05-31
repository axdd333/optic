from __future__ import annotations

import shutil
import time
from pathlib import Path

from . import cfg as cfgmod
from . import db, fs, log, retry, state


def apply(conn, cfg: dict, run_id: str) -> int:
    rows = [r for r in db.plan_rows(conn, run_id)
            if r["state"] == state.PLANNED]
    out = [move_one(conn, cfg, run_id, r) for r in rows]
    db.json_dump(cfgmod.state_dir(cfg, "applied") / f"{run_id}.ndjson", out)
    conn.commit()
    log.info("apply_done", run=run_id, count=len(out))
    return len(out)


def move_one(conn, cfg: dict, run_id: str, rec: dict) -> dict:
    attempts, base = cfgmod.retry(cfg)
    try:
        retry.run(lambda: move_checked(cfg, rec), attempts, base)
        verify(rec)
        set_plan(conn, run_id, rec["id"], state.VERIFIED, "")
        return dict(rec, state=state.VERIFIED)
    except Exception as exc:
        set_plan(conn, run_id, rec["id"], state.DEAD, str(exc))
        return dict(rec, state=state.DEAD, err=str(exc))


def move_checked(cfg: dict, rec: dict) -> None:
    if not fs.inside(rec["dst"], cfg["target"]):
        raise RuntimeError("destination outside target")
    if collision(rec["src"], rec["dst"]):
        raise RuntimeError("destination exists")
    Path(rec["dst"]).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(rec["src"], rec["dst"])


def collision(src: str, dst: str) -> bool:
    out = Path(dst)
    return out.exists() and not fs.same(src, dst)


def verify(rec: dict) -> None:
    if not Path(rec["dst"]).exists():
        raise RuntimeError("destination missing after move")


def set_plan(conn, run: str, iid: str, st: str, err: str) -> None:
    conn.execute("UPDATE plans SET state=?,err=? WHERE run=? AND id=?",
                 (st, err[:500], run, iid))


def rollback(conn, cfg: dict, run_id: str) -> int:
    rows = list(reversed(db.plan_rows(conn, run_id)))
    out = [rollback_one(conn, r) for r in rows if r["state"] == state.VERIFIED]
    db.json_dump(cfgmod.state_dir(cfg, "applied") / f"{run_id}.rollback.ndjson",
                 out)
    conn.commit()
    return len(out)


def rollback_one(conn, rec: dict) -> dict:
    try:
        if collision(rec["dst"], rec["src"]):
            raise RuntimeError("rollback destination exists")
        Path(rec["src"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(rec["dst"], rec["src"])
        set_plan(conn, rec["run"], rec["id"], state.ROLLED_BACK, "")
        return dict(rec, state=state.ROLLED_BACK, ts=time.time())
    except Exception as exc:
        set_plan(conn, rec["run"], rec["id"], state.DEAD, str(exc))
        return dict(rec, state=state.DEAD, err=str(exc))
