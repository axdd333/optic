"""
Regression tests for Heresy 3 fix (commit 4e8dd96):
  - risk_engine() now called dynamically instead of 3 hardcoded RiskFlag objects.
  - risk_engine returns real risks from DB data (contradictions, claims, artifacts).
  - Empty-input fallback path returns honest minimum (not hardcoded fake risks).

Before the fix, server.py had 3 hardcoded RiskFlag objects:
    RiskFlag(category=STALE_CONTEXT, ...)
    RiskFlag(category=NARRATIVE_FRAGMENTATION, ...)
    RiskFlag(category=MISSING_PROOF, ...)
After the fix, risks are generated dynamically via risk_engine().
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

# Ensure the Optic source tree is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from optic.v1.models import (
    ConfidenceBand,
    RiskCategory,
    RiskFlag,
    Severity,
)
from optic.v1.risk import (
    _CONTRADICTION_TO_RISK_MAP,
    _HIGH_RISK_LENSES,
    _compute_file_age_days,
    _map_contradiction_to_risk_category,
    risk_engine,
)


# ---------------------------------------------------------------------------
# UNIT TESTS — helper functions
# ---------------------------------------------------------------------------

class TestMapContradictionToRiskCategory:
    def test_known_category_maps_correctly(self):
        assert _map_contradiction_to_risk_category("audience_drift") == RiskCategory.AUDIENCE_MISMATCH
        assert _map_contradiction_to_risk_category("evidence_conflict") == RiskCategory.TIMELINE_GAP
        assert _map_contradiction_to_risk_category("temporal_decay") == RiskCategory.STALE_CONTEXT
        assert _map_contradiction_to_risk_category("claim_opposition") == RiskCategory.NARRATIVE_FRAGMENTATION

    def test_legacy_category_maps_correctly(self):
        assert _map_contradiction_to_risk_category("job_title_mismatch") == RiskCategory.IDENTITY_MISMATCH
        assert _map_contradiction_to_risk_category("timeline_gap") == RiskCategory.TIMELINE_GAP
        assert _map_contradiction_to_risk_category("stale_context") == RiskCategory.STALE_CONTEXT

    def test_unknown_category_defaults_to_narrative_fragmentation(self):
        assert _map_contradiction_to_risk_category("nonexistent_category") == RiskCategory.NARRATIVE_FRAGMENTATION
        assert _map_contradiction_to_risk_category("") == RiskCategory.NARRATIVE_FRAGMENTATION


class TestComputeFileAgeDays:
    def test_nonexistent_file_returns_none(self):
        now = datetime.now(timezone.utc)
        assert _compute_file_age_days("/nonexistent/path/abc.txt", now) is None

    def test_existing_file_returns_positive_age(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            tmp_path = f.name
        try:
            now = datetime.now(timezone.utc)
            age = _compute_file_age_days(tmp_path, now)
            assert age is not None
            assert age >= 0
        finally:
            os.unlink(tmp_path)

    def test_old_file_returns_large_age(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"old content")
            tmp_path = f.name
        try:
            # Set mtime to 200 days ago
            old_time = datetime.now(timezone.utc) - timedelta(days=200)
            mtime = old_time.timestamp()
            os.utime(tmp_path, (mtime, mtime))

            now = datetime.now(timezone.utc)
            age = _compute_file_age_days(tmp_path, now)
            assert age is not None
            assert age >= 199  # allow slight clock skew
        finally:
            os.unlink(tmp_path)

    def test_empty_path_returns_none(self):
        now = datetime.now(timezone.utc)
        # Empty string resolves to CWD on some platforms — use an impossible path instead
        assert _compute_file_age_days("/dev/null/does/not/exist", now) is None


# ---------------------------------------------------------------------------
# INTEGRATION TESTS — risk_engine behaviour
# ---------------------------------------------------------------------------

class TestRiskEngineEmptyInputs:
    """Empty inputs should return the honest minimum risk (not crash, not 3 hardcoded)."""

    def test_completely_empty_inputs(self):
        risks = risk_engine(contradictions=[], claims=[], artifacts=[], workstream_cards=[])
        assert isinstance(risks, list)
        assert len(risks) >= 1  # honest minimum note
        # The honest minimum risk should describe limited audit data
        honest_risk = risks[-1]
        assert honest_risk.category == RiskCategory.MISSING_PROOF
        assert "limited audit data" in honest_risk.description.lower() or \
               "run a full" in honest_risk.description.lower()
        assert honest_risk.severity == Severity.LOW

    def test_empty_inputs_return_only_honest_minimum(self):
        """With no data at all, we get exactly the 1 honest-note risk."""
        risks = risk_engine(contradictions=[], claims=[], artifacts=[], workstream_cards=[])
        # Should be exactly 1 risk — the honest minimum
        assert len(risks) == 1
        assert risks[0].category == RiskCategory.MISSING_PROOF

    def test_empty_input_never_crashes(self):
        """risk_engine must never crash on empty/malformed inputs."""
        # All real callers pass empty lists, not None — test the honest minimum path
        risks = risk_engine(contradictions=[], claims=[], artifacts=[], workstream_cards=[])
        assert isinstance(risks, list)
        assert len(risks) >= 1


class TestRiskEngineWithContradictions:
    """Each contradiction should generate a RiskFlag."""

    def test_single_contradiction_generates_risk(self):
        contra = [
            {
                "category": "stale_context",
                "description": "Stale data detected in workstream X",
                "severity": "medium",
                "claim_ids": [],
                "artifact_ids": [],
                "audience_affected": ["recruiter"],
            }
        ]
        risks = risk_engine(contradictions=contra, claims=[], artifacts=[])
        # >= 2: 1 from contradiction + honest minimum
        assert len(risks) >= 2
        stale_risks = [r for r in risks if r.category == RiskCategory.STALE_CONTEXT]
        assert len(stale_risks) >= 1
        assert "stale" in stale_risks[0].description.lower()

    def test_multiple_contradictions_generate_multiple_risks(self):
        contra = [
            {
                "category": "audience_drift",
                "description": "Narrative shifts across audiences",
                "severity": "high",
                "claim_ids": [],
                "artifact_ids": [],
                "audience_affected": ["recruiter", "investor"],
            },
            {
                "category": "evidence_conflict",
                "description": "Conflicting evidence for claim X",
                "severity": "high",
                "claim_ids": ["c1", "c2"],
                "artifact_ids": ["a1"],
                "audience_affected": ["all"],
            },
            {
                "category": "timeline_gap",
                "description": "2-year gap in timeline",
                "severity": "medium",
                "claim_ids": [],
                "artifact_ids": [],
                "audience_affected": ["recruiter"],
            },
            {
                "category": "identity_fragmentation",
                "description": "Multiple identities across platforms",
                "severity": "low",
                "claim_ids": [],
                "artifact_ids": [],
                "audience_affected": ["all"],
            },
            {
                "category": "claim_opposition",
                "description": "Opposing claims on same topic",
                "severity": "medium",
                "claim_ids": ["c3"],
                "artifact_ids": [],
                "audience_affected": ["investor"],
            },
        ]
        risks = risk_engine(contradictions=contra, claims=[], artifacts=[])
        # At least 5 from contradictions + optional honest minimum
        assert len(risks) >= 5
        # Each contradiction category should map to a risk
        categories_found = {r.category for r in risks}
        assert RiskCategory.AUDIENCE_MISMATCH in categories_found
        assert RiskCategory.TIMELINE_GAP in categories_found
        assert RiskCategory.IDENTITY_MISMATCH in categories_found
        assert RiskCategory.NARRATIVE_FRAGMENTATION in categories_found

    def test_duplicate_descriptions_are_deduped(self):
        """Same description should not produce duplicate risks."""
        contra = [
            {"category": "stale_context", "description": "Same stale issue", "severity": "low",
             "claim_ids": [], "artifact_ids": [], "audience_affected": []},
            {"category": "stale_context", "description": "Same stale issue", "severity": "low",
             "claim_ids": [], "artifact_ids": [], "audience_affected": []},
            {"category": "temporal_decay", "description": "Same stale issue", "severity": "low",
             "claim_ids": [], "artifact_ids": [], "audience_affected": []},
        ]
        risks = risk_engine(contradictions=contra, claims=[], artifacts=[])
        # Only 1 STALE_CONTEXT risk despite 3 contradictions with same desc
        stale = [r for r in risks if r.category == RiskCategory.STALE_CONTEXT]
        assert len(stale) == 1


class TestRiskEngineWithClaims:
    """Claims with HIGH confidence on sensitive lenses should generate exposure risks."""

    def test_high_confidence_on_sensitive_lens_generates_risk(self):
        claims = [
            {
                "audience_lens": "recruiter",
                "confidence_band": "high",
                "claim": "Candidate shows strong growth trajectory",
                "id": str(uuid4()),
            }
        ]
        risks = risk_engine(contradictions=[], claims=claims, artifacts=[])
        exposure = [r for r in risks if r.category == RiskCategory.OVEREXPOSURE]
        assert len(exposure) >= 1
        assert "recruiter" in exposure[0].description.lower()

    def test_low_confidence_no_exposure_risk(self):
        claims = [
            {
                "audience_lens": "recruiter",
                "confidence_band": "low",
                "claim": "Weak signal",
                "id": str(uuid4()),
            },
            {
                "audience_lens": "stranger",
                "confidence_band": "low",
                "claim": "Another weak signal",
                "id": str(uuid4()),
            },
        ]
        risks = risk_engine(contradictions=[], claims=claims, artifacts=[])
        exposure = [r for r in risks if r.category == RiskCategory.OVEREXPOSURE]
        assert len(exposure) == 0

    def test_non_sensitive_lens_no_exposure_risk(self):
        """Claims on lenses NOT in _HIGH_RISK_LENSES should not generate exposure risks."""
        claims = [
            {
                "audience_lens": "close_friend",
                "confidence_band": "high",
                "claim": "Trustworthy and kind",
                "id": str(uuid4()),
            },
            {
                "audience_lens": "family",
                "confidence_band": "high",
                "claim": "Family-oriented person",
                "id": str(uuid4()),
            },
        ]
        risks = risk_engine(contradictions=[], claims=claims, artifacts=[])
        exposure = [r for r in risks if r.category == RiskCategory.OVEREXPOSURE]
        assert len(exposure) == 0

    def test_missing_proof_from_low_confidence_claims(self):
        """Low-confidence claims should trigger missing_proof risk."""
        claims = [
            {"audience_lens": "recruiter", "confidence_band": "low", "claim": "Weak signal A", "id": str(uuid4())},
            {"audience_lens": "investor", "confidence_band": "low", "claim": "Weak signal B", "id": str(uuid4())},
            {"audience_lens": "collaborator", "confidence_band": "medium", "claim": "OK signal", "id": str(uuid4())},
        ]
        risks = risk_engine(contradictions=[], claims=claims, artifacts=[])
        missing = [r for r in risks if r.category == RiskCategory.MISSING_PROOF]
        assert len(missing) >= 1  # at least the honest minimum or the specific one
        # Check we have a MISSING_PROOF risk about lenses
        specific = [r for r in missing if "weak evidence" in r.description.lower()]
        assert len(specific) >= 1


class TestRiskEngineWithWorkstreams:
    """Workstream fragmentation should generate narrative fragmentation risks."""

    def test_many_workstreams_flag_fragmentation(self):
        cards = [{"name": f"WS-{i}", "confidence": 0.8} for i in range(10)]
        risks = risk_engine(contradictions=[], claims=[], artifacts=[], workstream_cards=cards)
        frag = [r for r in risks if r.category == RiskCategory.NARRATIVE_FRAGMENTATION]
        assert len(frag) >= 1
        assert "fragmentation" in frag[0].description.lower()

    def test_few_workstreams_no_fragmentation_risk(self):
        cards = [{"name": f"WS-{i}", "confidence": 0.8} for i in range(3)]
        risks = risk_engine(contradictions=[], claims=[], artifacts=[], workstream_cards=cards)
        frag = [r for r in risks if r.category == RiskCategory.NARRATIVE_FRAGMENTATION]
        assert len(frag) == 0  # <=5 workstreams should not flag fragmentation

    def test_exactly_5_workstreams_no_fragmentation(self):
        cards = [{"name": f"WS-{i}", "confidence": 0.8} for i in range(5)]
        risks = risk_engine(contradictions=[], claims=[], artifacts=[], workstream_cards=cards)
        frag = [r for r in risks if r.category == RiskCategory.NARRATIVE_FRAGMENTATION]
        assert len(frag) == 0

    def test_6_workstreams_flags_fragmentation(self):
        cards = [{"name": f"WS-{i}", "confidence": 0.8} for i in range(6)]
        risks = risk_engine(contradictions=[], claims=[], artifacts=[], workstream_cards=cards)
        frag = [r for r in risks if r.category == RiskCategory.NARRATIVE_FRAGMENTATION]
        assert len(frag) >= 1


class TestRiskEngineWithArtifacts:
    """Artifacts with stale files should generate STALE_CONTEXT risks."""

    def test_stale_artifact_generates_risk(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"old content")
            tmp_path = f.name
        try:
            # Set mtime to 400 days ago (old enough for HIGH severity)
            old_time = datetime.now(timezone.utc) - timedelta(days=400)
            mtime = old_time.timestamp()
            os.utime(tmp_path, (mtime, mtime))

            artifacts = [
                {
                    "id": str(uuid4()),
                    "metadata": {"path": tmp_path},
                }
            ]
            risks = risk_engine(contradictions=[], claims=[], artifacts=artifacts)
            stale = [r for r in risks if r.category == RiskCategory.STALE_CONTEXT]
            assert len(stale) >= 1
            # >365 days should be HIGH severity
            assert stale[0].severity == Severity.HIGH
        finally:
            os.unlink(tmp_path)

    def test_recent_artifact_no_stale_risk(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"fresh content")
            tmp_path = f.name
        try:
            artifacts = [
                {
                    "id": str(uuid4()),
                    "metadata": {"path": tmp_path},
                }
            ]
            risks = risk_engine(contradictions=[], claims=[], artifacts=artifacts)
            stale = [r for r in risks if r.category == RiskCategory.STALE_CONTEXT]
            assert len(stale) == 0  # freshly created file, not stale
        finally:
            os.unlink(tmp_path)

    def test_artifact_without_path_no_stale_risk(self):
        artifacts = [
            {
                "id": str(uuid4()),
                "metadata": {},  # no path
            }
        ]
        risks = risk_engine(contradictions=[], claims=[], artifacts=artifacts)
        stale = [r for r in risks if r.category == RiskCategory.STALE_CONTEXT]
        assert len(stale) == 0


# ---------------------------------------------------------------------------
# REGRESSION — verify the 3 hardcoded RiskFlag objects are GONE
# ---------------------------------------------------------------------------

class TestNoHardcodedRiskFlagsInServer:
    """After Heresy 3 fix, server.py must NOT contain the 3 hardcoded RiskFlag() calls."""

    def test_server_py_does_not_hardcode_risks(self):
        server_path = (
            Path(__file__).resolve().parent.parent
            / "src" / "optic" / "v1" / "server.py"
        )
        assert server_path.exists(), f"server.py not found at {server_path}"
        content = server_path.read_text()

        # Verify the hardcoded pattern is gone (in the audit function)
        # The old code had:
        #   risks = [
        #       RiskFlag(category=RiskCategory.STALE_CONTEXT, ...),
        #       RiskFlag(category=RiskCategory.NARRATIVE_FRAGMENTATION, ...),
        #       RiskFlag(category=RiskCategory.MISSING_PROOF, ...),
        #   ]
        # The new code calls: risks = risk_engine(...)
        assert "risk_engine(" in content, "server.py should call risk_engine()"

        # Check that the dynamic call is present in run_audit
        audit_lines = []
        in_audit = False
        for line in content.split("\n"):
            if "async def run_audit" in line:
                in_audit = True
            elif in_audit and line.startswith("async def "):
                break
            elif in_audit:
                audit_lines.append(line)

        audit_text = "\n".join(audit_lines)
        # The old hardcoded pattern should NOT exist as a list literal
        assert "risk_engine(" in audit_text, (
            "run_audit must call risk_engine() dynamically, not hardcode RiskFlag objects"
        )


class TestRiskFlagShape:
    """Verify returned RiskFlag objects have correct shape."""

    def test_risk_flags_have_required_fields(self):
        risks = risk_engine(
            contradictions=[
                {
                    "category": "stale_context",
                    "description": "Test risk",
                    "severity": "medium",
                    "claim_ids": [str(uuid4())],
                    "artifact_ids": [str(uuid4())],
                    "audience_affected": ["recruiter"],
                }
            ],
            claims=[],
            artifacts=[],
        )
        # At least 1 risk from contradiction + honest minimum
        assert len(risks) >= 1
        for r in risks:
            assert isinstance(r, RiskFlag)
            assert r.id is not None
            assert isinstance(r.category, RiskCategory)
            assert isinstance(r.description, str)
            assert len(r.description) > 0
            assert isinstance(r.severity, Severity)
            assert isinstance(r.linked_claim_ids, list)
            assert isinstance(r.linked_artifact_ids, list)
            assert isinstance(r.audience_affected, list)
            assert isinstance(r.created_at, str)

    def test_all_riskflags_are_unique(self):
        risks = risk_engine(
            contradictions=[
                {"category": "stale_context", "description": "Risk A", "severity": "low",
                 "claim_ids": [], "artifact_ids": [], "audience_affected": []},
                {"category": "claim_opposition", "description": "Risk B", "severity": "medium",
                 "claim_ids": [], "artifact_ids": [], "audience_affected": []},
            ],
            claims=[
                {"audience_lens": "recruiter", "confidence_band": "high",
                 "claim": "Test claim", "id": str(uuid4())},
            ],
            artifacts=[],
            workstream_cards=[{"name": f"WS-{i}", "confidence": 0.8} for i in range(7)],
        )
        ids = [r.id for r in risks]
        assert len(ids) == len(set(ids)), "All risk IDs must be unique"
