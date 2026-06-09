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

    # ── Triviality & dedup helpers ──────────────────────────────────

    @staticmethod
    def _word_overlap_ratio(text_a: str, text_b: str) -> float:
        """Jaccard similarity of word sets (0.0–1.0)."""
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    @staticmethod
    def _opposition_in_difference(text_a: str, text_b: str) -> bool:
        """Check that opposition markers appear in the DIFFERING words,
        not in the shared prefix that both claims agree on.

        Detects real semantic contradiction (e.g. 'focus on code' vs
        'no code activity') while ignoring topic shifts that share
        template language ('focus on code' vs 'focus on writing').
        """
        NEGATION = {
            "not", "no", "never", "doesn't", "don't", "cannot",
            "can't", "won't", "wouldn't", "isn't", "aren't", "wasn't",
            "weren't", "hasn't", "haven't", "hadn't", "nothing",
            "nowhere", "none", "nor", "neither",
        }
        CONTRAST = {
            "but", "however", "although", "though", "yet",
            "while", "whereas", "on the other hand", "instead",
            "rather", "conversely", "unlike", "opposite",
            "contrary", "different", "versus",
        }
        FLIP_MARKERS = {
            "unlikely", "rarely", "seldom", "barely", "hardly",
            "minimal", "absent", "missing", "lacking", "limited",
            "weak", "low", "poor", "insufficient",
        }
        # Strong positive markers vs flip markers = contradiction signal
        STRONG_POSITIVE = {
            "strong", "high", "significant", "substantial", "deep",
            "extensive", "consistent", "concentrated", "focused",
            "clear", "evident", "prominent", "notable", "major",
        }

        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        shared = words_a & words_b
        diff = (words_a - words_b) | (words_b - words_a)

        # Condition 1: negation or contrast in the difference
        if diff & (NEGATION | CONTRAST):
            return True

        # Condition 2: polarity flip — one side has strong positive,
        # the other has flip/weak markers in the difference
        has_positive = bool(shared & STRONG_POSITIVE)
        a_has_flip = bool((words_a - words_b) & FLIP_MARKERS)
        b_has_flip = bool((words_b - words_a) & FLIP_MARKERS)
        if has_positive and (a_has_flip or b_has_flip):
            return True

        # Condition 3: explicit "vs" / "rather than" present
        combined = text_a.lower() + " " + text_b.lower()
        if any(m in combined for m in ("rather than", "instead of", "as opposed to")):
            return True

        return False

    @staticmethod
    def _canonical_key(contradiction: Contradiction) -> str:
        """Stable key for dedup: sorted claim pair + normalized desc."""
        cids = sorted(str(cid) for cid in contradiction.claim_ids)
        # Normalize description: lowercase, strip quotes, collapse whitespace
        desc = " ".join(contradiction.description.lower().split())
        return f"{'|'.join(cids)}||{desc}"

    @staticmethod
    def _severity_from_overlap(overlap_ratio: float) -> Severity:
        """Map word overlap ratio to severity.
        High overlap = near-identical claims = trivial (LOW).
        Low overlap = genuinely different claims in conflict (HIGH)."""
        if overlap_ratio >= 0.70:
            return Severity.LOW       # near-duplicate, trivial
        elif overlap_ratio >= 0.40:
            return Severity.MEDIUM    # moderate difference
        else:
            return Severity.HIGH      # substantially different claims

    # ── Detection methods ──────────────────────────────────────────

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
        triviality_threshold: float = 0.85,
    ) -> List[Contradiction]:
        """Find claims that directly contradict each other.

        FILTERING RULES (applied per candidate pair):
        1. EXACT DUPLICATE DEDUP  — same claim-pair → keep first only
        2. TRIVIALITY FILTER      — >85% word overlap → NOT a real contradiction
        3. OPPOSITION IN DIFF     — marker must be in the DIFFERING words
        4. SEVERITY RECALIBRATION — overlap ratio maps to LOW/MED/HIGH
        """
        contradictions = []
        seen_pairs = set()  # (sorted_cid_tuple) for exact dedup
        skipped_trivial = 0
        skipped_no_opposition = 0

        for i, c1 in enumerate(claims):
            for c2 in claims[i + 1:]:
                if c1.audience_lens != c2.audience_lens:
                    continue

                # Gate 1: exact dedup by claim pair
                pair_key = tuple(sorted([str(c1.id), str(c2.id)]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Gate 2: triviality filter — near-identical claims aren't contradictory
                overlap = self._word_overlap_ratio(c1.claim, c2.claim)
                if overlap >= triviality_threshold:
                    skipped_trivial += 1
                    continue

                # Gate 3: opposition marker must be in differing words
                if not self._opposition_in_difference(c1.claim, c2.claim):
                    skipped_no_opposition += 1
                    continue

                # Gate 4: severity from semantic distance
                severity = self._severity_from_overlap(overlap)

                contradictions.append(Contradiction(
                    id=uuid4(),
                    category="claim_opposition",
                    description=f"'{c1.claim[:80]}' vs '{c2.claim[:80]}'",
                    claim_ids=[c1.id, c2.id],
                    artifact_ids=[],
                    severity=severity,
                    audience_affected=[c1.audience_lens],
                    resolution_suggestion=(
                        "Resolve the contradiction or add context"
                        if severity != Severity.LOW
                        else "Minor wording divergence — consider aligning phrasing"
                    )
                ))

        # Log filtering stats for observability
        if skipped_trivial or skipped_no_opposition:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"Contradiction engine filtered: "
                f"{skipped_trivial} trivial (>{triviality_threshold:.0%} overlap), "
                f"{skipped_no_opposition} no-opposition, "
                f"{len(contradictions)} retained"
            )

        return contradictions

    def run_full_audit(
        self,
        claims: List[InferenceClaim],
        artifacts: List[Artifact],
        entities: List[Entity],
    ) -> List[Contradiction]:
        """Run all contradiction checks and return DEDUPLICATED results.

        Post-processing dedup: canonical-key dedup across ALL categories
        catches cross-category duplicates (e.g. same claim-pair flagged by
        both claim_opposition and job_title_mismatch).
        """
        raw = []
        raw.extend(self.find_job_title_mismatches(claims, entities))
        raw.extend(self.find_timeline_conflicts(artifacts, claims))
        raw.extend(self.find_stale_context(artifacts))
        raw.extend(self.find_profile_mismatches(entities))
        raw.extend(self.find_claim_contradictions(claims))

        # ── Post-processing: cross-category dedup ─────────────────
        seen_keys = set()
        deduped = []
        duplicates_removed = 0
        for c in raw:
            key = self._canonical_key(c)
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(c)
            else:
                duplicates_removed += 1

        if duplicates_removed:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"Post-audit dedup: removed {duplicates_removed} cross-category "
                f"duplicates, {len(deduped)} contradictions retained "
                f"(from {len(raw)} raw)"
            )

        return deduped
