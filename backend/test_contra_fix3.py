"""Test contradiction engine — with dict conversion like server does."""
import sys, traceback
sys.path.insert(0, '/Users/ahmedm/Developer/Projects/optic/backend/src')

import json, sqlite3
from uuid import UUID, uuid4
from optic.v1.models import (
    Artifact, Entity, InferenceClaim, Severity, ConfidenceBand
)
from optic.v1.contradiction import ContradictionEngine

DB = '/Users/ahmedm/Developer/Projects/optic/backend/.optic/v1.db'


def _row_to_dict(row):
    """Convert sqlite3.Row to dict (like server's _v1_row_to_dict)."""
    return {k: row[k] for k in row.keys()}


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # Load claims (using dicts like server does)
    claim_rows = conn.execute("SELECT * FROM claims").fetchall()
    claim_dicts = [_row_to_dict(r) for r in claim_rows]
    claims = []
    claims_ok = 0
    claims_fail = 0
    for cd in claim_dicts:
        try:
            se = cd.get("supporting_evidence", [])
            if isinstance(se, str):
                try: se = json.loads(se)
                except Exception: se = []
            we = cd.get("weakening_evidence", [])
            if isinstance(we, str):
                try: we = json.loads(we)
                except Exception: we = []
            claims.append(InferenceClaim(
                id=UUID(cd["id"]) if cd.get("id") else uuid4(),
                title=cd.get("title", ""),
                audience_lens=cd.get("audience_lens", ""),
                claim=cd.get("claim", ""),
                confidence_band=ConfidenceBand(cd.get("confidence_band", "low")),
                evidence_count=int(cd.get("evidence_count") or 0),
                supporting_evidence=([UUID(x) for x in se if x] if isinstance(se, list) else []),
                weakening_evidence=([UUID(x) for x in we if x] if isinstance(we, list) else []),
                source_gaps=[],
                recency=cd.get("recency", ""),
                severity=Severity(cd.get("severity", "low")),
                counterargument=cd.get("counterargument", ""),
                not_a_verdict=bool(cd.get("not_a_verdict", True)),
            ))
            claims_ok += 1
        except Exception as e:
            claims_fail += 1
            if claims_fail <= 2:
                print(f"Claim fail: id={cd.get('id','')[:20]} error={e}")

    print(f"Claims: {claims_ok} loaded, {claims_fail} failed (from {len(claim_dicts)} rows)")

    # Load artifacts (using dicts)
    art_rows = conn.execute("SELECT * FROM artifacts LIMIT 50").fetchall()
    art_dicts = [_row_to_dict(r) for r in art_rows]
    artifacts = []
    for ad in art_dicts:
        try:
            meta = {}
            try:
                meta = json.loads(ad.get("metadata", "{}") or "{}")
            except Exception:
                pass
            artifacts.append(Artifact(
                id=UUID(ad["id"]) if ad.get("id") else uuid4(),
                source_id=UUID(ad["source_id"]) if ad.get("source_id") else uuid4(),
                type=ad.get("type", ""),
                raw_hash=ad.get("raw_hash", ""),
                encrypted_path=ad.get("encrypted_path", ""),
                metadata=meta,
                is_public=bool(ad.get("is_public", False)),
                content_preview=ad.get("content_preview", ""),
                created_at=ad.get("created_at", ""),
            ))
        except Exception as e:
            print(f"Artifact fail: id={ad.get('id','')[:20]} error={e}")

    print(f"Artifacts: {len(artifacts)}")

    # Build entities with diverse types (simulating server fix)
    entities = []
    workstream_names = [
        ("Research & Learning", ["research", "learning", "code", "writing"]),
        ("Career & Work", ["career", "work", "resume", "job"]),
        ("Code Projects", ["code", "project", "software", "engineering"]),
        ("Writing & Communication", ["writing", "communication", "design"]),
    ]
    for name, topics in workstream_names:
        tl = [t.lower() for t in topics]

        entities.append(Entity(id=uuid4(), type="workstream", name=name, metadata={"topics": topics}))

        if {"career", "work", "job", "resume"} & set(tl):
            entities.append(Entity(id=uuid4(), type="employer", name=name, metadata={}))
        if {"code", "project", "software", "engineering"} & set(tl):
            entities.append(Entity(id=uuid4(), type="project", name=name, metadata={}))
        if {"research", "learning", "design", "writing", "communication"} & set(tl):
            entities.append(Entity(id=uuid4(), type="skill", name=name, metadata={}))

    engine = ContradictionEngine()

    print(f"Entities: {len(entities)} types={set(e.type for e in entities)}")

    # Run each method
    r1 = engine.find_job_title_mismatches(claims, entities)
    print(f"\njob_title_mismatch: {len(r1)}")

    r2 = engine.find_timeline_conflicts(artifacts, claims)
    print(f"timeline_gap: {len(r2)}")

    r3 = engine.find_stale_context(artifacts)
    print(f"stale_context: {len(r3)}")

    r4 = engine.find_profile_mismatches(entities)
    print(f"identity_fragmentation: {len(r4)}")
    for c in r4:
        print(f"  - {c.description} [{c.severity.value}]")

    r5 = engine.find_claim_contradictions(claims)
    print(f"claim_opposition: {len(r5)}")

    all_contra = engine.run_full_audit(claims, artifacts, entities)
    cats = {}
    for c in all_contra:
        cats[c.category] = cats.get(c.category, 0) + 1
    print(f"\n=== Full Audit: {len(all_contra)} total ===")
    for cat, cnt in sorted(cats.items()):
        print(f"  {cat}: {cnt}")

    conn.close()

if __name__ == "__main__":
    main()
