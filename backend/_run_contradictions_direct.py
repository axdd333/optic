#!/usr/bin/env python3
"""Run the contradiction engine directly against seeded claims in v1.db."""
import sys
sys.path.insert(0, 'src')

import json
import sqlite3
import os
from pathlib import Path
from uuid import UUID

# Set DB_PATH to match server.py
DB_PATH = Path(os.environ.get("OPTIC_DB_PATH",
    str(Path(__file__).resolve().parent / ".optic" / "v1.db")))
print(f"DB path: {DB_PATH}")
print(f"DB exists: {DB_PATH.exists()}, size: {DB_PATH.stat().st_size if DB_PATH.exists() else 'N/A'}")

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

# Load claims
claim_rows = conn.execute("SELECT * FROM claims").fetchall()
print(f"\nClaims loaded: {len(claim_rows)}")

# Show claim distribution
lens_counts = {}
for r in claim_rows:
    lens = r["audience_lens"]
    lens_counts[lens] = lens_counts.get(lens, 0) + 1
print(f"Claims by lens: {dict(sorted(lens_counts.items()))}")

# Load artifacts
artifact_rows = conn.execute("SELECT * FROM artifacts").fetchall()
print(f"Artifacts loaded: {len(artifact_rows)}")

# Import models and engine
from optic.v1.models import (
    InferenceClaim, Artifact, Entity, ConfidenceBand, Severity,
)
from optic.v1.contradiction import ContradictionEngine

def row_to_claim(r):
    """Convert a sqlite3.Row to InferenceClaim."""
    supp = json.loads(r["supporting_evidence"] or "[]")
    weak = json.loads(r["weakening_evidence"] or "[]")
    repairs = json.loads(r["repair_options"] or "[]")
    
    return InferenceClaim(
        id=UUID(r["id"]),
        title=r["title"],
        audience_lens=r["audience_lens"],
        claim=r["claim"],
        confidence_band=ConfidenceBand(r["confidence_band"]) if r["confidence_band"] in ["high","medium","low"] else ConfidenceBand.MEDIUM,
        evidence_count=r["evidence_count"] or 0,
        supporting_evidence=[UUID(x) for x in supp if x] if isinstance(supp, list) else [],
        weakening_evidence=[UUID(x) for x in weak if x] if isinstance(weak, list) else [],
        source_gaps=json.loads(r["source_gaps"] or "[]") if isinstance(r["source_gaps"], str) else r["source_gaps"] or [],
        recency=r["recency"] or "recent",
        severity=Severity(r["severity"]) if r["severity"] in ["low","medium","high","critical"] else Severity.LOW,
        actionability=r["actionability"] or "medium",
        possible_consequence=r["possible_consequence"] or "",
        counterargument=r["counterargument"] or "",
        repair_options=[UUID(x) for x in repairs if x] if isinstance(repairs, list) else [],
        model_version=r["model_version"] or "v1",
        not_a_verdict=bool(r["not_a_verdict"]),
        generated_at=r["generated_at"] or "",
    )

def row_to_artifact(r):
    """Convert a sqlite3.Row to Artifact."""
    meta = {}
    try:
        meta = json.loads(r["metadata"] or "{}")
    except:
        pass
    return Artifact(
        id=UUID(r["id"]),
        source_id=UUID(r["source_id"]) if r["source_id"] and r["source_id"] != "scan" else UUID("00000000-0000-0000-0000-000000000000"),
        type=r["type"],
        raw_hash=r["raw_hash"] or "",
        encrypted_path=r["encrypted_path"] or "",
        metadata=meta,
        is_public=bool(r["is_public"]),
        content_preview=r["content_preview"] or "",
        created_at=r["created_at"] or "",
    )

claims = [row_to_claim(r) for r in claim_rows]
artifacts = [row_to_artifact(r) for r in artifact_rows]

print(f"\nParsed {len(claims)} claims and {len(artifacts)} artifacts")

# Run the engine
engine = ContradictionEngine()

# Only run claim_contradictions to verify the fix
print("\n--- Running find_claim_contradictions ---")
contradictions = engine.find_claim_contradictions(claims)

print(f"\nclaim_opposition contradictions found: {len(contradictions)}")

# Show severity breakdown
sev_counts = {}
for c in contradictions:
    sev = c.severity.value
    sev_counts[sev] = sev_counts.get(sev, 0) + 1
print(f"By severity: {dict(sorted(sev_counts.items()))}")

# Also run full audit for completeness
print("\n--- Running full audit ---")
full_contradictions = engine.run_full_audit(claims, artifacts, [])

print(f"\nTotal contradictions (all categories): {len(full_contradictions)}")

# Breakdown
cat_counts = {}
for c in full_contradictions:
    cat = c.category
    cat_counts[cat] = cat_counts.get(cat, 0) + 1
print(f"By category: {dict(sorted(cat_counts.items()))}")

# Store in DB (clear existing first)
conn.execute("DELETE FROM contradictions")
conn.execute("DELETE FROM contradiction_claims")
conn.execute("DELETE FROM contradiction_artifacts")

now = "2025-01-01T00:00:00+00:00"
for c in full_contradictions:
    conn.execute(
        "INSERT INTO contradictions(id, category, description, claim_ids, "
        "artifact_ids, severity, audience_affected, resolution_suggestion, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (str(c.id), c.category, c.description,
         json.dumps([str(x) for x in c.claim_ids]),
         json.dumps([str(x) for x in c.artifact_ids]),
         c.severity.value,
         json.dumps(c.audience_affected),
         c.resolution_suggestion, now)
    )
    for cid in c.claim_ids:
        conn.execute(
            "INSERT OR IGNORE INTO contradiction_claims(contradiction_id, claim_id) "
            "VALUES(?, ?)", (str(c.id), str(cid)))
    for aid in c.artifact_ids:
        conn.execute(
            "INSERT OR IGNORE INTO contradiction_artifacts(contradiction_id, artifact_id) "
            "VALUES(?, ?)", (str(c.id), str(aid)))

conn.commit()

# Verify
total = conn.execute("SELECT COUNT(*) as c FROM contradictions").fetchone()["c"]
claim_opp = conn.execute(
    "SELECT COUNT(*) as c FROM contradictions WHERE category='claim_opposition'"
).fetchone()["c"]
print(f"\n--- DB Verification ---")
print(f"Total contradictions in DB: {total}")
print(f"claim_opposition in DB: {claim_opp}")

# Show a few samples
samples = conn.execute(
    "SELECT category, severity, description FROM contradictions "
    "WHERE category='claim_opposition' LIMIT 5"
).fetchall()
print(f"\nSample claim_opposition contradictions:")
for s in samples:
    print(f"  [{s['severity']}] {s['description'][:120]}")

conn.close()
print("\nDone.")
