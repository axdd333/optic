"""
Optic-brain: Full inference engine audit.
PART A — Evidence-gating: every claim must cite actual data (not templates)
PART B — Confidence band: verify multi-factor computation
PART C — Structural: DEDUCTION_MAP coverage, missing categories
PART D — Claim text quality check
PART E — ACCEPTANCE RULE verification
"""

import json, sys
from uuid import uuid4
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "src")
from optic.v1.inference import (
    InferenceCardGenerator, DEDUCTION_MAP, CATEGORY_RISK_WEIGHT,
    _source_type_diversity, _recency_penalty
)
from optic.v1.models import Signal, Artifact, ConfidenceBand, Severity

# Create artifacts with real IDs
artifacts = [
    Artifact(id=uuid4(), type="linkedin_profile",
             metadata={"date": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                       "created": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()}),
    Artifact(id=uuid4(), type="resume_pdf",
             metadata={"date": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()}),
    Artifact(id=uuid4(), type="github_repo",
             metadata={"date": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()}),
    Artifact(id=uuid4(), type="social_posts",
             metadata={"date": (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()}),
    Artifact(id=uuid4(), type="file_upload",
             metadata={"date": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()}),
]
aid = [a.id for a in artifacts]

# Signal builders for each category
signal_defs = {
    "frequent_topic": Signal(
        id=uuid4(), category="frequent_topic", severity=Severity.MEDIUM,
        source_artifact_ids=[aid[0], aid[1], aid[2]],
        metadata={"workstream_name": "AI Research", "topics": ["machine_learning", "deep_learning", "nlp"],
                  "file_count": 42, "confidence": 0.85, "source_types": ["linkedin_profile", "resume_pdf", "github_repo"]}
    ),
    "project_velocity": Signal(
        id=uuid4(), category="project_velocity", severity=Severity.LOW,
        source_artifact_ids=[aid[2], aid[3], aid[4]],
        metadata={"workstream_name": "Optic Build", "file_count": 127, "confidence": 0.92,
                  "source_types": ["github_repo", "social_posts", "file_upload"]}
    ),
    "workstream_fragmentation": Signal(
        id=uuid4(), category="workstream_fragmentation", severity=Severity.MEDIUM,
        source_artifact_ids=[aid[0], aid[1]],
        metadata={"workstream_name": "Misc Projects", "file_count": 25, "confidence": 0.3}
    ),
    "ai_ml_content": Signal(
        id=uuid4(), category="ai_ml_content", severity=Severity.MEDIUM,
        source_artifact_ids=[aid[0], aid[2]],
        metadata={"workstream_name": "ML Work", "detection_count": 14, "file_count": 20,
                  "evidence_labels": ["transformer architecture", "gradient descent", "fine-tuning pipeline"]}
    ),
    "software_engineering": Signal(
        id=uuid4(), category="software_engineering", severity=Severity.LOW,
        source_artifact_ids=[aid[2], aid[4]],
        metadata={"workstream_name": "Dev Work", "detection_count": 47, "file_count": 80,
                  "evidence_labels": ["Python CI/CD", "React components", "Docker compose"]}
    ),
    "research_signals": Signal(
        id=uuid4(), category="research_signals", severity=Severity.MEDIUM,
        source_artifact_ids=[aid[0], aid[1]],
        metadata={"workstream_name": "Research", "detection_count": 22, "file_count": 35,
                  "evidence_labels": ["literature review", "experiment design", "statistical analysis"]}
    ),
    "loaded_language": Signal(
        id=uuid4(), category="loaded_language", severity=Severity.HIGH,
        source_artifact_ids=[aid[0]],
        metadata={"workstream_name": "Personal Writing", "detection_count": 5,
                  "evidence_labels": ["extremely critical", "total disaster", "absolutely vital"]}
    ),
    "emotional_appeal": Signal(
        id=uuid4(), category="emotional_appeal", severity=Severity.LOW,
        source_artifact_ids=[aid[3]],
        metadata={"workstream_name": "Social Content", "detection_count": 3,
                  "evidence_labels": ["you won't believe this", "heartbreaking story", "urgent call"]}
    ),
    "content_anomaly": Signal(
        id=uuid4(), category="content_anomaly", severity=Severity.LOW,
        source_artifact_ids=[aid[0], aid[4]],
        metadata={"workstream_name": "Docs", "detection_count": 7,
                  "evidence_labels": ["inconsistent formatting", "mixed tenses"]}
    ),
    "timeline_gap": Signal(
        id=uuid4(), category="timeline_gap", severity=Severity.HIGH,
        source_artifact_ids=[aid[1], aid[3]],
        metadata={"gap_days": 540, "gap_months": 18, "domain": "professional employment",
                  "source_types": ["resume_pdf", "social_posts"]}
    ),
    "stale_bio": Signal(
        id=uuid4(), category="stale_bio", severity=Severity.MEDIUM,
        source_artifact_ids=[aid[0]],
        metadata={"source_types": ["linkedin_profile"]}
    ),
    "inconsistent_title": Signal(
        id=uuid4(), category="inconsistent_title", severity=Severity.MEDIUM,
        source_artifact_ids=[aid[0], aid[1], aid[2]],
        metadata={"titles": ["Senior Engineer", "Lead Developer", "Principal"],
                  "source_count": 3, "source_types": ["linkedin_profile", "resume_pdf", "github_repo"]}
    ),
    "public_association": Signal(
        id=uuid4(), category="public_association", severity=Severity.HIGH,
        source_artifact_ids=[aid[0], aid[3], aid[4]],
        metadata={"entity_name": "OpenAI", "association_count": 5,
                  "association_context": "public references",
                  "source_types": ["linkedin_profile", "social_posts", "file_upload"]}
    ),
    "controversial_phrase": Signal(
        id=uuid4(), category="controversial_phrase", severity=Severity.CRITICAL,
        source_artifact_ids=[aid[3]],
        metadata={"flagged_phrase": "burn it all down", "flag_context": "public content",
                  "source_types": ["social_posts"]}
    ),
    "unclear_credential": Signal(
        id=uuid4(), category="unclear_credential", severity=Severity.MEDIUM,
        source_artifact_ids=[aid[1]],
        metadata={"credential_type": "PhD", "credential_source": "your profile",
                  "ambiguity_detail": "lacks issuing institution and year",
                  "source_types": ["resume_pdf"]}
    ),
}

lenses_tested = ["recruiter", "investor", "creator", "stranger", "privacy", "institution", "search", "collaborator"]

# PART A: Evidence-Gating Audit
print("=" * 70)
print("PART A: EVIDENCE-GATING AUDIT — every claim must cite real data")
print("=" * 70)

issues_a = []
for lens_id in lenses_tested:
    gen = InferenceCardGenerator(lens_id=lens_id)
    all_sigs = list(signal_defs.values())
    claims = gen.generate_claims(all_sigs, artifacts)
    
    for claim in claims:
        if len(claim.supporting_evidence) == 0:
            issues_a.append(f"{lens_id}/{claim.title}: ZERO supporting evidence")
        if claim.evidence_count != len(claim.supporting_evidence):
            issues_a.append(f"{lens_id}/{claim.title}: evidence_count mismatch")
        if not claim.not_a_verdict:
            issues_a.append(f"{lens_id}/{claim.title}: ACCEPTANCE RULE VIOLATION")
        if not claim.counterargument:
            issues_a.append(f"{lens_id}/{claim.title}: MISSING counterargument")
        if not claim.recency or claim.recency == "unknown":
            issues_a.append(f"{lens_id}/{claim.title}: Missing/unknown recency")

if issues_a:
    for i in issues_a:
        print(f"  [ISSUE] {i}")
else:
    print("  [PASS] All evidence-gating invariants hold across all lenses")

# PART B: Confidence Band Analysis
print("\n" + "=" * 70)
print("PART B: CONFIDENCE BAND ANALYSIS (recruiter, investor, creator)")
print("=" * 70)

for cat, sig in signal_defs.items():
    bands = {}
    for lens_id in lenses_tested[:3]:
        gen = InferenceCardGenerator(lens_id=lens_id)
        claims = gen.generate_claims([sig], artifacts)
        if claims:
            bands[lens_id] = claims[0].confidence_band.value
    print(f"  {cat:25s} => {bands}")

# PART C: DEDUCTION_MAP coverage
print("\n" + "=" * 70)
print("PART C: DEDUCTION_MAP COVERAGE")
print("=" * 70)

all_categories_in_map = set(DEDUCTION_MAP.keys())
all_categories_used = set(signal_defs.keys())
missing = all_categories_used - all_categories_in_map
extra = all_categories_in_map - all_categories_used

print(f"  Categories in DEDUCTION_MAP: {len(DEDUCTION_MAP)}")
print(f"  Categories with test signals: {len(all_categories_used)}")
if missing:
    print(f"  [GAP] Categories used but NOT in DEDUCTION_MAP: {missing}")
else:
    print(f"  [PASS] All used categories are in DEDUCTION_MAP")
if extra:
    print(f"  [INFO] {len(extra)} DEDUCTION_MAP categories not covered here (harmless extras)")

# PART D: Claim text quality check (sample)
print("\n" + "=" * 70)
print("PART D: CLAIM TEXT QUALITY CHECK (recruiter lens, sample)")
print("=" * 70)

gen = InferenceCardGenerator(lens_id="recruiter")
claims = gen.generate_claims(list(signal_defs.values()), artifacts)
for claim in claims[:5]:
    print(f"\n  [{claim.confidence_band.value}] {claim.title}")
    print(f"  {claim.claim[:200]}...")
    print(f"  Evidence: {claim.evidence_count} supporting | recency: {claim.recency}")
    print(f"  Counter: {claim.counterargument[:150]}...")

# PART E: ACCEPTANCE RULE verification
print("\n" + "=" * 70)
print("PART E: ACCEPTANCE RULE VERIFICATION")
print("=" * 70)

gen = InferenceCardGenerator(lens_id="recruiter")
all_claims = gen.generate_claims(list(signal_defs.values()), artifacts)
violations = [c for c in all_claims if not c.not_a_verdict]

# Also check across ALL lenses
total_claims = 0
for lens_id in lenses_tested:
    gen = InferenceCardGenerator(lens_id=lens_id)
    claims = gen.generate_claims(list(signal_defs.values()), artifacts)
    total_claims += len(claims)
    for c in claims:
        if not c.not_a_verdict:
            violations.append(c)

if not violations:
    print(f"  [PASS] not_a_verdict=True on ALL {total_claims} claims across {len(lenses_tested)} lenses")
    print("  ACCEPTANCE RULE IS ABSOLUTE.")
else:
    print(f"  [FAIL] {len(violations)} ACCEPTANCE RULE VIOLATIONS across {len(lenses_tested)} lenses")

# PART F: Counterargument quality
print("\n" + "=" * 70)
print("PART F: COUNTERARGUMENT PRESENCE")
print("=" * 70)

missing_cc = 0
empty_cc = 0
for lens_id in lenses_tested:
    gen = InferenceCardGenerator(lens_id=lens_id)
    claims = gen.generate_claims(list(signal_defs.values()), artifacts)
    for c in claims:
        if not c.counterargument:
            missing_cc += 1
        elif len(c.counterargument.strip()) < 20:
            empty_cc += 1

if missing_cc == 0 and empty_cc == 0:
    print(f"  [PASS] All claims have substantive counterarguments")
else:
    print(f"  [WARN] {missing_cc} missing, {empty_cc} with minimal counterarguments")

print(f"\n=== AUDIT COMPLETE — {total_claims} total claims across {len(lenses_tested)} lenses ===")
