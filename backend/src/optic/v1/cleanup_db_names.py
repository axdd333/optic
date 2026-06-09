#!/usr/bin/env python3
# DEPRECATED — one-shot utility, never imported by any server code.
# Used during development to clean workstream names in the DB.
# Safe to archive. No runtime dependency on this script.
"""Optic V1 — DB Workstream Name Cleanup

Scans the V1 signal database (v1.db) and cleans ugly workstream names
like 'HTTPS ABX XTCFTW Com' into human-readable labels.

Run:
    python3 cleanup_db_names.py

Environment:
    OPTIC_DATA_DIR  — override DB directory (default: ~/.optic)
    DRY_RUN=1       — print changes without committing
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path


# ── Path resolution ──────────────────────────────────────────────────

def get_db_path() -> Path:
    data_dir = Path(os.environ.get("OPTIC_DATA_DIR", Path.home() / ".optic"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "v1.db"


# ── Name cleaner (mirrors startup.py _is_noise_token + _clean_name) ──

_NOISE_SET = {
    # --- URL fragments & protocols (never meaningful) ---
    "https", "http", "www", "com", "org", "net", "html", "json", "xml",
    "css", "js", "php", "asp", "jsp", "htm", "xhtml",
    # --- TLDs and protocol schemes ---
    "io", "co", "uk", "de", "fr", "dev", "app", "ai", "gov", "edu",
    "ftp", "sftp", "ssh", "tcp", "udp", "ip", "tls",
    # --- Known random/noise tokens from real data ---
    "abx", "xtcftw", "rspace", "pyasn1",
    # --- Very generic filesystem cruft ---
    "screenshot", "screenshots", "temp", "untitled", "node_modules",
    "desktop", "downloads", "inbox",
    # --- Duplicate/copy markers ---
    "copy", "backup", "final", "draft",
    # --- Extremely generic (only noise when isolated; kept minimal) ---
}

_KNOWN_ACRONYMS = {
    "ai", "api", "ssl", "dns", "pdf", "css", "js", "ml",
    "ui", "ux", "nlp", "gpu", "cpu", "ram", "ssd",
    "vm", "ci", "cd", "aws", "gcp", "sql", "nosql", "db",
    "html", "json", "xml", "scss", "sass",
    "yaml", "toml", "csv", "tsv", "rss", "svg",
    "md", "pdf", "png", "jpg", "jpeg", "gif", "mp4",
    "wip", "todo", "readme", "changelog", "license",
    # Note: URL protocols (http, https, ftp, ssh, tcp, ip, udp)
    # are deliberately NOT included — they are noise, not display acronyms.
}

_DISPLAY_ACRONYMS = {
    "ai", "api", "ssl", "dns", "pdf", "css", "js", "ml",
    "ui", "ux", "nlp", "gpu", "cpu", "ram", "ssd",
    "vm", "ci", "cd", "aws", "gcp", "sql", "nosql", "db",
    "html", "json", "xml", "scss", "sass",
    "yaml", "toml", "csv", "tsv", "rss", "svg",
    "md", "wip", "todo", "readme",
}


_COMMON_TWO_LETTER = {
    "my", "an", "of", "to", "in", "it", "is", "on", "at", "be", "by",
    "do", "go", "he", "if", "no", "so", "we", "up", "us", "or", "as",
}


def is_noise_token(w: str) -> bool:
    wl = w.lower()
    # Known acronyms are never noise — check before noise set
    if wl in _KNOWN_ACRONYMS:
        return False
    if wl in _NOISE_SET:
        return True
    if re.fullmatch(r"[0-9a-f]{6,}", wl):
        return True
    # All-consonant gibberish with no vowels (but allow numbers)
    if len(wl) >= 4 and not re.search(r"[aeiouy]", wl) and not re.search(r"\d", wl):
        return True
    if len(wl) >= 4 and wl == wl.upper() and wl != wl.lower():
        if wl not in _KNOWN_ACRONYMS:
            return True
    return False


def token_to_display(w: str) -> str:
    if w.upper() in _DISPLAY_ACRONYMS:
        return w.upper()
    if len(w) <= 2:
        if w.lower() in _COMMON_TWO_LETTER:
            return w[0].upper() + w[1:].lower()
        return w.upper()
    return w[0].upper() + w[1:].lower()


def clean_name(raw: str) -> str:
    """Clean a workstream name, removing URL fragments and noise."""
    if not raw or not raw.strip():
        return "Other"
    name = raw.strip()
    for prefix in ["set-up-", "setup-", "config-"]:
        if name.lower().startswith(prefix):
            name = name[len(prefix):]
            break  # only strip one prefix
    name = name.replace("-", " ").replace("_", " ")
    words = name.split()
    meaningful = [w for w in words if not is_noise_token(w)]
    if not meaningful:
        return "Other"
    cleaned = [token_to_display(w) for w in meaningful]
    result = " ".join(cleaned).strip()
    if result and len(result.split()) >= 4 and result == result.upper():
        return "Other"
    return result or "Other"


# ── DB cleanup ───────────────────────────────────────────────────────

def cleanup_db(db_path: Path, dry_run: bool = False) -> list[dict]:
    """Scan v1.db signals, clean workstream_name in metadata, return changelog."""
    if not db_path.exists():
        print(f"DB not found: {db_path} — nothing to clean.", file=sys.stderr)
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Find all signal rows with workstream_name in metadata
    rows = conn.execute(
        "SELECT id, metadata FROM signals WHERE metadata LIKE '%workstream_name%'"
    ).fetchall()

    changes = []
    for row in rows:
        try:
            meta = json.loads(row["metadata"] or "{}")
        except json.JSONDecodeError:
            continue

        old_name = meta.get("workstream_name", "")
        if not old_name:
            continue

        new_name = clean_name(old_name)
        if new_name == old_name:
            continue

        changes.append({
            "signal_id": row["id"],
            "old_name": old_name,
            "new_name": new_name,
        })

        if not dry_run:
            meta["workstream_name"] = new_name
            conn.execute(
                "UPDATE signals SET metadata = ? WHERE id = ?",
                (json.dumps(meta, ensure_ascii=False), row["id"]),
            )

    if not dry_run and changes:
        conn.commit()

    conn.close()
    return changes


# ── Test harness ─────────────────────────────────────────────────────

def test_cleaner():
    """Test the name cleaner against known-ugly inputs."""
    test_cases = [
        # --- Noise-dominated names (should collapse to Other) ---
        ("HTTPS ABX XTCFTW Com", "Other"),
        ("HTTPS-ABX-XTCFTW-Com", "Other"),
        ("https www example com", "Example"),  # "example" is a real word, not URL noise
        ("a1b2c3d4e5f6 temp backup", "Other"),
        # --- Normal names should pass through ---
        ("My Research Notes", "My Research Notes"),
        ("AI ML Project", "AI ML Project"),
        ("Hello World", "Hello World"),
        ("Resume & CV", "Resume & CV"),
        ("Photos 2024", "Photos 2024"),
        ("Writing & Blog", "Writing & Blog"),
        ("some Data Old", "Some Data Old"),
        # --- Setup prefix stripping ---
        ("setup-config-files", "Config Files"),
        # --- Common project names ---
        ("actual-project-name", "Actual Project Name"),
        ("node_modules dist build", "Node Modules Dist Build"),
        # --- Names with noise tokens partially cleaned ---
        ("test-samples-backups", "Test Samples Backups"),
        ("just-a-test", "Just A Test"),
        ("simple-docs", "Simple Docs"),
        # --- All-noise: nothing meaningful survives ---
        ("screenshot temp inbox", "Other"),
        ("copy backup draft", "Other"),
    ]

    passed = 0
    failed = 0
    for raw, expected in test_cases:
        result = clean_name(raw)
        status = "PASS" if result == expected else "FAIL"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {raw!r:40s} → {result!r:25s} (expected {expected!r})")

    print(f"\n  Results: {passed} passed, {failed} failed")
    return failed == 0


# ── Main ─────────────────────────────────────────────────────────────

def main():
    dry_run = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")
    db_path = get_db_path()

    print("=" * 70)
    print("Optic V1 — Workstream Name Cleanup")
    print("=" * 70)
    print(f"  DB path:  {db_path}")
    print(f"  Dry run:  {dry_run}")
    print()

    # Run tests first
    print("Running cleaner tests:")
    ok = test_cleaner()

    print()
    print("Scanning DB for ugly workstream names...")

    if not db_path.exists():
        print(f"\n  DB does not exist at {db_path}")
        print("  No cleanup needed — Optic has not been seeded yet.")
        print("\n  The cleaner code is in place and will produce human-readable")
        print("  names from the next scan onward.")
        return 0 if ok else 1

    changes = cleanup_db(db_path, dry_run=dry_run)

    if not changes:
        print("  All workstream names are already clean.")
    else:
        print(f"  Found {len(changes)} names to clean:\n")
        for c in changes:
            print(f"    [{c['signal_id']}]")
            print(f"      OLD: {c['old_name']}")
            print(f"      NEW: {c['new_name']}")
            print()

        if dry_run:
            print("  DRY RUN — no changes committed. Remove DRY_RUN=1 to apply.")
        else:
            print(f"  COMMITTED — {len(changes)} names cleaned.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
