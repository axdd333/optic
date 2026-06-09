"""Inference engine health check — integrity invariants."""
from uuid import uuid4
from datetime import datetime, timezone
from src.optic.v1.inference import InferenceCardGenerator
from src.optic.v1.models import Signal, Artifact, ConfidenceBand, Severity

artifacts = [
    Artifact(id=uuid4(), type='linkedin_profile', metadata={'date': '2026-05-01T00:00:00Z', 'created': '2026-05-01T00:00:00Z'}),
    Artifact(id=uuid4(), type='resume_pdf', metadata={'date': '2025-12-15T00:00:00Z'}),
    Artifact(id=uuid4(), type='github_repo', metadata={'date': '2026-01-10T00:00:00Z'}),
    Artifact(id=uuid4(), type='file_upload', metadata={'date': '2026-06-01T00:00:00Z'}),
    Artifact(id=uuid4(), type='project_doc', metadata={'date': '2026-05-20T00:00:00Z'}),
]
aid = [a.id for a in artifacts]

signals = [
    Signal(id=uuid4(), category='frequent_topic', description='Frequent topic cluster', severity=Severity.MEDIUM,
        source_artifact_ids=[aid[0], aid[1], aid[2]],
        metadata={'workstream_name': 'AI Research', 'topics': ['machine_learning', 'deep_learning', 'nlp'], 'file_count': 42, 'confidence': 0.85}),
    Signal(id=uuid4(), category='timeline_gap', description='Employment gap', severity=Severity.HIGH,
        source_artifact_ids=[aid[1], aid[4]],
        metadata={'gap_days': 540, 'gap_months': 18, 'domain': 'professional employment'}),
    Signal(id=uuid4(), category='stale_bio', description='Old bio', severity=Severity.MEDIUM,
        source_artifact_ids=[aid[1]], metadata={}),
    Signal(id=uuid4(), category='loaded_language', description='Emotionally charged', severity=Severity.LOW,
        source_artifact_ids=[aid[0]],
        metadata={'workstream_name': 'Personal Writing', 'detection_count': 3, 'evidence_labels': ['extremely critical', 'total disaster', 'absolutely vital']}),
    Signal(id=uuid4(), category='project_velocity', description='High output', severity=Severity.LOW,
        source_artifact_ids=[aid[2], aid[3], aid[4]],
        metadata={'workstream_name': 'Optic Build', 'file_count': 127, 'confidence': 0.92}),
    Signal(id=uuid4(), category='unknown_category', description='Unmodeled signal', severity=Severity.MEDIUM,
        source_artifact_ids=[aid[0]], metadata={}),
]

errors = []
warnings = []
lens_ids = ['recruiter', 'investor', 'creator', 'stranger', 'privacy']

for lens_id in lens_ids:
    try:
        gen = InferenceCardGenerator(lens_id=lens_id)
        claims = gen.generate_claims(signals, artifacts)

        for claim in claims:
            # INVARIANT 3: Evidence-gated
            if claim.evidence_count == 0:
                errors.append(f'{lens_id}: ZERO evidence count for "{claim.title}"')
            if not claim.supporting_evidence:
                errors.append(f'{lens_id}: NO supporting evidence for "{claim.title}"')

            # INVARIANT 4: Confidence-banded
            if claim.confidence_band not in (ConfidenceBand.HIGH, ConfidenceBand.MEDIUM, ConfidenceBand.LOW):
                errors.append(f'{lens_id}: Invalid confidence band {claim.confidence_band} for "{claim.title}"')

            # ACCEPTANCE RULE
            if not claim.not_a_verdict:
                errors.append(f'CRITICAL: ACCEPTANCE RULE VIOLATED! not_a_verdict=False for "{claim.title}"')

            # Counterargument
            if not claim.counterargument:
                warnings.append(f'{lens_id}: Missing counterargument for "{claim.title}"')

            # Recency
            if not claim.recency:
                warnings.append(f'{lens_id}: Missing recency for "{claim.title}"')

    except Exception as e:
        errors.append(f'EXCEPTION for lens {lens_id}: {e}')

print('=== INFERENCE ENGINE INTEGRITY CHECK ===')
if errors:
    print(f'ERRORS FOUND ({len(errors)}):')
    for err in errors:
        print(f'  [FAIL] {err}')
else:
    print('[PASS] All integrity invariants pass')

if warnings:
    print(f'WARNINGS ({len(warnings)}):')
    for w in warnings:
        print(f'  [WARN] {w}')
else:
    print('[PASS] No warnings')

# Unknown category fallback
gen = InferenceCardGenerator(lens_id='recruiter')
unknown_claims = gen.generate_claims([s for s in signals if s.category == 'unknown_category'], artifacts)
print(f'\nUnknown category fallback: {len(unknown_claims)} claims generated')
for c in unknown_claims:
    print(f'  Model version: {c.model_version}')
    print(f'  Evidence count: {c.evidence_count}')
    print(f'  Confidence: {c.confidence_band.value}')
    print(f'  Has counterargument: {bool(c.counterargument)}')
    print(f'  not_a_verdict: {c.not_a_verdict}')

# Test evidence count gate
low_ev_signal = Signal(id=uuid4(), category='frequent_topic', severity=Severity.LOW,
    source_artifact_ids=[],  # ZERO artifacts
    metadata={'workstream_name': 'Empty', 'topics': ['test']})
claims_zero = gen.generate_claims([low_ev_signal], artifacts)
print(f'\nZero-evidence signal: {len(claims_zero)} claims (should be 0)')
assert len(claims_zero) == 0, f'Expected 0 claims for zero-evidence signal, got {len(claims_zero)}'
print('[PASS] Zero-evidence signals are correctly gated')
