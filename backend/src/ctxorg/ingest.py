from __future__ import annotations

import concurrent.futures as fut
import json
import threading
import time

from . import cfg as cfgmod
from . import db, extract, log, retry, state


def run(conn, cfg: dict, run_id: str) -> int:
    rows = pending(conn, cfg)
    done = drain(conn, cfg, run_id, rows)
    conn.commit()
    log.info("ingest_done", run=run_id, count=done)
    return done


def drain(conn, cfg: dict, run_id: str, rows: list[dict]) -> int:
    workers = worker_count(cfg)
    active: set[fut.Future] = set()
    sem = threading.BoundedSemaphore(ocr_count(cfg, workers))
    src = iter(rows)
    done = 0
    with fut.ThreadPoolExecutor(max_workers=workers) as pool:
        fill(pool, active, src, cfg, sem, workers * 2)
        while active:
            fin, active = fut.wait(active, return_when=fut.FIRST_COMPLETED)
            done += save_all(conn, cfg, run_id, fin, done)
            fill(pool, active, src, cfg, sem, workers * 2)
    return done


def fill(pool, active: set, src, cfg: dict, sem, lim: int) -> None:
    while len(active) < lim:
        try:
            rec = next(src)
        except StopIteration:
            return
        active.add(pool.submit(one, rec, cfg, sem))


def save_all(conn, cfg: dict, run_id: str, fin: set, base: int) -> int:
    done = 0
    for task in fin:
        rec, txt, err = task.result()
        save(conn, cfg, run_id, rec, txt, err)
        done += 1
        if (base + done) % 100 == 0:
            conn.commit()
    return done


def pending(conn, cfg: dict) -> list[dict]:
    sql = pending_sql(cfg)
    rows = db.rows(conn, sql, pending_args(cfg))
    rows = sorted(rows, key=lambda r: pri(r, cfg))
    cap = int(cfg.get("max_ingest_items", 0) or 0)
    return rows[:cap] if cap else rows


def pending_sql(cfg: dict) -> str:
    roots = src_roots(cfg)
    base = "SELECT * FROM items WHERE state IN (?,?)"
    if not roots:
        return base
    expr = " OR ".join(["(path=? OR path LIKE ?)"] * len(roots))
    return f"{base} AND ({expr})"


def pending_args(cfg: dict) -> tuple:
    out: list[str] = [state.SCANNED, state.DEAD]
    for root in src_roots(cfg):
        out.extend([root, root + "/%"])
    return tuple(out)


def src_roots(cfg: dict) -> list[str]:
    out = []
    seen = set()
    for raw in cfg.get("sources", []):
        root = src_root(raw)
        if root and root not in seen:
            seen.add(root)
            out.append(root)
    return out


def src_root(raw: object) -> str:
    val = str(raw or "").strip()
    if not val:
        return ""
    if len(val) > 1:
        val = val.rstrip("/")
    return val or "/"


def pri(rec: dict, cfg: dict) -> tuple[int, int, int, str]:
    st = 0 if rec["state"] == state.SCANNED else 1
    if rec["kind"] == "dir":
        return st, 0, 0, rec["path"]
    ext = rec["ext"]
    if ext in cfg.get("doc_priority_exts", []):
        return st, 1, int(rec["size"]), rec["path"]
    if ext in cfg.get("ocr_priority_exts", []):
        return st, 2, int(rec["size"]), rec["path"]
    if ext in cfg.get("text_priority_exts", []):
        return st, 3, int(rec["size"]), rec["path"]
    return st, 9, int(rec["size"]), rec["path"]


def one(rec: dict, cfg: dict, sem) -> tuple[dict, str, str]:
    attempts, base = cfgmod.retry(cfg)
    try:
        txt = retry.run(lambda: extract_one(rec, cfg, sem), attempts, base)
        return rec, str(txt), ""
    except Exception as exc:
        return rec, "", str(exc)[:500]


def extract_one(rec: dict, cfg: dict, sem) -> str:
    if heavy(rec, cfg):
        with sem:
            return extract.extract(rec, cfg)
    return extract.extract(rec, cfg)


def heavy(rec: dict, cfg: dict) -> bool:
    exts = set(cfg.get("ocr_priority_exts", []))
    exts.update({".pdf", ".doc", ".docx", ".rtf", ".pages"})
    return rec["ext"] in exts


def worker_count(cfg: dict) -> int:
    return max(1, int(cfg.get("workers", 1)))


def ocr_count(cfg: dict, workers: int) -> int:
    raw = cfg.get("ocr_workers", min(2, workers))
    return max(1, min(workers, int(raw)))


def save(conn, cfg: dict, run_id: str, rec: dict, txt: str, err: str) -> None:
    if err:
        dead(conn, cfg, run_id, rec, err)
        return
    path = cfgmod.state_dir(cfg, "extracts") / f"{rec['id']}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(txt, encoding="utf-8")
    db.set_item(conn, rec["id"], text=txt, state=state.EXTRACTED, err="")
    db.inc(conn, "extracted")


def dead(conn, cfg: dict, run_id: str, rec: dict, err: str) -> None:
    db.set_item(conn, rec["id"], state=state.DEAD, err=err)
    conn.execute("INSERT INTO dead VALUES(?,?,?,?,?)",
                 (run_id, rec["id"], rec["path"], err, time.time()))
    log_dead(cfg, run_id, rec, err)
    db.inc(conn, "dead")


def log_dead(cfg: dict, run_id: str, rec: dict, err: str) -> None:
    root = cfgmod.state_dir(cfg, "dead")
    root.mkdir(parents=True, exist_ok=True)
    data = {"run": run_id, "id": rec["id"], "path": rec["path"],
            "err": err, "ts": time.time()}
    with (root / f"{run_id}.ndjson").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, sort_keys=True) + "\n")
