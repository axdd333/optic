#!/usr/bin/env python3
"""Seed the V1 database — lightweight, no FastAPI dependency."""
import sys, os, json, hashlib, sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

# Use dynamic path resolution — bootstrap-safe (Invariant #13)
SCRIPT_DIR = Path(__file__).resolve().parent.parent  # backend/
sys.path.insert(0, str(SCRIPT_DIR / "src"))

# ── Create DB ────────────────────────────────────────────────────
v1_db = Path.home() / ".optic" / "v1.db"
v1_db.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(str(v1_db))
conn.row_factory = sqlite3.Row
conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT UNIQUE, settings TEXT,
        local_mode INTEGER DEFAULT 1, encryption_key_ref TEXT,
        is_test_user INTEGER DEFAULT 0,
        created_at TEXT, updated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS artifacts (
        id TEXT PRIMARY KEY, source_id TEXT, type TEXT, raw_hash TEXT,
        encrypted_path TEXT, metadata TEXT, is_public INTEGER DEFAULT 0,
        content_preview TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS signals (
        id TEXT PRIMARY KEY, category TEXT, description TEXT,
        severity TEXT DEFAULT 'low', source_artifact_ids TEXT,  /* DEPRECATED */
        metadata TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS claims (
        id TEXT PRIMARY KEY, title TEXT, audience_lens TEXT, claim TEXT,
        confidence_band TEXT, evidence_count INTEGER,
        supporting_evidence TEXT,   /* DEPRECATED — use claim_supporting_evidence */
        weakening_evidence TEXT,    /* DEPRECATED — use claim_weakening_evidence */
        source_gaps TEXT, recency TEXT, severity TEXT,
        actionability TEXT, possible_consequence TEXT, counterargument TEXT,
        repair_options TEXT,        /* DEPRECATED — use claim_repair_options */
        model_version TEXT, not_a_verdict INTEGER DEFAULT 1,
        generated_at TEXT
    );
    CREATE TABLE IF NOT EXISTS contradictions (
        id TEXT PRIMARY KEY, category TEXT, description TEXT,
        claim_ids TEXT, artifact_ids TEXT, severity TEXT,
        audience_affected TEXT, resolution_suggestion TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS risks (
        id TEXT PRIMARY KEY, category TEXT, description TEXT,
        severity TEXT, linked_claim_ids TEXT, linked_artifact_ids TEXT,
        audience_affected TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS repairs (
        id TEXT PRIMARY KEY, title TEXT, affected_audience TEXT,
        linked_claim_id TEXT REFERENCES claims(id) ON DELETE SET NULL,
        linked_evidence_ids TEXT, impact REAL DEFAULT 0.5,
        effort REAL DEFAULT 0.5, urgency REAL DEFAULT 0.5,
        reversibility REAL DEFAULT 0.5, cost_cents INTEGER DEFAULT 0,
        exact_steps TEXT, expected_effect TEXT, risk_of_overcorrecting TEXT,
        before_measurement TEXT, after_measurement TEXT,
        status TEXT DEFAULT 'pending'
    );
    CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY, user_id TEXT, version INTEGER DEFAULT 1,
        audit_mode TEXT, scope TEXT, source_count INTEGER, artifact_count INTEGER,
        claim_count INTEGER, contradiction_count INTEGER, risk_count INTEGER,
        repair_count INTEGER, sections TEXT, export_policy TEXT,
        created_at TEXT, snapshot_id TEXT
    );

    -- ═══ JUNCTION TABLES — FOREIGN KEY ENFORCEMENT (Invariant #10) ═══

    CREATE TABLE IF NOT EXISTS claim_supporting_evidence (
        claim_id    TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        PRIMARY KEY (claim_id, artifact_id)
    ) WITHOUT ROWID;

    CREATE TABLE IF NOT EXISTS claim_weakening_evidence (
        claim_id    TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        PRIMARY KEY (claim_id, artifact_id)
    ) WITHOUT ROWID;

    CREATE TABLE IF NOT EXISTS claim_repair_options (
        claim_id  TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        repair_id TEXT NOT NULL REFERENCES repairs(id) ON DELETE CASCADE,
        PRIMARY KEY (claim_id, repair_id)
    ) WITHOUT ROWID;

    CREATE TABLE IF NOT EXISTS risk_linked_claims (
        risk_id  TEXT NOT NULL REFERENCES risks(id) ON DELETE CASCADE,
        claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        PRIMARY KEY (risk_id, claim_id)
    ) WITHOUT ROWID;

    CREATE TABLE IF NOT EXISTS risk_linked_artifacts (
        risk_id     TEXT NOT NULL REFERENCES risks(id) ON DELETE CASCADE,
        artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        PRIMARY KEY (risk_id, artifact_id)
    ) WITHOUT ROWID;

    CREATE TABLE IF NOT EXISTS repair_linked_evidence (
        repair_id   TEXT NOT NULL REFERENCES repairs(id) ON DELETE CASCADE,
        artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        PRIMARY KEY (repair_id, artifact_id)
    ) WITHOUT ROWID;

    CREATE TABLE IF NOT EXISTS contradiction_claims (
        contradiction_id TEXT NOT NULL REFERENCES contradictions(id) ON DELETE CASCADE,
        claim_id         TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
        PRIMARY KEY (contradiction_id, claim_id)
    ) WITHOUT ROWID;

    CREATE TABLE IF NOT EXISTS contradiction_artifacts (
        contradiction_id TEXT NOT NULL REFERENCES contradictions(id) ON DELETE CASCADE,
        artifact_id      TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        PRIMARY KEY (contradiction_id, artifact_id)
    ) WITHOUT ROWID;

    CREATE TABLE IF NOT EXISTS signal_source_artifacts (
        signal_id   TEXT NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
        artifact_id TEXT NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
        PRIMARY KEY (signal_id, artifact_id)
    ) WITHOUT ROWID;
""")
conn.commit()

# Check if already seeded
cnt = conn.execute("SELECT COUNT(*) as c FROM claims").fetchone()["c"]
if cnt > 0:
    print(f"Already seeded: {cnt} claims exist")
    conn.close()
    sys.exit(0)

# ── Scan filesystem ──────────────────────────────────────────────
from optic.v1.startup import scan_all, build_workstreams, generate_narratives, _seed_from_scan

print("Scanning filesystem...")
files = scan_all()
workstreams = build_workstreams(files)
print(f"Scanned {len(files)} files → {len(workstreams)} workstreams")

if len(workstreams) >= 2 and len(files) >= 20:
    n = _seed_from_scan(conn, workstreams, files)
    print(f"Seeded: {n} claims, {len(workstreams)} workstreams")
else:
    # HONEST EMPTY STATE — Invariant #8: No Fake Completeness
    # Never insert template/fake/demo data. Never fabricate evidence counts.
    # Return cleanly with zero claims rather than lying to the user.
    print(f"HONEST EMPTY STATE: Only {len(files)} files across {len(workstreams)} workstreams.")
    print("Not enough data for meaningful inference. No fake data will be inserted.")
    print("Re-run this script when more files are available in Desktop, Documents, or Projects.")
    conn.close()
    sys.exit(0)

# Populate junction tables (Invariant #10 FK enforcement)
try:
    from optic.v1.server import _migrate_v2_junction_tables as _migrate
    _migrate(conn)
except Exception as exc:
    print(f"  (junction migration skipped: {exc})")

# Report
for table in ['claims','contradictions','risks','repairs']:
    cnt = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()["c"]
    print(f"  {table}: {cnt} rows")

# Junction table report
for jt in ['claim_supporting_evidence','claim_weakening_evidence',
           'claim_repair_options','repair_linked_evidence']:
    cnt = conn.execute(f"SELECT COUNT(*) as c FROM {jt}").fetchone()["c"]
    print(f"  {jt}: {cnt} rows")

conn.close()
print("Done.")
