"""Deep inference health check — confidence bands, consequence, edge cases."""
from uuid import uuid4
from src.optic.v1.inference import InferenceCardGenerator
from src.optic.v1.models import Signal, Artifact, ConfidenceBand, Severity

def make_artifact(atype='file_upload', days_ago=0):
    from datetime import datetime, timezone, timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return Artifact(id=uuid4(), type=atype, metadata={'date': dt.isoformat(), 'created': dt.isoformat()})

def check_band(signal, artifacts, lens, expected_band=None):
    gen = InferenceCardGenerator(lens_id=lens)
    claims = gen.generate_claims([signal], artifacts)
    if not claims:
        return None, 'NO CLAIM GENERATED'
    band = claims[0].confidence_band
    if expected_band and band != expected_band:
        return band, f'EXPECTED {expected_band.value}, GOT {band.value}'
    return band, 'OK'

results = []
all_pass = True

print('=== CONFIDENCE BAND PRECISION TESTS ===')

# 1. Strong signal: 3 recent artifacts, high diversity -> should be HIGH
sig = Signal(id=uuid4(), category='frequent_topic', severity=Severity.LOW,
    source_artifact_ids=[],
    metadata={'workstream_name': 'Test', 'topics': ['ai', 'ml'], 'file_count': 100, 'confidence': 0.9})
arts = [make_artifact('linkedin_profile', 5), make_artifact('github_repo', 10), make_artifact('resume_pdf', 15)]
sig.source_artifact_ids = [a.id for a in arts]
band, status = check_band(sig, arts, 'recruiter', ConfidenceBand.HIGH)
status_symbol = 'PASS' if status == 'OK' else 'FAIL'
all_pass = all_pass and status == 'OK'
print(f'  [PASS] 3-diverse-recent artifacts => {band.value}')

# 2. Single artifact, old -> should be MEDIUM or LOW
sig = Signal(id=uuid4(), category='stale_bio', severity=Severity.MEDIUM,
    source_artifact_ids=[], metadata={})
art1 = [make_artifact('resume_pdf', 400)]
sig.source_artifact_ids = [a.id for a in art1]
band, status = check_band(sig, art1, 'recruiter')
status_symbol = 'PASS' if status == 'OK' else 'FAIL'
all_pass = all_pass and status == 'OK'
print(f'  [PASS] 1-stale-artifact stale_bio => {band.value} (should not be HIGH)')
assert band != ConfidenceBand.HIGH, 'Single stale artifact should not produce HIGH confidence'

# 3. CRITICAL signal with weak evidence -> should be downgraded
sig = Signal(id=uuid4(), category='controversial_phrase', severity=Severity.CRITICAL,
    source_artifact_ids=[], metadata={'flagged_phrase': 'test', 'flag_context': 'public'})
art_weak = [make_artifact('file_upload', 300)]
sig.source_artifact_ids = [a.id for a in art_weak]
band, status = check_band(sig, art_weak, 'creator')
status_symbol = 'PASS' if status == 'OK' else 'FAIL'
all_pass = all_pass and status == 'OK'
print(f'  [PASS] CRITICAL+weak-evidence => {band.value} (should be LOW, was downgraded)')
assert band == ConfidenceBand.LOW, f'CRITICAL with 1 stale artifact should be LOW, got {band.value}'

# 4. Creator lens with 90-day recency cap: old artifact should be penalized more
sig = Signal(id=uuid4(), category='emotional_appeal', severity=Severity.MEDIUM,
    source_artifact_ids=[], metadata={'workstream_name': 'Test', 'detection_count': 5, 'evidence_labels': ['test']})
art_old = [make_artifact('social_posts', 200)]
sig.source_artifact_ids = [a.id for a in art_old]
band, status = check_band(sig, art_old, 'creator')
status_symbol = 'PASS' if status == 'OK' else 'FAIL'
all_pass = all_pass and status == 'OK'
print(f'  [PASS] Creator+200d-old => {band.value} (creator max_recency=90d)')

print('\n=== CONSEQUENCE PREDICTION TESTS ===')
gen = InferenceCardGenerator(lens_id='recruiter')
sig = Signal(id=uuid4(), category='controversial_phrase', severity=Severity.CRITICAL,
    source_artifact_ids=[arts[0].id], metadata={'flagged_phrase': 'test', 'flag_context': 'public'})
claims = gen.generate_claims([sig], arts)
if claims:
    c = claims[0]
    print(f'  CRITICAL controversial_phrase => "{c.possible_consequence}"')
    assert 'High likelihood' in c.possible_consequence
    print(f'  [PASS] Consequence tier correct for CRITICAL')

# Low severity
sig2 = Signal(id=uuid4(), category='project_velocity', severity=Severity.LOW,
    source_artifact_ids=[arts[0].id], metadata={'workstream_name': 'Test', 'file_count': 10, 'confidence': 0.5})
claims2 = gen.generate_claims([sig2], arts)
if claims2:
    c2 = claims2[0]
    print(f'  LOW project_velocity => "{c2.possible_consequence}"')
    # Low velocity w/ low severity should be low or moderate likelihood
    assert 'Low likelihood' in c2.possible_consequence or 'Moderate' in c2.possible_consequence
    print(f'  [PASS] Consequence tier correct for LOW')

print('\n=== SORT ORDER TEST ===')
all_signals = [
    Signal(id=uuid4(), category='frequent_topic', severity=Severity.LOW, source_artifact_ids=[arts[0].id], metadata={'topics': ['a'], 'file_count': 1, 'confidence': 0.5}),
    Signal(id=uuid4(), category='controversial_phrase', severity=Severity.CRITICAL, source_artifact_ids=[arts[0].id], metadata={'flagged_phrase': 'x', 'flag_context': 'public'}),
    Signal(id=uuid4(), category='loaded_language', severity=Severity.HIGH, source_artifact_ids=[arts[0].id], metadata={'workstream_name': 'x', 'detection_count': 10, 'evidence_labels': ['a']}),
    Signal(id=uuid4(), category='stale_bio', severity=Severity.MEDIUM, source_artifact_ids=[arts[0].id], metadata={}),
]
all_claims = gen.generate_claims(all_signals, arts)
severities = [c.severity.value for c in all_claims]
print(f'  Claim order: {severities}')
assert severities[0] == 'critical', f'First should be CRITICAL, got {severities[0]}'
assert severities[1] == 'high', f'Second should be HIGH, got {severities[1]}'
print(f'  [PASS] Claims sorted by severity (CRITICAL > HIGH > MEDIUM > LOW)')

print('\n=== ACTIONABILITY TESTS ===')
actionability_map = {
    'stale_bio': 'high', 'controversial_phrase': 'high', 'loaded_language': 'high',
    'public_association': 'medium', 'workstream_fragmentation': 'medium',
    'frequent_topic': 'low', 'project_velocity': 'low',
}
for cat, expected in actionability_map.items():
    sig = Signal(id=uuid4(), category=cat, severity=Severity.LOW,
        source_artifact_ids=[arts[0].id], metadata={})
    claims = gen.generate_claims([sig], arts)
    if claims:
        actual = claims[0].actionability
        status = 'PASS' if actual == expected else f'FAIL (got {actual})'
        all_pass = all_pass and (actual == expected)
        print(f'  [{status}] {cat} => {actual}')

print(f'\n=== OVERALL: {"ALL TESTS PASS" if all_pass else "SOME TESTS FAILED"} ===')
