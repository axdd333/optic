#!/usr/bin/env python3
"""
Optic State Directory Cleanup — Disk Crisis Response
====================================================
Idempotent, recoverable, evidence-gated state cleanup.

Operations (all gated by mtime threshold, default 7 days):
  1. purge_dead       — rm dead/ ndjson files older than threshold
  2. archive_extracts — tar.gz old extracts, rm originals
  3. archive_graphs   — tar.gz old graph JSON, rm originals
  4. monitor          — report disk usage for /api/health

Usage:
  python3 cleanup_state.py --state-dir .ctxorg/state [--dry-run] [--days 7]
  python3 cleanup_state.py --state-dir .ctxorg/state --emergency 500
  python3 cleanup_state.py --state-dir .ctxorg/state --monitor-only

Emergency mode (--emergency MB): uses 1-day threshold and aggressive
compression when free disk < threshold.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────

def now_ts() -> float:
    return time.time()


def age_days(path: Path) -> float:
    """Days since last modification (mtime)."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return float("inf")
    return (now_ts() - mtime) / 86400.0


def size_mb(path: Path) -> float:
    """Size in megabytes, recursive for dirs."""
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = Path(root) / f
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


def free_mb(path: str | Path) -> int:
    """Free disk space in MB on the volume containing `path`."""
    usage = shutil.disk_usage(str(path))
    return usage.free // (1024 * 1024)


def human(n: float) -> str:
    if n >= 1024:
        return f"{n/1024:.1f}G"
    if n >= 1:
        return f"{n:.0f}M"
    return f"{n*1024:.0f}K"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def utc_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── operations ───────────────────────────────────────────────────────

def purge_dead(state_dir: Path, days: float, dry_run: bool) -> dict:
    """
    Remove dead/ ndjson files older than `days`.
    Returns {count, freed_mb, files: [...]}.
    """
    dead_dir = state_dir / "dead"
    if not dead_dir.is_dir():
        return {"count": 0, "freed_mb": 0.0, "files": []}

    freed = 0.0
    removed: list[str] = []
    for f in sorted(dead_dir.iterdir()):
        if not f.is_file():
            continue
        age = age_days(f)
        if age < days:
            continue
        mb = size_mb(f)
        log(f"DEAD  rm  {f.name}  ({human(mb)}, {age:.0f}d old)")
        if not dry_run:
            try:
                f.unlink()
            except OSError as exc:
                log(f"DEAD  FAIL {f.name}: {exc}")
                continue
        freed += mb
        removed.append(str(f.name))

    return {"count": len(removed), "freed_mb": round(freed, 1), "files": removed}


def archive_extracts(state_dir: Path, days: float, dry_run: bool,
                     archive_dir: Path | None = None) -> dict:
    """
    Archive extract .txt files older than `days` into a compressed tar.gz,
    then delete the originals.
    Returns {count, original_mb, archive_mb, archive_path, files: [...]}.
    """
    extracts_dir = state_dir / "extracts"
    if not extracts_dir.is_dir():
        return {"count": 0, "original_mb": 0.0, "archive_mb": 0.0,
                "archive_path": "", "files": []}

    if archive_dir is None:
        archive_dir = state_dir / "archives"
    ensure_dir(archive_dir)

    old_files: list[Path] = []
    original_mb = 0.0
    for f in extracts_dir.iterdir():
        if not f.is_file():
            continue
        if age_days(f) >= days:
            old_files.append(f)
            original_mb += size_mb(f)

    if not old_files:
        log(f"EXTRACTS  nothing older than {days:.0f}d")
        return {"count": 0, "original_mb": 0.0, "archive_mb": 0.0,
                "archive_path": "", "files": []}

    archive_name = f"extracts-{utc_label()}.tar.gz"
    archive_path = archive_dir / archive_name

    log(f"EXTRACTS  archiving {len(old_files)} files ({human(original_mb)}) → {archive_name}")

    if not dry_run:
        with tarfile.open(archive_path, "w:gz") as tar:
            for f in old_files:
                tar.add(f, arcname=f.name)
        archive_sz = size_mb(archive_path)
        log(f"EXTRACTS  archive written ({human(archive_sz)})")

        # Delete originals only after successful archive
        for f in old_files:
            try:
                f.unlink()
            except OSError as exc:
                log(f"EXTRACTS  FAIL unlink {f.name}: {exc}")
    else:
        archive_sz = 0.0

    return {
        "count": len(old_files),
        "original_mb": round(original_mb, 1),
        "archive_mb": round(archive_sz, 1),
        "archive_path": str(archive_path),
        "files": [f.name for f in old_files[:100]],  # cap file list
    }


def archive_graphs(state_dir: Path, days: float, dry_run: bool,
                   archive_dir: Path | None = None) -> dict:
    """
    Archive graph JSON files older than `days` into compressed tar.gz,
    then delete originals.
    Returns {count, original_mb, archive_mb, archive_path, files: [...]}.
    """
    graphs_dir = state_dir / "graphs"
    if not graphs_dir.is_dir():
        return {"count": 0, "original_mb": 0.0, "archive_mb": 0.0,
                "archive_path": "", "files": []}

    if archive_dir is None:
        archive_dir = state_dir / "archives"
    ensure_dir(archive_dir)

    old_files: list[Path] = []
    original_mb = 0.0
    for f in graphs_dir.iterdir():
        if not f.is_file():
            continue
        if age_days(f) >= days:
            old_files.append(f)
            original_mb += size_mb(f)

    if not old_files:
        log(f"GRAPHS  nothing older than {days:.0f}d")
        return {"count": 0, "original_mb": 0.0, "archive_mb": 0.0,
                "archive_path": "", "files": []}

    archive_name = f"graphs-{utc_label()}.tar.gz"
    archive_path = archive_dir / archive_name

    log(f"GRAPHS  archiving {len(old_files)} files ({human(original_mb)}) → {archive_name}")

    if not dry_run:
        with tarfile.open(archive_path, "w:gz") as tar:
            for f in old_files:
                tar.add(f, arcname=f.name)
        archive_sz = size_mb(archive_path)
        log(f"GRAPHS  archive written ({human(archive_sz)})")

        for f in old_files:
            try:
                f.unlink()
            except OSError as exc:
                log(f"GRAPHS  FAIL unlink {f.name}: {exc}")
    else:
        archive_sz = 0.0

    return {
        "count": len(old_files),
        "original_mb": round(original_mb, 1),
        "archive_mb": round(archive_sz, 1),
        "archive_path": str(archive_path),
        "files": [f.name for f in old_files],
    }


# ── monitoring ───────────────────────────────────────────────────────

def monitor(state_dir: Path) -> dict:
    """
    Full disk monitoring snapshot for /api/health enrichment.
    Returns {state_dir, free_mb, dirs: {name: {size_mb, file_count, oldest_days}},
              total_mb, critical}.
    """
    result: dict = {
        "state_dir": str(state_dir.resolve()),
        "free_mb": free_mb(state_dir),
        "dirs": {},
        "total_mb": 0.0,
        "critical": False,
        "ts": now_ts(),
    }

    # Emergency thresholds (per Invariant 14: honest state reporting)
    total_free = result["free_mb"]
    critical_mb = int(os.environ.get("OPTIC_DISK_CRITICAL_MB", "500"))
    warn_mb = int(os.environ.get("OPTIC_DISK_WARN_MB", "2000"))
    result["critical"] = total_free < critical_mb
    result["warning"] = total_free < warn_mb
    result["threshold_critical_mb"] = critical_mb
    result["threshold_warn_mb"] = warn_mb

    # Per-subdirectory breakdown
    for name in ["dead", "extracts", "graphs", "backups", "exports",
                 "edits", "scans", "plans", "atlas", "applied",
                 "integrations", "labels"]:
        d = state_dir / name
        if not d.is_dir():
            continue
        files = [f for f in d.iterdir() if f.is_file()]
        sz = sum((f.stat().st_size for f in files if f.exists()),
                 start=0) / (1024 * 1024)
        ages = [age_days(f) for f in files]
        result["dirs"][name] = {
            "size_mb": round(sz, 1),
            "file_count": len(files),
            "oldest_days": round(max(ages) if ages else 0, 1),
            "newest_days": round(min(ages) if ages else 0, 1),
        }
        result["total_mb"] += sz

    result["total_mb"] = round(result["total_mb"], 1)
    return result


# ── main ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Optic state directory cleanup")
    ap.add_argument("--state-dir", default=".ctxorg/state",
                    help="Path to state directory (default: .ctxorg/state)")
    ap.add_argument("--days", type=float, default=7.0,
                    help="Age threshold in days (default: 7)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be done, take no action")
    ap.add_argument("--emergency", type=int, default=0, metavar="MB",
                    help="Emergency mode: use 1d threshold if free < MB")
    ap.add_argument("--monitor-only", action="store_true",
                    help="Only print monitoring JSON and exit")
    ap.add_argument("--skip-dead", action="store_true",
                    help="Skip dead/ purge")
    ap.add_argument("--skip-extracts", action="store_true",
                    help="Skip extracts archive")
    ap.add_argument("--skip-graphs", action="store_true",
                    help="Skip graphs archive")
    ap.add_argument("--output", "-o", default="",
                    help="Write result JSON to file")
    args = ap.parse_args()

    state_dir = Path(args.state_dir).resolve()
    if not state_dir.is_dir():
        print(f"ERROR: state_dir not found: {state_dir}", file=sys.stderr)
        sys.exit(1)

    # Monitoring always runs
    stats = monitor(state_dir)
    free_before = stats["free_mb"]
    total_before = stats["total_mb"]

    if args.monitor_only:
        print(json.dumps(stats, indent=2))
        sys.exit(0)

    # Determine threshold
    days = args.days
    emergency = False
    if args.emergency > 0 and free_before < args.emergency:
        days = min(days, 1.0)
        emergency = True
        log(f"EMERGENCY MODE  free={free_before}M < threshold={args.emergency}M  "
            f"using {days}d window")

    dry = args.dry_run
    if dry:
        log(f"DRY RUN  state_dir={state_dir}  threshold={days}d  free_before={free_before}M")

    results: dict = {
        "run": utc_label(),
        "state_dir": str(state_dir),
        "dry_run": dry,
        "emergency": emergency,
        "threshold_days": days,
        "free_before_mb": free_before,
        "total_state_mb": total_before,
        "purge_dead": {},
        "archive_extracts": {},
        "archive_graphs": {},
    }

    # 1. Purge dead/
    if not args.skip_dead:
        results["purge_dead"] = purge_dead(state_dir, days, dry)

    # 2. Archive extracts/
    if not args.skip_extracts:
        results["archive_extracts"] = archive_extracts(state_dir, days, dry)

    # 3. Archive graphs/
    if not args.skip_graphs:
        results["archive_graphs"] = archive_graphs(state_dir, days, dry)

    # Post-cleanup monitoring
    post_stats = monitor(state_dir)
    results["free_after_mb"] = post_stats["free_mb"]
    freed = post_stats["free_mb"] - free_before
    results["freed_mb"] = freed
    results["dirs_after"] = post_stats["dirs"]

    # Summary
    total_freed = (
        results["purge_dead"].get("freed_mb", 0)
        + results["archive_extracts"].get("original_mb", 0)
        + results["archive_graphs"].get("original_mb", 0)
    )
    results["total_files_removed"] = (
        results["purge_dead"].get("count", 0)
        + results["archive_extracts"].get("count", 0)
        + results["archive_graphs"].get("count", 0)
    )
    results["total_reclaimed_mb"] = round(total_freed, 1)

    log("")
    log(f"DONE  removed {results['total_files_removed']} files  "
        f"reclaimed {human(results['total_reclaimed_mb'])}  "
        f"free: {free_before}M → {post_stats['free_mb']}M "
        f"({'OK' if not post_stats['critical'] else 'CRITICAL'})")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
        log(f"result → {out_path}")

    # Print JSON summary to stdout for script consumers
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
