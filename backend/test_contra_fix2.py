"""Test the contradiction engine against real DB data — with error reporting."""
import sys, traceback
sys.path.insert(0, '/Users/ahmedm/Developer/Projects/optic/backend/src')

import json, sqlite3
from uuid import UUID, uuid4
from optic.v1.models import (
    Artifact, Entity, InferenceClaim, Severity, ConfidenceBand
)
from optic.v1.contradiction import ContradictionEngine

DB = '/Users/ahmedm/Developer/Projects/optic/backend/.optic/v1.db'

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    # Load claims
    claim_rows = conn.execute("SELECT * FROM claims").fetchall()
    claims = []
    claims_ok = 0
    claims_fail = 0
    for cd in claim_rows:
        try:
            se = cd["supporting_evidence"]
            if isinstance(se, str):
                try: se = json.loads(se)
                except Exception: se = []
            we = cd["weakening_evidence"]
            if isinstance(we, str):
                try: we = json.loads(we)
                except Exception: we = []
            claims.append(InferenceClaim(
                id=UUID(cd["id"]),
                title=cd["title"] or "",
                audience_lens=cd["audience_lens"] or "",
                claim=cd["claim"] or "",
                confidence_band=ConfidenceBand(cd["confidence_band"] or "low"),
                evidence_count=int(cd["evidence_count"] or 0),
                supporting_evidence=([UUID(x) for x in se if x] if isinstance(se, list) else []),
                weakening_evidence=([UUID(x) for x in we if x] if isinstance(we, list) else []),
                source_gaps=[],
                recency=cd["recency"] or "",
                severity=Severity(cd["severity"] or "low"),
                counterargument=cd.get("counterargument", ""),
            ))
            claims_ok += 1
        except Exception as e:
            claims_fail += 1
            if claims_fail == 1:
                print(f"First claim fail: id={cd['id'][:20]} error={e}")
                traceback.print_exc()
    print(f"Claims loaded: {claims_ok}/{len(claim_rows)} (failed: {claims_fail})")

    # Load artifacts
    art_rows = conn.execute("SELECT * FROM artifacts LIMIT 50").fetchall()
    artifacts = []
    for ad in art_rows:
        try:
            meta = {}
            try:
                meta = json.loads(ad["metadata"] or "{}")
            except Exception:
                pass
            artifacts.append(Artifact(
                id=UUID(ad["id"]),
                source_id=UUID(ad["source_id"]),
                type=ad["type"] or "",
                raw_hash=ad["raw_hash"] or "",
                encrypted_path=ad.get("encrypted_path", ""),
                metadata=meta,
                is_public=bool(ad["is_public"]),
                content_preview=ad["content_preview"] or "",
                created_at=ad["created_at"] or "",
            ))
        except Exception as e:
            print(f"Artifact fail: {e}")

    print(f"Artifacts: {len(artifacts)}, Claims: {len(claims)}")

    # Build diverse entities
    entities = []
    workstream_names = [
        ("Research & Learning", ["research", "learning", "code", "writing"]),
        ("Career & Work", ["career", "work", "resume", "job"]),
        ("Code Projects", ["code", "project", "software", "engineering"]),
        ("Writing & Communication", ["writing", "communication", "design"]),
    ]
    for name, topics in workstream_names:
        topics_lower = [t.lower() for t in topics]

        entities.append(Entity(
            id=uuid4(), type="workstream", name=name,
            metadata={"topics": topics, "confidence": 0.8}
        ))

        job_kw = {"career", "work", "job", "resume", "cv", "employment"}
        org_kw = {"company", "organization", "startup", "business", "employer"}
        proj_kw = {"code", "project", "software", "app", "development", "engineering"}
        skill_kw = {"skill", "learning", "research", "design", "writing", "communication"}

        if job_kw & set(topics_lower):
            entities.append(Entity(id=uuid4(), type="employer", name=name, metadata={}))
        if org_kw & set(topics_lower):
            entities.append(Entity(id=uuid4(), type="org", name=name, metadata={}))
        if proj_kw & set(topics_lower):
            entities.append(Entity(id=uuid4(), type="project", name=name, metadata={}))
        if skill_kw & set(topics_lower):
            entities.append(Entity(id=uuid4(), type="skill", name=name, metadata={}))

    engine = ContradictionEngine()

    print(f"Entity types: {set(e.type for e in entities)}")
    print(f"Entity names: {[e.name + ':' + e.type for e in entities]}")

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
    print(f"\n--- Full Audit ---")
    print(f"Total: {len(all_contra)}")
    for cat, cnt in sorted(cats.items()):
        print(f"  {cat}: {cnt}")

    conn.close()

if __name__ == "__main__":
    main()
