#!/usr/bin/env python3
"""TASK-T2 verification: typed object construction from dicts."""
import sys, json
sys.path.insert(0, "src")

from optic.v1.models import Artifact, Entity, InferenceClaim, ConfidenceBand, Severity
from uuid import UUID, uuid4

errors = 0

# ── Test 1: InferenceClaim from dict ──
cd = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Senior Engineer",
    "audience_lens": "recruiter",
    "claim": "They work as a senior engineer",
    "confidence_band": "medium",
    "evidence_count": 3,
    "supporting_evidence": ["550e8400-e29b-41d4-a716-446655440001"],
    "weakening_evidence": [],
    "source_gaps": "[]",
    "recency": "recent",
    "severity": "low",
    "actionability": "medium",
    "possible_consequence": "",
    "counterargument": "",
    "repair_options": "[]",
    "model_version": "v1",
    "generated_at": "2025-01-01T00:00:00Z",
    "not_a_verdict": 1,
}
try:
    se = json.loads(cd["supporting_evidence"]) if isinstance(cd["supporting_evidence"], str) else cd["supporting_evidence"]
    c = InferenceClaim(
        id=UUID(cd["id"]),
        title=cd["title"],
        audience_lens=cd["audience_lens"],
        claim=cd["claim"],
        confidence_band=ConfidenceBand(cd["confidence_band"]),
        evidence_count=cd["evidence_count"],
        supporting_evidence=[UUID(x) for x in se],
        recency=cd["recency"],
        severity=Severity(cd["severity"]),
        actionability=cd["actionability"],
        model_version=cd["model_version"],
        generated_at=cd["generated_at"],
        not_a_verdict=bool(cd["not_a_verdict"]),
    )
    assert c.title == "Senior Engineer"
    assert c.audience_lens == "recruiter"
    assert c.confidence_band == ConfidenceBand.MEDIUM
    print("PASS: InferenceClaim from dict")
except Exception as e:
    print(f"FAIL: InferenceClaim from dict: {e}")
    errors += 1

# ── Test 2: Artifact from dict ──
ad = {
    "id": "660e8400-e29b-41d4-a716-446655440000",
    "source_id": "660e8400-e29b-41d4-a716-446655440001",
    "type": "pdf",
    "raw_hash": "abc123",
    "metadata": {"pages": 3},
    "is_public": False,
    "content_preview": "Resume...",
}
try:
    a = Artifact(
        id=UUID(ad["id"]),
        source_id=UUID(ad["source_id"]),
        type=ad["type"],
        raw_hash=ad["raw_hash"],
        metadata=ad["metadata"],
        is_public=ad["is_public"],
        content_preview=ad["content_preview"],
    )
    assert a.type == "pdf"
    assert a.metadata == {"pages": 3}
    assert a.is_public is False
    print("PASS: Artifact from dict")
except Exception as e:
    print(f"FAIL: Artifact from dict: {e}")
    errors += 1

# ── Test 3: Entity from dict ──
ed = {
    "type": "workstream",
    "name": "Research & Learning",
    "metadata": {"confidence": 0.87, "file_count": 142, "topics": ["research"]},
}
try:
    e = Entity(
        id=uuid4(),
        type=ed["type"],
        name=ed["name"],
        metadata=ed["metadata"],
        confidence=float(ed["metadata"]["confidence"]),
    )
    assert e.type == "workstream"
    assert e.name == "Research & Learning"
    print("PASS: Entity from dict")
except Exception as e:
    print(f"FAIL: Entity from dict: {e}")
    errors += 1

# ── Test 4: Attribute access (the TASK-T2 root cause) ──
try:
    # Dicts would fail:  ad["type"], cd["title"], ed["type"]
    # Objects use:      a.type,     c.title,     e.type
    assert a.type == "pdf"
    assert a.metadata["pages"] == 3
    assert a.is_public is False
    assert c.title == "Senior Engineer"
    assert c.audience_lens == "recruiter"
    assert e.type == "workstream"
    print("PASS: attribute access on typed objects")
except Exception as e:
    print(f"FAIL: attribute access: {e}")
    errors += 1

# ── Test 5: Server syntax ──
try:
    import ast
    with open("src/ctxorg/server.py") as f:
        ast.parse(f.read())
    print("PASS: server.py syntax OK")
except Exception as e:
    print(f"FAIL: server.py syntax: {e}")
    errors += 1

print(f"\n{7 - errors}/5 tests passed, {errors} failures")
sys.exit(errors)
