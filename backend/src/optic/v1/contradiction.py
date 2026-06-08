"""
Optic V1 — Contradiction Engine
================================
Finds gaps, conflicts, stale context, and audience-dependent ambiguity
across the user's evidence graph.
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from .models import (
    Artifact, Contradiction, Entity, EvidenceLink,
    InferenceClaim, ParsedSpan, Severity,
)


class ContradictionEngine:
    """Finds contradictions across claims, profiles, and evidence."""

    def find_job_title_mismatches(
        self,
        claims: List[InferenceClaim],
        entities: List[Entity],
        threshold: int = 1,
    ) -> List[Contradiction]:
        """Detect different job titles across profiles."""
        contradictions = []
        job_entities = [e for e in entities if e.type == "employer"]
        title_signals = {}

        for claim in claims:
            if "title" in claim.title.lower() or "role" in claim.title.lower():
                key = claim.audience_lens
                if key not in title_signals:
                    title_signals[key] = []
                title_signals[key].append(claim)

        for audience, audience_claims in title_signals.items():
            titles = set()
            for c in audience_claims:
                titles.add(c.claim.lower())

            if len(titles) > threshold:
                contradictions.append(Contradiction(
                    id=uuid4(),
                    category="job_title_mismatch",
                    description=f"Different titles found across {len(titles)} sources",
                    claim_ids=[c.id for c in audience_claims],
                    artifact_ids=[],
                    severity=Severity.MEDIUM if len(titles) > 2 else Severity.LOW,
                    audience_affected=[audience],
                    resolution_suggestion="Align LinkedIn headline, resume, and portfolio titles"
                ))

        return contradictions

    def find_timeline_conflicts(
        self,
        artifacts: List[Artifact],
        claims: List[InferenceClaim],
    ) -> List[Contradiction]:
        """Detect timeline gaps or inconsistent dates."""
        contradictions = []
        dated_artifacts = []
        for a in artifacts:
            created = a.metadata.get("date") or a.metadata.get("created")
            if created:
                dated_artifacts.append((created, a))

        dated_artifacts.sort(key=lambda x: str(x[0]))

        # Find gaps > 2 years with no context
        for i in range(1, len(dated_artifacts)):
            prev_date_str = str(dated_artifacts[i - 1][0])
            curr_date_str = str(dated_artifacts[i][0])
            try:
                prev = datetime.fromisoformat(prev_date_str.replace("Z", "+00:00"))
                curr = datetime.fromisoformat(curr_date_str.replace("Z", "+00:00"))
                gap_days = (curr - prev).days
                if gap_days > 730:  # 2 years
                    contradictions.append(Contradiction(
                        id=uuid4(),
                        category="timeline_gap",
                        description=(
                            f"{gap_days} day gap between {prev.strftime('%Y-%m')} "
                            f"and {curr.strftime('%Y-%m')} with no context"
                        ),
                        claim_ids=[],
                        artifact_ids=[
                            dated_artifacts[i - 1][1].id,
                            dated_artifacts[i][1].id,
                        ],
                        severity=Severity.MEDIUM if gap_days > 1095 else Severity.LOW,
                        audience_affected=["recruiter", "investor"],
                        resolution_suggestion="Add context for the gap period"
                    ))
            except (ValueError, TypeError):
                continue

        return contradictions

    def find_stale_context(
        self,
        artifacts: List[Artifact],
        max_age_days: int = 365,
    ) -> List[Contradiction]:
        """Flag artifacts older than max_age_days that appear to be active context."""
        contradictions = []
        now = datetime.now(timezone.utc)

        for a in artifacts:
            created = a.metadata.get("date") or a.metadata.get("created")
            if not created:
                continue
            try:
                created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                age_days = (now - created_dt).days
                if age_days > max_age_days and a.is_public:
                    contradictions.append(Contradiction(
                        id=uuid4(),
                        category="stale_context",
                        description=f"Public artifact is {age_days} days old and may appear current",
                        claim_ids=[],
                        artifact_ids=[a.id],
                        severity=Severity.LOW,
                        audience_affected=["stranger", "recruiter"],
                        resolution_suggestion="Update or archive the stale content"
                    ))
            except (ValueError, TypeError):
                continue

        return contradictions

    def find_profile_mismatches(
        self,
        entities: List[Entity],
    ) -> List[Contradiction]:
        """Find entities that should be linked but aren't, or that conflict."""
        contradictions = []
        name_groups: dict[str, List[Entity]] = {}

        for e in entities:
            key = e.name.lower().strip()
            if key not in name_groups:
                name_groups[key] = []
            name_groups[key].append(e)

        for name, group in name_groups.items():
            if len(group) > 1:
                types = {e.type for e in group}
                if len(types) > 1:
                    contradictions.append(Contradiction(
                        id=uuid4(),
                        category="identity_fragmentation",
                        description=f"'{name}' appears as multiple types: {types}",
                        claim_ids=[],
                        artifact_ids=[],
                        severity=Severity.MEDIUM,
                        audience_affected=["all"],
                        resolution_suggestion="Link these entities or clarify the distinction"
                    ))

        return contradictions

    def find_claim_contradictions(
        self,
        claims: List[InferenceClaim],
    ) -> List[Contradiction]:
        """Find claims that directly contradict each other."""
        contradictions = []
        for i, c1 in enumerate(claims):
            for c2 in claims[i + 1:]:
                if c1.audience_lens == c2.audience_lens:
                    # Check for semantic opposition (simple heuristic)
                    c1_words = set(c1.claim.lower().split())
                    c2_words = set(c2.claim.lower().split())
                    opposition_markers = {
                        "not", "no", "never", "unlike", "opposite",
                        "contrary", "however", "but", "although"
                    }
                    overlap = c1_words & c2_words
                    if overlap and any(m in c1.claim.lower() or m in c2.claim.lower()
                                      for m in opposition_markers):
                        contradictions.append(Contradiction(
                            id=uuid4(),
                            category="claim_opposition",
                            description=f"'{c1.claim[:60]}' vs '{c2.claim[:60]}'",
                            claim_ids=[c1.id, c2.id],
                            artifact_ids=[],
                            severity=Severity.HIGH,
                            audience_affected=[c1.audience_lens],
                            resolution_suggestion="Resolve the contradiction or add context"
                        ))

        return contradictions

    def run_full_audit(
        self,
        claims: List[InferenceClaim],
        artifacts: List[Artifact],
        entities: List[Entity],
    ) -> List[Contradiction]:
        """Run all contradiction checks and return combined results."""
        results = []
        results.extend(self.find_job_title_mismatches(claims, entities))
        results.extend(self.find_timeline_conflicts(artifacts, claims))
        results.extend(self.find_stale_context(artifacts))
        results.extend(self.find_profile_mismatches(entities))
        results.extend(self.find_claim_contradictions(claims))
        return results
