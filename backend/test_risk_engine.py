"""Quick validation test for risk engine."""
import sys
sys.path.insert(0, "/Users/ahmedm/Developer/Projects/optic/backend/src")

from optic.v1.risk import risk_engine
from optic.v1.models import RiskFlag, RiskCategory, Severity

# Quick unit test: empty input should return at least 3 risks (honest minimum)
result = risk_engine(contradictions=[], claims=[], artifacts=[], workstream_cards=[])
print(f"Empty input → {len(result)} risks")
for r in result:
    print(f"  [{r.category.value}] {r.severity.value}: {r.description[:100]}")

# Test with some contradictions
contra = [
    {"category": "stale_context", "description": "Test stale content", "severity": "medium",
     "claim_ids": [], "artifact_ids": ["abc123"], "audience_affected": ["recruiter"]},
    {"category": "claim_opposition", "description": "Conflicting claims detected", "severity": "high",
     "claim_ids": ["c1", "c2"], "artifact_ids": [], "audience_affected": ["recruiter"]},
    {"category": "timeline_gap", "description": "2-year gap found", "severity": "medium",
     "claim_ids": [], "artifact_ids": ["a1", "a2"], "audience_affected": ["investor"]},
    {"category": "job_title_mismatch", "description": "Different titles across platforms", "severity": "low",
     "claim_ids": ["c3"], "artifact_ids": [], "audience_affected": ["recruiter"]},
    {"category": "identity_fragmentation", "description": "Name appears as multiple types", "severity": "medium",
     "claim_ids": [], "artifact_ids": [], "audience_affected": ["all"]},
]

claims = [
    {"audience_lens": "recruiter", "confidence_band": "high", "claim": "Strong recruiter signal detected for hiring",
     "id": "c1"},
    {"audience_lens": "stranger", "confidence_band": "high", "claim": "Public profile strongly indicates expertise",
     "id": "c2"},
    {"audience_lens": "investor", "confidence_band": "low", "claim": "Weak funding signal",
     "id": "c3"},
]

result2 = risk_engine(contradictions=contra, claims=claims, artifacts=[], workstream_cards=[{"name": "Test"}])
print(f"\nWith contradictions + claims → {len(result2)} risks")
for r in result2:
    print(f"  [{r.category.value}] {r.severity.value}: {r.description[:120]}")

print(f"\nOK: Risk engine works. Dynamic generation: {len(result2)} risks from 5 contradictions + 3 claims")
assert len(result2) >= 5, f"Expected >=5 risks, got {len(result2)}"
print("PASS: >= 5 risks generated")
