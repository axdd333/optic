from __future__ import annotations

import argparse
import json
import time

from . import atlas, cfg as cfgmod, db, doctor, docedit, health
from . import cleanup
from . import bulkplan, deep, ingest, labels, latent, mover, planner, scan
from . import screens
from . import server


def main() -> int:
    args = parse()
    cfg = cfgmod.load(args.cfg)
    cfgmod.ensure(cfg)
    conn = db.open_db(cfg)
    run_id = args.run or time.strftime("%Y%m%d-%H%M%S")
    return dispatch(args, cfg, conn, run_id)


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=cmds())
    p.add_argument("--cfg", default="config.json")
    p.add_argument("--run")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--fast", action="store_true")
    return p.parse_args()


def cmds() -> list[str]:
    return ["doctor", "scan", "ingest", "map", "plan", "atlas",
            "apply", "rollback", "health", "serve", "run",
            "edit-plan", "edit-apply", "edit-rollback",
            "label-plan", "label-apply", "label-rollback",
            "bulk-plan", "cleanup-plan", "cleanup-apply",
            "cleanup-rollback", "screenshot-plan", "screenshot-apply",
            "screenshot-rollback", "deep-plan", "deep-apply",
            "deep-run"]


def dispatch(args, cfg: dict, conn, run_id: str) -> int:
    if args.fast and cfg.get("fast_model"):
        cfg["model"] = cfg["fast_model"]
    if args.cmd == "doctor":
        return show(doctor.check(cfg))
    if args.cmd == "health":
        return show(health.report(conn, cfg))
    if args.cmd == "serve":
        server.serve(cfg, args.host, args.port)
        return 0
    return work(args, cfg, conn, run_id)


def work(args, cfg: dict, conn, run_id: str) -> int:
    if args.cmd in ("edit-plan", "edit-apply", "edit-rollback"):
        return edit(args, cfg, conn, run_id)
    if args.cmd in ("label-plan", "label-apply", "label-rollback"):
        return label(args, cfg, conn, run_id)
    if args.cmd in ("cleanup-plan", "cleanup-apply", "cleanup-rollback"):
        return clean(args, cfg, run_id)
    if args.cmd in ("screenshot-plan", "screenshot-apply",
                    "screenshot-rollback"):
        return screenshot(args, cfg, run_id)
    if args.cmd in ("deep-plan", "deep-apply", "deep-run"):
        return deep_cmd(args, cfg, run_id)
    if args.cmd == "bulk-plan":
        bulkplan.run(conn, cfg, run_id)
        return finish(args, cfg, conn, run_id)
    if args.cmd in ("scan", "run"):
        scan.run(conn, cfg, run_id)
    if args.cmd in ("ingest", "run"):
        ingest.run(conn, cfg, run_id)
    if args.cmd in ("map", "plan", "atlas", "run"):
        clusters = latent.run(conn, cfg, run_id)
    if args.cmd in ("plan", "run"):
        planner.run(conn, cfg, run_id, clusters)
    return finish(args, cfg, conn, run_id)


def deep_cmd(args, cfg: dict, run_id: str) -> int:
    if args.cmd == "deep-plan":
        print(len(deep.plan(cfg, run_id)))
    if args.cmd == "deep-apply":
        require_yes(args)
        print(len(deep.apply(cfg, run_id)))
    if args.cmd == "deep-run":
        require_yes(args)
        print(len(deep.run(cfg, run_id)))
    return 0


def screenshot(args, cfg: dict, run_id: str) -> int:
    if args.cmd == "screenshot-plan":
        print(len(screens.plan(cfg, run_id)))
    if args.cmd == "screenshot-apply":
        require_yes(args)
        print(len(screens.apply(cfg, run_id)))
    if args.cmd == "screenshot-rollback":
        require_yes(args)
        print(len(screens.rollback(cfg, run_id)))
    return 0


def clean(args, cfg: dict, run_id: str) -> int:
    if args.cmd == "cleanup-plan":
        cleanup.plan(cfg, run_id)
    if args.cmd == "cleanup-apply":
        require_yes(args)
        cleanup.apply(cfg, run_id)
    if args.cmd == "cleanup-rollback":
        require_yes(args)
        cleanup.rollback(cfg, run_id)
    return 0


def label(args, cfg: dict, conn, run_id: str) -> int:
    if args.cmd == "label-plan":
        labels.plan(conn, cfg, run_id)
    if args.cmd == "label-apply":
        require_yes(args)
        labels.apply(cfg, run_id)
    if args.cmd == "label-rollback":
        require_yes(args)
        labels.rollback(cfg, run_id)
    return 0


def edit(args, cfg: dict, conn, run_id: str) -> int:
    if args.cmd == "edit-plan":
        docedit.plan(conn, cfg, run_id)
    if args.cmd == "edit-apply":
        require_yes(args)
        docedit.apply(conn, cfg, run_id)
    if args.cmd == "edit-rollback":
        require_yes(args)
        docedit.rollback(cfg, run_id)
    return 0


def finish(args, cfg: dict, conn, run_id: str) -> int:
    if args.cmd in ("atlas", "run", "plan"):
        path = atlas.write(conn, cfg, run_id)
        print(path)
    if args.cmd == "apply":
        require_yes(args)
        mover.apply(conn, cfg, run_id)
    if args.cmd == "rollback":
        require_yes(args)
        mover.rollback(conn, cfg, run_id)
    return 0


def require_yes(args) -> None:
    if not args.yes:
        raise SystemExit("add --yes after inspecting the atlas and manifest")


def show(data: dict) -> int:
    print(json.dumps(data, indent=2, sort_keys=True))
    return 0
