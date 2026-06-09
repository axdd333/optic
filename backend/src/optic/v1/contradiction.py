"""
Optic V1 — Contradiction Engine
================================
Finds gaps, conflicts, stale context, and audience-dependent ambiguity
across the user's evidence graph.
"""
from datetime import datetime, timezone
from math import exp
from typing import List, Optional
from uuid import UUID, uuid4

from .models import (
    Artifact, ConfidenceBand, Contradiction, Entity,
    EvidenceLink, InferenceClaim, ParsedSpan, Severity,
)


# ── Lens risk sensitivity (mirrors lenses.py AudienceLens config) ──
# Higher = contradictions under this lens carry more real-world weight.
_LENS_RISK_SENSITIVITY: dict[str, float] = {
    "recruiter": 0.70,
    "investor": 0.60,
    "collaborator": 0.60,
    "creator": 0.80,
    "privacy": 0.90,
    "platform": 0.30,
    "search": 0.70,
    "institution": 0.60,
    "stranger": 0.90,
}


# ── Topic / workstream keywords for claim grouping ──────────────────
# Claims that don't share at least one keyword CANNOT semantically
# contradict each other. Extracted from inference.py claim generation
# patterns and workstream naming conventions.
_TOPIC_KEYWORDS: set[str] = {
    # Workstream names (from inference.py _deduce_* functions)
    # NOTE: "work" deliberately excluded — too generic, matches
    # "workstream", "workout", "framework" across unrelated domains.
    "research", "learning", "career", "code", "project",
    "writing", "communication", "social", "profile", "identity",
    "finance", "health", "travel", "photo", "habit",
    "behavior", "relationship", "contact", "email", "message",
    "skill", "education", "employment", "resume", "cv", "bio",
    # Signal categories
    "frequent_topic", "workstream_fragmentation", "volume_spike",
    "recency_decay", "public_association", "narrative_gap",
    "evidence_thin", "counterfactual", "temporal_anomaly",
    # Topic markers
    "ai", "ml", "machine learning", "artificial intelligence",
    "engineering", "software", "data", "science", "design",
    "product", "management", "leadership", "strategy",
    "startup", "business", "investment", "portfolio",
    "open source", "community", "teaching", "mentoring",
    "security", "privacy", "infrastructure", "devops",
}


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
        desc = " ".join(contradiction.description.lower().split())
        return f"{'|'.join(cids)}||{desc}"

    # ── Topic / workstream signature extraction ─────────────────────

    @staticmethod
    def _extract_topic_signature(claim_text: str) -> str:
        """Derive a stable topic key from claim text for workstream grouping.

        Extracts known workstream/topic keywords from the claim text and
        returns a sorted, deduplicated key. Two claims about completely
        different topics (e.g. 'code' vs 'travel') will produce different
        signatures and will NOT be compared for contradiction.

        Fallback: if no keywords match, uses a hash of the first 60 chars
        as a crude topic proxy (these claims likely share structure).
        """
        import hashlib
        text_lower = claim_text.lower()
        found = sorted(
            kw for kw in _TOPIC_KEYWORDS
            if kw in text_lower
        )
        if found:
            return "|".join(found)
        return "fallback:" + hashlib.md5(
            claim_text[:60].encode()
        ).hexdigest()[:8]

    @staticmethod
    def _extract_texts_from_description(description: str) -> tuple[str, str]:
        """Parse claim texts from contradiction description.

        Format: \"'<text1>' vs '<text2>'\"
        Returns (text_a, text_b) for semantic distance computation.
        """
        desc = description.strip("'\"")
        parts = desc.split("' vs '", 1)
        if len(parts) == 2:
            a = parts[0].lstrip("'\"")
            b = parts[1].rstrip("'\"")
            return (a, b)
        return (description, "")

    # ── Multi-factor severity calibration ────────────────────────────

    @staticmethod
    def _confidence_numeric(band: ConfidenceBand) -> float:
        """Map ConfidenceBand to a 0.0–1.0 numeric weight."""
        return {
            ConfidenceBand.HIGH: 0.90,
            ConfidenceBand.MEDIUM: 0.60,
            ConfidenceBand.LOW: 0.25,
        }.get(band, 0.40)

    @staticmethod
    def _temporal_proximity(
        c1: InferenceClaim, c2: InferenceClaim
    ) -> float:
        """Compute 0.0–1.0 temporal proximity between two claims.

        Returns 1.0 if claims were generated at nearly the same time
        (suggesting a real conflict rather than natural evolution).
        Decays exponentially with a half-life of 7 days, bottoming
        at 0.10 for claims > 30 days apart.

        If one or both lack parseable timestamps, returns 0.5 (neutral).
        """
        try:
            t1 = datetime.fromisoformat(
                c1.generated_at.replace("Z", "+00:00")
            )
            t2 = datetime.fromisoformat(
                c2.generated_at.replace("Z", "+00:00")
            )
        except (ValueError, TypeError, AttributeError):
            return 0.5  # neutral when unparseable

        hours_diff = abs((t1 - t2).total_seconds()) / 3600.0
        decay = exp(-0.693147 * hours_diff / 168.0)
        return max(0.10, decay)

    @staticmethod
    def _lens_risk(lens_id: str) -> float:
        """Return the risk sensitivity for a given audience lens, 0.0–1.0."""
        return _LENS_RISK_SENSITIVITY.get(lens_id, 0.50)

    @staticmethod
    def _semantic_distance(text_a: str, text_b: str) -> float:
        """Compute 0.0–1.0 semantic distance between two claim texts.

        Uses Jaccard distance (1 - overlap) weighted by a length-divergence
        factor. Higher = more genuinely different claims in opposition.
        """
        jaccard_dist = 1.0 - ContradictionEngine._word_overlap_ratio(
            text_a, text_b
        )
        max_len = max(len(text_a), len(text_b), 1)
        min_len = min(len(text_a), len(text_b))
        len_ratio = min_len / max_len
        length_penalty = 1.0 - len_ratio
        return 0.7 * jaccard_dist + 0.3 * length_penalty

    @staticmethod
    def _calibrate_severity(
        c1: InferenceClaim,
        c2: InferenceClaim,
        distance: float,
    ) -> Severity:
        """Multi-factor severity calibration for claim_opposition.

        Factors (weighted):
          1. Semantic distance  (0.40) — how different the claims are
          2. Confidence product  (0.30) — avg confidence of both claims
          3. Temporal proximity  (0.15) — closer = more likely real conflict
          4. Audience risk       (0.15) — lens sensitivity to contradictions

        Severity banding (calibrated for 0.30–1.0 distance range):
          score >= 0.72  -> CRITICAL  (genuinely dangerous contradictions)
          score >= 0.62  -> HIGH      (strong conflict, review needed)
          score >= 0.50  -> MEDIUM    (moderate divergence)
          score <  0.50  -> LOW       (minor wording / low-impact)
        """
        sem_factor = distance
        conf1 = ContradictionEngine._confidence_numeric(c1.confidence_band)
        conf2 = ContradictionEngine._confidence_numeric(c2.confidence_band)
        conf_factor = (conf1 + conf2) / 2.0
        temp_factor = ContradictionEngine._temporal_proximity(c1, c2)
        audience_factor = ContradictionEngine._lens_risk(c1.audience_lens)

        score = (
            sem_factor * 0.40
            + conf_factor * 0.30
            + temp_factor * 0.15
            + audience_factor * 0.15
        )

        if score >= 0.72:
            return Severity.CRITICAL
        elif score >= 0.62:
            return Severity.HIGH
        elif score >= 0.50:
            return Severity.MEDIUM
        return Severity.LOW

    # ── Deprecated: kept for backward compatibility ──────────────────

    @staticmethod
    def _severity_from_overlap(overlap_ratio: float) -> Severity:
        """DEPRECATED. Map word overlap ratio to severity.

        Use _calibrate_severity for claim_opposition contradictions.
        This method only considers one factor and produces flat distributions.
        """
        if overlap_ratio >= 0.70:
            return Severity.LOW
        elif overlap_ratio >= 0.40:
            return Severity.MEDIUM
        return Severity.HIGH

    @staticmethod
    def _severity_from_distance(distance: float) -> Severity:
        """Calibrate severity from semantic distance (0.0–1.0).

        Simpler single-factor alternative to _calibrate_severity.
        Used for sorting/capping where claim objects aren't available.

        Mapping:
          distance >= 0.70  -> HIGH
          distance >= 0.45  -> MEDIUM
          distance <  0.45  -> LOW
        """
        if distance >= 0.70:
            return Severity.HIGH
        elif distance >= 0.45:
            return Severity.MEDIUM
        else:
            return Severity.LOW

    # ── Detection methods ──────────────────────────────────────────

    def find_audience_drift(
        self,
        claims: List[InferenceClaim],
        entities: List[Entity],
        min_audiences: int = 2,
    ) -> List[Contradiction]:
        """Detect claims that diverge across different audience lenses for the SAME topic.

        When the same underlying evidence produces materially different claims for
        different audiences, this signals audience-dependent narrative drift —
        a trustworthiness problem.
        """
        contradictions = []
        seen_drift_pairs: set = set()

        # Audience prefix patterns to strip when normalizing claim text
        AUDIENCE_PREFIXES = [
            f"{p}{r} read may "
            for p in ("a ", "an ")
            for r in ("recruiter", "investor", "collaborator", "creator",
                       "privacy", "stranger", "platform", "search", "institution")
        ]

        def _strip_audience_prefix(text: str) -> str:
            t = text.lower().strip()
            for prefix in AUDIENCE_PREFIXES:
                t = t.removeprefix(prefix)
            return t

        # Group claims by topic signature (content key from normalized text)
        topic_groups: dict[str, list[InferenceClaim]] = {}
        for claim in claims:
            text = _strip_audience_prefix(claim.claim)
            key = text[:60]
            if key not in topic_groups:
                topic_groups[key] = []
            topic_groups[key].append(claim)

        for topic_key, group in topic_groups.items():
            if len(group) < min_audiences:
                continue
            audiences_seen = {c.audience_lens for c in group}
            if len(audiences_seen) < min_audiences:
                continue

            # Check if claims diverge materially
            unique_claims = {}
            for c in group:
                text = _strip_audience_prefix(c.claim)
                if text not in unique_claims:
                    unique_claims[text] = c

            if len(unique_claims) < 2:
                continue

            all_artifact_ids: list[UUID] = []
            all_claim_ids: list[UUID] = []
            affected_audiences = set()
            for c in group:
                all_artifact_ids.extend(c.supporting_evidence[:3])
                all_claim_ids.append(c.id)
                affected_audiences.add(c.audience_lens)

            drift_hash = (
                "|".join(sorted(audiences_seen)) + "||" + topic_key[:40]
            )
            if drift_hash in seen_drift_pairs:
                continue
            seen_drift_pairs.add(drift_hash)

            contradictions.append(Contradiction(
                id=uuid4(),
                category="audience_drift",
                description=(
                    f"Same topic presents differently across "
                    f"{len(audiences_seen)} audiences: "
                    f"{', '.join(sorted(audiences_seen)[:4])}"
                ),
                claim_ids=all_claim_ids[:10],
                artifact_ids=list(set(all_artifact_ids))[:5],
                severity=Severity.MEDIUM if len(audiences_seen) >= 4 else Severity.LOW,
                audience_affected=list(affected_audiences),
                resolution_suggestion=(
                    "Ensure consistent representation across platforms and audiences"
                )
            ))

        return contradictions

    def find_evidence_conflicts(
        self,
        artifacts: List[Artifact],
        claims: List[InferenceClaim],
    ) -> List[Contradiction]:
        """Detect timeline gaps and date inconsistencies in evidence.

        Uses artifact metadata (mtime, date, created) and artifact.created_at
        as fallback. Timestamps are parsed and sorted numerically to find
        genuine chronological gaps.
        """
        contradictions = []
        dated_artifacts: list[tuple[datetime, Artifact]] = []

        for a in artifacts:
            # Try multiple timestamp sources: mtime (Unix) → date → created →
            # artifact.created_at
            ts = None
            mtime = a.metadata.get("mtime")
            if mtime is not None:
                try:
                    ts = datetime.fromtimestamp(float(mtime), tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pass
            if ts is None:
                for key in ("date", "created"):
                    val = a.metadata.get(key)
                    if val:
                        try:
                            ts = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                            break
                        except (ValueError, TypeError):
                            pass
            if ts is None and a.created_at:
                try:
                    ts = datetime.fromisoformat(str(a.created_at).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            if ts:
                dated_artifacts.append((ts, a))

        dated_artifacts.sort(key=lambda x: x[0])

        seen_gaps: set[tuple[str, str]] = set()

        # Find gaps > 2 years with no context
        for i in range(1, len(dated_artifacts)):
            prev_dt, prev_a = dated_artifacts[i - 1]
            curr_dt, curr_a = dated_artifacts[i]

            gap_days = (curr_dt - prev_dt).days
            if gap_days > 730:
                sorted_ids = tuple(sorted([str(prev_a.id), str(curr_a.id)]))
                pair_key: tuple[str, str] = (sorted_ids[0], sorted_ids[1])
                if pair_key in seen_gaps:
                    continue
                seen_gaps.add(pair_key)

                contradictions.append(Contradiction(
                    id=uuid4(),
                    category="evidence_conflict",
                    description=(
                        f"{gap_days:,} day gap between "
                        f"{prev_dt.strftime('%Y-%m')} and "
                        f"{curr_dt.strftime('%Y-%m')} with no context"
                    ),
                    claim_ids=[],
                    artifact_ids=[prev_a.id, curr_a.id],
                    severity=Severity.MEDIUM if gap_days > 1095 else Severity.LOW,
                    audience_affected=["recruiter", "investor"],
                    resolution_suggestion="Add context for the gap period"
                ))

        return contradictions

    def find_temporal_decay(
        self,
        artifacts: List[Artifact],
        max_age_days: int = 365,
    ) -> List[Contradiction]:
        """Flag artifacts older than max_age_days as temporally decayed.

        Public or local — all old artifacts represent stale context that may
        need review. Public artifacts get higher severity.
        Uses artifact metadata timestamps first (mtime, date, created),
        falls back to artifact.created_at.
        """
        contradictions = []
        now = datetime.now(timezone.utc)

        for a in artifacts:
            # Extract timestamp (same logic as evidence_conflicts)
            ts = None
            mtime = a.metadata.get("mtime")
            if mtime is not None:
                try:
                    ts = datetime.fromtimestamp(float(mtime), tz=timezone.utc)
                except (ValueError, TypeError, OSError):
                    pass
            if ts is None:
                for key in ("date", "created"):
                    val = a.metadata.get(key)
                    if val:
                        try:
                            ts = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                            break
                        except (ValueError, TypeError):
                            pass
            if ts is None and a.created_at:
                try:
                    ts = datetime.fromisoformat(str(a.created_at).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass
            if ts is None:
                continue

            age_days = (now - ts).days
            if age_days < max_age_days:
                continue

            if a.is_public:
                contradictions.append(Contradiction(
                    id=uuid4(),
                    category="temporal_decay",
                    description=(
                        f"Public artifact is {age_days:,} days old "
                        f"and may appear current"
                    ),
                    claim_ids=[],
                    artifact_ids=[a.id],
                    severity=Severity.MEDIUM,
                    audience_affected=["stranger", "recruiter"],
                    resolution_suggestion="Update or archive the stale content"
                ))
            else:
                contradictions.append(Contradiction(
                    id=uuid4(),
                    category="temporal_decay",
                    description=(
                        f"Local artifact is {age_days:,} days old — "
                        f"may represent stale context"
                    ),
                    claim_ids=[],
                    artifact_ids=[a.id],
                    severity=Severity.LOW,
                    audience_affected=["self"],
                    resolution_suggestion=(
                        "Review whether this content is still relevant "
                        "or should be archived"
                    )
                ))

        return contradictions

    def find_identity_fragmentation(
        self,
        entities: List[Entity],
    ) -> List[Contradiction]:
        """Find entities that appear as multiple conflicting types.

        An entity appearing under different type classifications signals
        identity fragmentation — the same subject read differently by
        different signals.
        """
        contradictions = []
        name_groups: dict[str, List[Entity]] = {}

        for e in entities:
            key = e.name.lower().strip()
            if not key:
                continue
            if key not in name_groups:
                name_groups[key] = []
            name_groups[key].append(e)

        for name, group in name_groups.items():
            if len(group) < 2:
                continue

            types = {e.type for e in group}
            if len(types) <= 1:
                continue

            entity_artifact_ids: list = []
            for e in group:
                entity_artifact_ids.extend(
                    e.metadata.get("artifact_ids", [])[:3]
                )

            contradictions.append(Contradiction(
                id=uuid4(),
                category="identity_fragmentation",
                description=(
                    f"'{name}' appears as multiple types: "
                    f"{', '.join(sorted(types))}"
                ),
                claim_ids=[],
                artifact_ids=list(set(entity_artifact_ids))[:5],
                severity=Severity.HIGH if len(types) >= 3 else Severity.MEDIUM,
                audience_affected=["all"],
                resolution_suggestion="Link these entities or clarify the distinction"
            ))

        return contradictions

    def find_claim_contradictions(
        self,
        claims: List[InferenceClaim],
        triviality_threshold: float = 0.85,
        max_per_lens: int = 20,
    ) -> List[Contradiction]:
        """Find claims that directly contradict each other.

        HERESY-9 FIX — Multi-gate filtering with topic grouping:
        0. TOPIC/WORKSTREAM GROUP  — only compare claims about same workstream
        1. EXACT DUPLICATE DEDUP    — same claim-pair -> keep first only
        2. TRIVIALITY FILTER        — >85% word overlap -> NOT a real contradiction
        3. OPPOSITION IN DIFF       — marker must be in the DIFFERING words
        4. STRONG OPPOSITION GATE   — semantic distance must be >= 0.30
        5. SEVERITY CALIBRATION     — multi-factor: distance x confidence
                                      x temporal proximity x audience risk
        6. PER-LENS CAP             — top N by semantic distance
        """
        from collections import defaultdict

        contradictions: list[Contradiction] = []
        seen_pairs: set[tuple[str, ...]] = set()
        skipped_topic = 0
        skipped_trivial = 0
        skipped_no_opposition = 0
        skipped_weak = 0

        # Pre-group claims by (lens, topic_signature)
        groups: dict[tuple[str, str], list[tuple[int, InferenceClaim]]] = defaultdict(list)
        for idx, claim in enumerate(claims):
            sig = self._extract_topic_signature(claim.claim)
            groups[(claim.audience_lens, sig)].append((idx, claim))

        # Merge all claims within same lens into one comparison pool,
        # but apply per-pair topic gating below.
        merged_groups: dict[str, list[tuple[int, InferenceClaim]]] = defaultdict(list)
        for (lens, _sig), group_items in groups.items():
            merged_groups[lens].extend(group_items)

        for lens, lens_claims in merged_groups.items():
            # Build topic-keyword index for this lens
            claim_kws: list[tuple[int, set[str], InferenceClaim]] = []
            for idx, claim in lens_claims:
                kws = set(self._extract_topic_signature(claim.claim).split("|"))
                kws.discard("")
                claim_kws.append((idx, kws, claim))

            n = len(claim_kws)
            for i_idx in range(n):
                _idx_i, kws_i, c1 = claim_kws[i_idx]
                for j_idx in range(i_idx + 1, n):
                    _idx_j, kws_j, c2 = claim_kws[j_idx]

                    # Gate 0: topic/workstream grouping
                    # If both have concrete keywords and they don't share
                    # any, skip — these are about completely different topics.
                    # "work" is excluded from _TOPIC_KEYWORDS to prevent
                    # false overlaps (workstream vs workout vs framework).
                    both_concrete = (
                        not any(k.startswith("fallback:") for k in kws_i)
                        and not any(k.startswith("fallback:") for k in kws_j)
                    )
                    if both_concrete and kws_i and kws_j and not (kws_i & kws_j):
                        arts1 = set(str(a) for a in c1.supporting_evidence[:5])
                        arts2 = set(str(a) for a in c2.supporting_evidence[:5])
                        if not (arts1 & arts2):
                            skipped_topic += 1
                            continue

                    # Gate 1: exact dedup by claim pair
                    pair_key = tuple(sorted([str(c1.id), str(c2.id)]))
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)

                    # Gate 2: triviality filter
                    overlap = self._word_overlap_ratio(c1.claim, c2.claim)
                    if overlap >= triviality_threshold:
                        skipped_trivial += 1
                        continue

                    # Gate 3: opposition marker must be in differing words
                    if not self._opposition_in_difference(c1.claim, c2.claim):
                        skipped_no_opposition += 1
                        continue

                    # Gate 4: strong opposition — semantic distance floor
                    distance = self._semantic_distance(c1.claim, c2.claim)
                    if distance < 0.30:
                        skipped_weak += 1
                        continue

                    # Gate 5: multi-factor severity calibration
                    severity = self._calibrate_severity(c1, c2, distance)

                    if severity == Severity.CRITICAL:
                        suggestion = (
                            "High-impact contradiction — review both claims and "
                            "resolve the conflict urgently"
                        )
                    elif severity == Severity.HIGH:
                        suggestion = (
                            "Resolve the contradiction or add context to explain "
                            "the apparent conflict"
                        )
                    elif severity == Severity.MEDIUM:
                        suggestion = (
                            "Moderate contradiction — review claims and consider "
                            "adding clarifying context"
                        )
                    else:
                        suggestion = (
                            "Minor wording divergence — consider aligning phrasing"
                        )

                    contradictions.append(Contradiction(
                        id=uuid4(),
                        category="claim_opposition",
                        description=f"'{c1.claim[:80]}' vs '{c2.claim[:80]}'",
                        claim_ids=[c1.id, c2.id],
                        artifact_ids=list(
                            set(list(c1.supporting_evidence)[:3]
                                + list(c2.supporting_evidence)[:3])
                        )[:5],
                        severity=severity,
                        audience_affected=[c1.audience_lens],
                        resolution_suggestion=suggestion,
                    ))

        # Gate 6: per-lens cap — keep top N by semantic distance
        lens_buckets: dict[str, list[Contradiction]] = defaultdict(list)
        for c in contradictions:
            lens_buckets[c.audience_affected[0]].append(c)

        capped: list[Contradiction] = []
        capped_count = 0
        for _lens_id, bucket in lens_buckets.items():
            bucket.sort(
                key=lambda c: self._semantic_distance(
                    *self._extract_texts_from_description(c.description)
                ),
                reverse=True,
            )
            if len(bucket) > max_per_lens:
                capped_count += len(bucket) - max_per_lens
                capped.extend(bucket[:max_per_lens])
            else:
                capped.extend(bucket)

        # Log filtering stats for observability
        if any([skipped_topic, skipped_trivial, skipped_no_opposition, skipped_weak, capped_count]):
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"Contradiction engine filtered: "
                f"{skipped_topic} cross-topic, "
                f"{skipped_trivial} trivial (>{triviality_threshold:.0%} overlap), "
                f"{skipped_no_opposition} no-opposition, "
                f"{skipped_weak} weak-semantic, "
                f"{capped_count} capped, "
                f"{len(capped)} retained "
                f"(from {len(claims)} claims across {len(merged_groups)} lenses)"
            )

        return capped

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
        raw.extend(self.find_audience_drift(claims, entities))
        raw.extend(self.find_evidence_conflicts(artifacts, claims))
        raw.extend(self.find_temporal_decay(artifacts))
        raw.extend(self.find_identity_fragmentation(entities))
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
