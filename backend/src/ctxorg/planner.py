from __future__ import annotations

import concurrent.futures as fut
from pathlib import Path

from . import cfg as cfgmod
from . import bulkplan, db, fs, log, ollama, state, terms


def run(conn, cfg: dict, run_id: str, clusters: dict) -> list[dict]:
    out = []
    with fut.ThreadPoolExecutor(max_workers=llm_workers(cfg)) as pool:
        tasks = [pool.submit(safe_plan, cfg, cid, rows)
                 for cid, rows in selected(clusters, cfg)]
        for task in fut.as_completed(tasks):
            out.extend(task.result())
    out = dedupe(cfg, out)
    save(conn, cfg, run_id, out)
    return out


def llm_workers(cfg: dict) -> int:
    return max(1, int(cfg.get("llm_workers", 1)))


def safe_plan(cfg: dict, cid: str, rows: list[dict]) -> list[dict]:
    try:
        return plan_cluster(cfg, cid, rows)
    except Exception as exc:
        log.info("llm_cluster_dead", cluster=cid, err=str(exc)[:160])
        return [bulkplan.plan(cfg, r) for r in rows]


def selected(clusters: dict, cfg: dict) -> list[tuple[str, list[dict]]]:
    cap = int(cfg.get("llm_cluster_limit", 24))
    item_cap = int(cfg.get("llm_item_limit", 400))
    rows = sorted(clusters.items(), key=lambda kv: len(kv[1]), reverse=True)
    out = []
    total = 0
    for cid, vals in rows[:cap]:
        take = vals[: max(1, item_cap - total)]
        out.append((cid, take))
        total += len(take)
        if total >= item_cap:
            break
    return out


def plan_cluster(cfg: dict, cid: str, rows: list[dict]) -> list[dict]:
    sample = sample_rows(rows, int(cfg["cluster_item_cap"]))
    data = ollama.gen(cfg, ollama.prompt(cid, sample, cfg),
                      feature="planner")
    folder = folder_path(cfg, data.get("folder", "Temporary/NeedsReview"))
    out = [plan_item(cfg, r, folder, data, cid) for r in rows]
    return [r for r in out if r]


def sample_rows(rows: list[dict], cap: int) -> list[dict]:
    ranked = sorted(rows, key=lambda r: len(r.get("text", "")), reverse=True)
    return ranked[:cap]


def folder_path(cfg: dict, rel: str) -> Path:
    clean = Path(str(rel).strip("/"))
    dst = Path(cfg["target"]) / clean
    return dst if fs.inside(str(dst), cfg["target"]) else fallback(cfg)


def fallback(cfg: dict) -> Path:
    return Path(cfg["target"]) / "Temporary" / "NeedsReview"


def plan_item(cfg: dict, rec: dict, folder: Path, data: dict,
              cid: str) -> dict | None:
    if rec["kind"] != "dir" and bulkplan.unit_key(rec) != rec["path"]:
        return None
    base = bulkplan.plan(cfg, rec)
    if base["state"] != state.PLANNED:
        return base
    if weak_folder(cfg, folder):
        return base
    name = item_name(rec, data)
    dst = folder / name
    why = str(data.get("reason", "context cluster"))
    return {"id": rec["id"], "src": rec["path"], "dst": str(dst),
            "state": state.PLANNED, "why": why[:500], "cluster": cid}


def weak_folder(cfg: dict, folder: Path) -> bool:
    rel = folder.relative_to(Path(cfg["target"]))
    return str(rel) == "Temporary/NeedsReview"


def item_name(rec: dict, data: dict) -> str:
    names = {x.get("id"): x.get("name") for x in data.get("items", [])}
    raw = names.get(rec["id"]) or Path(rec["path"]).name
    clean = fs.safe_name(str(raw), Path(rec["path"]).stem)
    return with_ext(clean, Path(rec["path"]).suffix, rec["kind"])


def with_ext(name: str, ext: str, kind: str) -> str:
    if kind == "dir" or not ext or name.lower().endswith(ext.lower()):
        return name
    return name + ext


def dedupe(cfg: dict, rows: list[dict]) -> list[dict]:
    used = set()
    for rec in rows:
        dst = fs.unique(Path(rec["dst"]))
        while str(dst) in used:
            dst = fs.unique(Path(str(dst) + "-2"))
        rec["dst"] = str(dst)
        used.add(rec["dst"])
    return rows


def save(conn, cfg: dict, run_id: str, rows: list[dict]) -> None:
    for rec in rows:
        db.add_plan(conn, run_id, rec)
    all_rows = db.plan_rows(conn, run_id)
    db.json_dump(cfgmod.state_dir(cfg, "plans") / f"{run_id}.ndjson", all_rows)
    conn.commit()
