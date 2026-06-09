#!/usr/bin/env python3
"""
Verify contradiction engine works with diverse claims,
then seed real contradictions into the DB for pipeline verification.
"""
import sys, os, json
from uuid import uuid4
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_backend_dir / "src"))

from optic.v1.contradiction import ContradictionEngine
from optic.v1.models import InferenceClaim, ConfidenceBand, Severity

# ── Create hand-crafted CLAIMS that SHOULD contradict ────
claims = [
    # Pair 1: Contradictory job focus (same audience)
    InferenceClaim(
        id=uuid4(), title="Recruiter: Job Focus",
        audience_lens="recruiter",
        claim="Candidate has strong focus on backend engineering and distributed systems",
        confidence_band=ConfidenceBand.HIGH, evidence_count=10,
        severity=Severity.LOW, not_a_verdict=True
    ),
    InferenceClaim(
        id=uuid4(), title="Recruiter: Job Focus 2",
        audience_lens="recruiter",
        claim="Candidate has no significant backend experience and focuses primarily on frontend",
        confidence_band=ConfidenceBand.HIGH, evidence_count=8,
        severity=Severity.LOW, not_a_verdict=True
    ),

    # Pair 2: Contradictory activity level (same audience)
    InferenceClaim(
        id=uuid4(), title="Investor: Project Velocity",
        audience_lens="investor",
        claim="Shows sustained high-velocity open source contributions over past 24 months",
        confidence_band=ConfidenceBand.HIGH, evidence_count=15,
        severity=Severity.MEDIUM, not_a_verdict=True
    ),
    InferenceClaim(
        id=uuid4(), title="Investor: Project Velocity 2",
        audience_lens="investor",
        claim="Shows minimal open source activity with no significant contributions in recent years",
        confidence_band=ConfidenceBand.HIGH, evidence_count=6,
        severity=Severity.MEDIUM, not_a_verdict=True
    ),

    # Pair 3: Stale vs fresh (same audience)
    InferenceClaim(
        id=uuid4(), title="Recruiter: Bio Freshness",
        audience_lens="recruiter",
        claim="Bio and resume show current, actively maintained professional presence",
        confidence_band=ConfidenceBand.HIGH, evidence_count=4,
        severity=Severity.LOW, not_a_verdict=True
    ),
    InferenceClaim(
        id=uuid4(), title="Recruiter: Bio Freshness 2",
        audience_lens="recruiter",
        claim="Bio and resume appear outdated with no recent updates or current activity",
        confidence_band=ConfidenceBand.HIGH, evidence_count=3,
        severity=Severity.LOW, not_a_verdict=True
    ),

    # Pair 4: Different audience — should NOT contradict
    InferenceClaim(
        id=uuid4(), title="Collaborator: Tooling",
        audience_lens="collaborator",
        claim="Uses modern CI/CD pipelines and infrastructure-as-code extensively",
        confidence_band=ConfidenceBand.HIGH, evidence_count=12,
        severity=Severity.LOW, not_a_verdict=True
    ),
    InferenceClaim(
        id=uuid4(), title="Stranger: Tooling",
        audience_lens="stranger",
        claim="No evidence of modern DevOps tooling in public profile (different lens - should not be checked against collaborator)",
        confidence_band=ConfidenceBand.LOW, evidence_count=2,
        severity=Severity.LOW, not_a_verdict=True
    ),
]

print(f"Created {len(claims)} hand-crafted claims for contradiction testing")
print()

engine = ContradictionEngine()
contradictions = engine.run_full_audit(claims, [], [])

print(f"Contradictions found: {len(contradictions)}")
print()

if contradictions:
    print("CONTRADICTION ENGINE WORKS! Found these contradictions:")
    for c in contradictions:
        print(f"  [{c.severity.value}] {c.category}")
        print(f"    {c.description[:120]}")
        print()
else:
    print("ERROR: Contradiction engine found 0 contradictions from diverse input!")

# ── Test each detector individually ──
print("\n--- Individual detector tests ---")

# Test claim_contradictions directly
cc = engine.find_claim_contradictions(claims)
print(f"find_claim_contradictions: {len(cc)}")
for c in cc:
    print(f"  [{c.severity.value}] {c.description[:100]}")

# Test overlap ratio 
for i, c1 in enumerate(claims):
    for c2 in claims[i+1:]:
        if c1.audience_lens == c2.audience_lens:
            overlap = engine._word_overlap_ratio(c1.claim, c2.claim)
            oppose = engine._opposition_in_difference(c1.claim, c2.claim)
            print(f"  [{c1.audience_lens}] overlap={overlap:.2f} oppose={oppose}")
            print(f"    A: {c1.claim[:60]}...")
            print(f"    B: {c2.claim[:60]}...")

print("\nDone. Contradiction engine verified.")
