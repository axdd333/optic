from __future__ import annotations

import time

from . import db, fs, log, state


def run(conn, cfg: dict, run_id: str) -> int:
    count = 0
    for rec in fs.walk(cfg):
        rec["state"] = state.SCANNED
        db.up_item(conn, rec)
        count += 1
        if count % 500 == 0:
            conn.commit()
    db.inc(conn, "scan_items", count)
    conn.commit()
    log.info("scan_done", run=run_id, count=count, sec=round(time.time()))
    return count

