#!/usr/bin/env python3
"""Seed the V1 database — lightweight, no FastAPI dependency."""
import sys, os, json, hashlib, sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

sys.path.insert(0, '/Users/ahmedm/Developer/Projects/optic/backend/src')

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
        severity TEXT DEFAULT 'low', source_artifact_ids TEXT,
        metadata TEXT, created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS claims (
        id TEXT PRIMARY KEY, title TEXT, audience_lens TEXT, claim TEXT,
        confidence_band TEXT, evidence_count INTEGER, supporting_evidence TEXT,
        weakening_evidence TEXT, source_gaps TEXT, recency TEXT, severity TEXT,
        actionability TEXT, possible_consequence TEXT, counterargument TEXT,
        repair_options TEXT, model_version TEXT, not_a_verdict INTEGER DEFAULT 1,
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
        linked_claim_id TEXT, linked_evidence_ids TEXT, impact REAL DEFAULT 0.5,
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
    print("Not enough files for real scan. Seeding demo data...")
    now = datetime.now(timezone.utc).isoformat()
    uid = str(uuid4())
    conn.execute("INSERT INTO users(id, email, settings, local_mode, created_at) VALUES(?,?,?,?,?)",
                 (uid, "local@optic.app", "{}", 1, now))

    # Seed demo claims
    lenses = ["recruiter","investor","collaborator","creator","stranger"]
    demo_claims = [
        ("Recruiter read: frequent_topic", "recruiter", "A recruiter may notice consistent focus on AI/ML engineering", "high", 8),
        ("Recruiter read: project_velocity", "recruiter", "A recruiter may assess your project output as strong and consistent", "high", 12),
        ("Investor read: frequent_topic", "investor", "An investor may notice consistent focus on infrastructure and tooling", "medium", 5),
        ("Investor read: stale_bio", "investor", "An investor may read your LinkedIn headline as outdated", "low", 2),
        ("Collaborator read: project_velocity", "collaborator", "A collaborator may assess your project output as high-velocity", "high", 10),
        ("Creator read: public_association", "creator", "A creator/audience may associate you with AI tooling and open-source", "medium", 6),
        ("Stranger read: timeline_gap", "stranger", "A stranger may question a gap in your public timeline", "medium", 3),
        ("Recruiter read: inconsistent_title", "recruiter", "A recruiter may find your title inconsistent across platforms", "medium", 4),
        ("Investor read: controversial_phrase", "investor", "An investor may flag certain public statements as potentially controversial", "low", 2),
        ("Creator read: stale_bio", "creator", "A creator's audience may read outdated bios as neglect", "low", 1),
    ]
    for title, lens, claim, band, ev_count in demo_claims:
        conn.execute("INSERT INTO claims(id,title,audience_lens,claim,confidence_band,evidence_count,"
                     "supporting_evidence,weakening_evidence,source_gaps,recency,severity,"
                     "actionability,possible_consequence,counterargument,repair_options,"
                     "model_version,not_a_verdict,generated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (str(uuid4()), title, lens, claim, band, ev_count,
                      "[]", "[]", "[]", "recent", "medium", "medium",
                      "", "", "[]", "v1", 1, now))

    # Seed contradictions
    demo_contradictions = [
        ("job_title_mismatch", "Different titles found across 3 sources", "medium",
         "[\"recruiter\"]", "Align LinkedIn headline, resume, and portfolio titles"),
        ("timeline_gap", "730 day gap between 2022-01 and 2024-01 with no context", "low",
         "[\"recruiter\",\"investor\"]", "Add context for the gap period"),
        ("stale_context", "Public artifact is 450 days old and may appear current", "low",
         "[\"stranger\",\"recruiter\"]", "Update or archive the stale content"),
    ]
    for cat, desc, sev, audiences, resolution in demo_contradictions:
        conn.execute("INSERT INTO contradictions(id,category,description,claim_ids,artifact_ids,"
                     "severity,audience_affected,resolution_suggestion,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (str(uuid4()), cat, desc, "[]", "[]", sev, audiences, resolution, now))

    # Seed risks
    demo_risks = [
        ("STALE_CONTEXT", "LinkedIn profile may be outdated", "medium", "[\"recruiter\"]"),
        ("IDENTITY_MISMATCH", "Title mismatch between GitHub and LinkedIn", "medium", "[\"recruiter\",\"collaborator\"]"),
        ("TIMELINE_GAP", "Employment timeline has unexplained gap", "low", "[\"investor\"]"),
        ("OVEREXPOSURE", "Personal contact info visible in public repos", "high", "[\"stranger\"]"),
        ("SENSITIVE_INFERENCE", "Health-related repos may be inferred by AI agents", "medium", "[\"future_agent\"]"),
        ("CONTROVERSY_SURFACE", "Old public posts may be taken out of context", "low", "[\"creator\"]"),
        ("SEARCH_CONTAMINATION", "Search results mix you with a namesake", "medium", "[\"stranger\"]"),
    ]
    for cat, desc, sev, audiences in demo_risks:
        conn.execute("INSERT INTO risks(id,category,description,severity,linked_claim_ids,"
                     "linked_artifact_ids,audience_affected,created_at) VALUES(?,?,?,?,?,?,?,?)",
                     (str(uuid4()), cat, desc, sev, "[]", "[]", audiences, now))

    # Seed repairs
    demo_repairs = [
        ("Update LinkedIn headline", 0.8, 0.2, 0.7, 0.95, "1. Go to LinkedIn profile\n2. Edit headline\n3. Add current role"),
        ("Align titles across platforms", 0.7, 0.4, 0.6, 0.85, "1. List all platforms\n2. Pick canonical title\n3. Update all profiles"),
        ("Add context for timeline gap", 0.6, 0.3, 0.5, 0.9, "1. Identify gap period\n2. Write brief explanation\n3. Add to LinkedIn/portfolio"),
        ("Redact personal info from public repos", 0.9, 0.5, 0.8, 0.7, "1. Search repos for PII\n2. Remove or .gitignore\n3. Force-push clean history"),
        ("Archive old public posts", 0.5, 0.6, 0.4, 0.8, "1. Review old posts\n2. Archive controversial ones\n3. Update bio to reflect current views"),
        ("Pin strongest projects", 0.7, 0.15, 0.5, 0.95, "1. Identify top 3 projects\n2. Pin on GitHub profile\n3. Add README context"),
        ("Add personal website", 0.6, 0.7, 0.3, 1.0, "1. Choose domain\n2. Create landing page\n3. Link from all profiles"),
    ]
    for title, impact, effort, urgency, rev, steps in demo_repairs:
        conn.execute("INSERT INTO repairs(id,title,affected_audience,linked_claim_id,"
                     "linked_evidence_ids,impact,effort,urgency,reversibility,cost_cents,"
                     "exact_steps,expected_effect,risk_of_overcorrecting,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (str(uuid4()), title, "[\"all\"]", "", "[]",
                      impact, effort, urgency, rev, 0,
                      steps, "Improved signal coherence", "Minimal", "pending"))

    conn.commit()
    print("Seeded demo data")

# Report
for table in ['claims','contradictions','risks','repairs']:
    cnt = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()["c"]
    print(f"  {table}: {cnt} rows")
conn.close()
print("Done.")
