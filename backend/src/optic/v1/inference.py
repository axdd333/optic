"""
Optic V1 — Inference Card Generator
====================================
Creates structured inference claims from signals, evidence, and audience lenses.
Every claim must cite evidence, expose uncertainty, and show counterarguments.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from .lenses import AUDIENCE_LENSES
from .models import (
    Artifact, AudienceLens, ConfidenceBand, EvidenceLink,
    InferenceClaim, Signal, Severity,
)


class InferenceCardGenerator:
    """Generates structured inference claims for a specific audience lens."""

    def __init__(self, lens_id: str):
        self.lens = AUDIENCE_LENSES.get(lens_id)
        if not self.lens:
            raise ValueError(f"Unknown audience lens: {lens_id}")

    def generate_claims(
        self,
        signals: List[Signal],
        artifacts: List[Artifact],
        existing_claims: Optional[List[InferenceClaim]] = None,
    ) -> List[InferenceClaim]:
        """Generate inference claims from signals for this audience."""
        claims = []
        existing_claims = existing_claims or []

        for signal in signals:
            claim = self._signal_to_claim(signal, artifacts)
            if claim and self._passes_lens_filter(claim):
                claim = self._add_counterargument(claim, artifacts, existing_claims)
                claims.append(claim)

        return self._sort_by_impact(claims)

    def _signal_to_claim(
        self,
        signal: Signal,
        artifacts: List[Artifact],
    ) -> Optional[InferenceClaim]:
        """Convert a signal into a structured inference claim."""
        relevant_artifacts = [
            a for a in artifacts if a.id in signal.source_artifact_ids
        ]

        evidence_count = len(relevant_artifacts)
        if evidence_count < self.lens.confidence_rules.get("min_evidence_count", 1):
            return None

        # Determine confidence band
        confidence = self._compute_confidence(signal, evidence_count)

        # Build claim text based on signal category
        claim_text = self._build_claim_text(signal, self.lens)

        # Find supporting and weakening evidence
        supporting = [a.id for a in relevant_artifacts[:5]]
        weakening = self._find_weakening_evidence(signal, artifacts)

        return InferenceClaim(
            id=uuid4(),
            title=f"{self.lens.name}: {signal.category}",
            audience_lens=self.lens.id,
            claim=claim_text,
            confidence_band=confidence,
            evidence_count=evidence_count,
            supporting_evidence=supporting,
            weakening_evidence=weakening[:3],
            source_gaps=self._identify_source_gaps(signal),
            recency=self._compute_recency(artifacts),
            severity=signal.severity,
            actionability=self._compute_actionability(signal),
            possible_consequence=self._predict_consequence(signal, self.lens),
            counterargument="",  # filled by _add_counterargument
            repair_options=[],
            model_version="optic-v1-alpha",
            not_a_verdict=True,
        )

    def _compute_confidence(
        self,
        signal: Signal,
        evidence_count: int,
    ) -> ConfidenceBand:
        """Compute confidence band from evidence count and quality."""
        rules = self.lens.confidence_rules
        min_evidence = rules.get("min_evidence_count", 2)

        if evidence_count >= min_evidence * 2:
            return ConfidenceBand.HIGH
        elif evidence_count >= min_evidence:
            return ConfidenceBand.MEDIUM
        return ConfidenceBand.LOW

    def _build_claim_text(self, signal: Signal, lens: AudienceLens) -> str:
        """Build a human-readable claim from a signal and lens."""
        templates = {
            "frequent_topic": f"A {lens.name.lower()} may notice consistent focus on {signal.description}",
            "timeline_gap": f"A {lens.name.lower()} may question the {signal.description} gap in your timeline",
            "stale_bio": f"A {lens.name.lower()} may read your {signal.description} as outdated",
            "inconsistent_title": f"A {lens.name.lower()} may find your {signal.description} inconsistent across platforms",
            "public_association": f"A {lens.name.lower()} may associate you with {signal.description}",
            "project_velocity": f"A {lens.name.lower()} may assess your project output as {signal.description}",
            "controversial_phrase": f"A {lens.name.lower()} may flag {signal.description} as potentially controversial",
            "unclear_credential": f"A {lens.name.lower()} may find your {signal.description} unclear or unverified",
        }
        return templates.get(
            signal.category,
            f"A {lens.name.lower()} may interpret {signal.description} as a signal",
        )

    def _passes_lens_filter(self, claim: InferenceClaim) -> bool:
        """Check if the claim passes the lens's forbidden output rules."""
        claim_lower = claim.claim.lower()
        for forbidden in self.lens.forbidden_outputs:
            if forbidden.lower() in claim_lower:
                return False
        return True

    def _add_counterargument(
        self,
        claim: InferenceClaim,
        artifacts: List[Artifact],
        existing_claims: List[InferenceClaim],
    ) -> InferenceClaim:
        """Generate a counterargument for the claim."""
        # Find evidence that weakens the claim
        weakening = [
            a for a in artifacts
            if a.id in claim.weakening_evidence
        ]

        if not weakening and not existing_claims:
            claim.counterargument = (
                f"No direct contradictory evidence found. "
                f"This reading is based on {claim.evidence_count} sources "
                f"and should be treated as a hypothesis, not a verdict."
            )
            return claim

        if weakening:
            sources = len(weakening)
            claim.counterargument = (
                f"However, {sources} source{'s' if sources > 1 else ''} "
                f"provide context that may weaken this reading. "
                f"Consider reviewing these before acting on this claim."
            )
        else:
            # Look for claims that support alternative readings
            alt_claims = [
                c for c in existing_claims
                if c.audience_lens == claim.audience_lens
                and c.id != claim.id
            ]
            if alt_claims:
                claim.counterargument = (
                    f"Alternative readings exist. "
                    f"See related claims for a more complete picture."
                )
            else:
                claim.counterargument = (
                    f"This reading is based on available evidence. "
                    f"Additional sources may change or weaken this interpretation. "
                    f"Not a verdict."
                )

        return claim

    def _find_weakening_evidence(
        self,
        signal: Signal,
        artifacts: List[Artifact],
    ) -> List[UUID]:
        """Find artifacts that may weaken the signal."""
        weakening = []
        for a in artifacts:
            if a.id not in signal.source_artifact_ids:
                # Check if this artifact provides alternative context
                if self._is_relevant_alternative(a, signal):
                    weakening.append(a.id)
        return weakening

    def _is_relevant_alternative(
        self,
        artifact: Artifact,
        signal: Signal,
    ) -> bool:
        """Check if an artifact provides alternative context for a signal."""
        # Simple heuristic: same time period but different content
        signal_artifacts = signal.metadata.get("artifact_dates", {})
        artifact_date = artifact.metadata.get("date", "")
        if artifact_date and signal_artifacts:
            return any(
                abs(self._date_diff(artifact_date, sd)) < 90
                for sd in signal_artifacts.values()
                if sd
            )
        return False

    @staticmethod
    def _date_diff(d1: str, d2: str) -> int:
        """Difference in days between two ISO date strings."""
        from datetime import datetime, timezone
        try:
            dt1 = datetime.fromisoformat(d1.replace("Z", "+00:00"))
            dt2 = datetime.fromisoformat(d2.replace("Z", "+00:00"))
            return abs((dt1 - dt2).days)
        except (ValueError, TypeError):
            return 999

    def _identify_source_gaps(self, signal: Signal) -> List[str]:
        """Identify what kinds of sources are missing."""
        gaps = []
        for priority in self.lens.evidence_preferences:
            if priority not in str(signal.metadata.get("source_types", [])):
                gaps.append(f"Missing {priority} evidence")
        return gaps[:3]

    def _compute_recency(self, artifacts: List[Artifact]) -> str:
        """Determine recency of the evidence."""
        if not artifacts:
            return "unknown"
        now = datetime.now(timezone.utc)
        ages = []
        for a in artifacts:
            created = a.metadata.get("date") or a.metadata.get("created")
            if created:
                try:
                    dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    ages.append((now - dt).days)
                except (ValueError, TypeError):
                    pass
        if not ages:
            return "unknown"
        avg_age = sum(ages) / len(ages)
        if avg_age < 90:
            return "recent"
        elif avg_age < 365:
            return "mixed"
        return "stale"

    def _compute_actionability(self, signal: Signal) -> str:
        """How actionable is this signal?"""
        actionable_categories = {
            "stale_bio", "inconsistent_title", "old_username",
            "public_metadata", "missing_proof", "credential_ambiguity"
        }
        if signal.category in actionable_categories:
            return "high"
        return "low"

    def _predict_consequence(
        self,
        signal: Signal,
        lens: AudienceLens,
    ) -> str:
        """Predict possible consequence of this signal for this audience."""
        templates = {
            "recruiter": "May affect hiring decisions or role fit assessment",
            "investor": "May affect funding decisions or trust assessment",
            "admissions": "May affect application review",
            "creator": "May affect audience trust or brand perception",
            "stranger": "May affect first impression from public fragments",
            "customer": "May affect client trust or purchase decisions",
            "collaborator": "May affect team formation or partnership decisions",
            "ad_platform": "May affect ad targeting or consumer categorization",
            "future_agent": "May affect how AI systems summarize or categorize you",
        }
        return templates.get(lens.id, "May affect how this audience perceives you")

    @staticmethod
    def _sort_by_impact(claims: List[InferenceClaim]) -> List[InferenceClaim]:
        """Sort claims by severity then confidence."""
        severity_order = {
            Severity.CRITICAL: 0, Severity.HIGH: 1,
            Severity.MEDIUM: 2, Severity.LOW: 3,
        }
        return sorted(
            claims,
            key=lambda c: (
                severity_order.get(c.severity, 3),
                {"high": 0, "medium": 1, "low": 2}.get(
                    c.confidence_band.value if hasattr(c.confidence_band, 'value')
                    else str(c.confidence_band),
                    2
                )
            )
        )
