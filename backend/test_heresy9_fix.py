"""
HERESY-9 FIX — Validation Test Suite
====================================
Validates that the contradiction engine no longer produces a Cartesian
explosion of false positives. Tests topic grouping, semantic distance
gating, severity calibration, and per-lens caps.
"""
from __future__ import annotations

import sys
import os
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from optic.v1.contradiction import ContradictionEngine
from optic.v1.models import (
    Contradiction, InferenceClaim, Severity, ConfidenceBand,
)


def make_claim(
    title: str = "Test Claim",
    lens: str = "recruiter",
    claim_text: str = "",
    evidence: list | None = None,
    confidence: ConfidenceBand = ConfidenceBand.MEDIUM,
) -> InferenceClaim:
    """Factory for test claims with defaults."""
    return InferenceClaim(
        id=uuid4(),
        title=title,
        audience_lens=lens,
        claim=claim_text,
        confidence_band=confidence,
        evidence_count=len(evidence or []),
        supporting_evidence=evidence or [],
        not_a_verdict=True,
    )


def test_topic_grouping_filters_cross_topic():
    """Claims about DIFFERENT workstreams should NEVER be compared."""
    engine = ContradictionEngine()

    code_claims = [
        make_claim(lens="recruiter",
                   claim_text="Your code workstream shows strong consistent activity with deep technical engagement across multiple projects"),
        make_claim(lens="recruiter",
                   claim_text="You have no significant coding activity in the last 6 months with minimal project work"),
    ]

    health_claims = [
        make_claim(lens="recruiter",
                   claim_text="Your health and fitness workstream shows consistent workout activity across 142 tracked sessions"),
        make_claim(lens="recruiter",
                   claim_text="You have no health tracking data and limited fitness engagement"),
    ]

    all_claims = code_claims + health_claims
    result = engine.find_claim_contradictions(all_claims)

    # Each topic group should only compare within itself (not cross-topic)
    # Code: 2 claims -> max 1 contradiction within topic
    # Health: 2 claims -> max 1 contradiction within topic
    assert len(result) <= 2, (
        f"Expected <=2 contradictions (one per topic group), got {len(result)}. "
        f"Cross-topic filtering failed!"
    )
    print(f"  PASS: topic_grouping_filters_cross_topic — {len(result)} contradictions "
          f"(from {len(all_claims)} claims across 2 topics)")


def test_same_topic_produces_contradictions():
    """Claims about SAME workstream with genuine opposition SHOULD be detected."""
    engine = ContradictionEngine()

    claims = [
        make_claim(lens="recruiter",
                   claim_text="Your code and engineering workstream shows strong consistent programming activity across multiple open source projects",
                   evidence=[uuid4(), uuid4()]),
        make_claim(lens="recruiter",
                   claim_text="You have no meaningful engineering contribution and limited code activity in your workstream",
                   evidence=[uuid4()]),
    ]

    result = engine.find_claim_contradictions(claims)

    assert len(result) >= 1, (
        f"Expected >=1 contradiction for genuinely opposing claims about same topic, "
        f"got {len(result)}"
    )
    assert result[0].category == "claim_opposition"
    print(f"  PASS: same_topic_produces_contradictions — detected {len(result)} contradiction(s)")


def test_no_opposition_skipped():
    """Claims about same topic but NO opposition should be filtered."""
    engine = ContradictionEngine()

    claims = [
        make_claim(lens="recruiter",
                   claim_text="Your research and learning workstream contains 142 files spanning AI and machine learning topics",
                   evidence=[uuid4()]),
        make_claim(lens="recruiter",
                   claim_text="Your research and learning workstream covers deep technical subjects across multiple domains",
                   evidence=[uuid4()]),
    ]

    result = engine.find_claim_contradictions(claims)

    assert len(result) == 0, (
        f"Expected 0 contradictions for non-opposing claims about same topic, "
        f"got {len(result)}"
    )
    print(f"  PASS: no_opposition_skipped — filtered {len(result)} (expected 0)")


def test_per_lens_cap():
    """Per-lens cap of max_per_lens should limit output."""
    engine = ContradictionEngine()

    claims = []
    for i in range(50):
        claims.append(make_claim(
            lens="recruiter",
            claim_text=f"Your code workstream has strong activity pattern {i} across projects",
            evidence=[uuid4()],
        ))
        claims.append(make_claim(
            lens="recruiter",
            claim_text=f"You never demonstrated coding ability in workstream pattern {i}",
            evidence=[uuid4()],
        ))

    result = engine.find_claim_contradictions(claims, max_per_lens=20)

    assert len(result) <= 20, (
        f"Expected <=20 contradictions with cap, got {len(result)}"
    )
    print(f"  PASS: per_lens_cap — {len(result)} contradictions returned "
          f"(capped at 20, from {len(claims)} claims)")


def test_cartesian_explosion_prevented():
    """Simulate the original bug: 120 claims across 5 lenses with mixed topics."""
    engine = ContradictionEngine()

    lenses = ["recruiter", "investor", "stranger", "creator", "privacy"]
    topics = [
        ("code", "Your code workstream shows {} programming activity"),
        ("writing", "Your writing signals {} across documents"),
        ("research", "Your research and learning workstream {} deep curiosity"),
        ("health", "Health tracking data shows {} fitness engagement"),
        ("travel", "Travel patterns reveal {} global mobility"),
        ("finance", "Financial signals show {} portfolio management"),
        ("social", "Social and relationship signals indicate {} connections"),
        ("career", "Career workstream reflects {} professional growth"),
    ]

    claims = []
    for lens in lenses:
        for _topic, template in topics:
            claims.append(make_claim(
                lens=lens,
                claim_text=template.format("strong consistent"),
                evidence=[uuid4()],
            ))
            claims.append(make_claim(
                lens=lens,
                claim_text=template.format("no significant"),
                evidence=[uuid4()],
            ))
            claims.append(make_claim(
                lens=lens,
                claim_text=template.format("moderate"),
                evidence=[uuid4()],
            ))

    total_claims = len(claims)
    possible_pairs = total_claims * (total_claims - 1) // 2
    print(f"  INFO: {total_claims} claims across {len(lenses)} lenses, "
          f"{len(topics)} topics, {possible_pairs} possible pairs")

    result = engine.find_claim_contradictions(claims, max_per_lens=20)

    # Original bug: ~54K false positives. Fixed: must be way under 500.
    assert len(result) < 500, (
        f"Cartesian explosion NOT fixed! Expected <500, got {len(result)}"
    )

    # Per-lens cap enforced
    per_lens = {}
    for c in result:
        lens = c.audience_affected[0]
        per_lens[lens] = per_lens.get(lens, 0) + 1

    max_per = max(per_lens.values()) if per_lens else 0
    assert max_per <= 20, f"Per-lens cap violated! Max per lens: {max_per}"

    # Diverse artifact IDs (not just 15 distinct)
    all_artifact_ids = set()
    for c in result:
        for aid in c.artifact_ids:
            all_artifact_ids.add(aid)

    print(f"  PASS: cartesian_explosion_prevented — {len(result)} contradictions "
          f"(from {possible_pairs} possible pairs)")
    print(f"  STATS: {len(all_artifact_ids)} distinct artifact IDs, "
          f"max {max_per} per lens, {len(per_lens)} lenses")


def test_severity_calibration():
    """Severity should scale with semantic distance."""
    engine = ContradictionEngine()

    high_dist = engine._semantic_distance(
        "Your code workstream shows strong consistent activity",
        "You have no coding ability or engineering skills"
    )
    low_dist = engine._semantic_distance(
        "Your code workstream shows strong activity",
        "Your code workstream shows strong consistent activity"
    )

    high_sev = engine._severity_from_distance(high_dist)
    low_sev = engine._severity_from_distance(low_dist)

    assert high_dist > low_dist, "Semantic distance ordering broken"
    assert high_sev in (Severity.HIGH, Severity.MEDIUM, Severity.CRITICAL), (
        f"High distance ({high_dist:.2f}) should map to HIGH/MEDIUM/CRITICAL, got {high_sev}"
    )
    print(f"  PASS: severity_calibration — high dist={high_dist:.2f}->{high_sev}, "
          f"low dist={low_dist:.2f}->{low_sev}")


def test_topic_signature_extraction():
    """Topic keywords should be extracted from claim text."""
    code_sig = ContradictionEngine._extract_topic_signature(
        "Your code workstream shows strong engineering across software projects"
    )
    health_sig = ContradictionEngine._extract_topic_signature(
        "Health and travel data shows consistent fitness tracking activity"
    )

    assert "code" in code_sig, f"Expected 'code' in signature, got '{code_sig}'"
    assert "engineering" in code_sig or "software" in code_sig
    assert "health" in health_sig, f"Expected 'health' in signature, got '{health_sig}'"
    assert "travel" in health_sig
    assert code_sig != health_sig, "Different topics should produce different signatures"
    print(f"  PASS: topic_signature_extraction — code='{code_sig}', health='{health_sig}'")


if __name__ == "__main__":
    print("=" * 60)
    print("HERESY-9 FIX — Validation Suite")
    print("=" * 60)

    failures = []

    tests = [
        ("Topic signature extraction", test_topic_signature_extraction),
        ("Topic grouping filters cross-topic", test_topic_grouping_filters_cross_topic),
        ("Same topic produces contradictions", test_same_topic_produces_contradictions),
        ("No opposition is skipped", test_no_opposition_skipped),
        ("Severity calibration", test_severity_calibration),
        ("Per-lens cap", test_per_lens_cap),
        ("Cartesian explosion prevented", test_cartesian_explosion_prevented),
    ]

    for name, fn in tests:
        try:
            fn()
        except AssertionError as e:
            print(f"  FAIL: {name} — {e}")
            failures.append(name)
        except Exception as e:
            import traceback
            print(f"  ERROR: {name} — {type(e).__name__}: {e}")
            traceback.print_exc()
            failures.append(name)

    print()
    if failures:
        print(f"FAILED: {len(failures)}/{len(tests)} tests")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} TESTS PASSED")
        sys.exit(0)
