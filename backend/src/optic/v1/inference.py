"""
Optic V1 — Inference Card Generator (v2: STRUCTURAL DEDUCTION)
===============================================================
Creates structured inference claims from signals, evidence, and audience lenses.
Every claim MUST cite specific evidence with real artifact IDs.
Every claim MUST be derived from actual signal data — NOT template-filled.

Doctrine: Invariants 3 (evidence-gated), 4 (confidence-banded), 15 (explicit over elegant).
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from .lenses import AUDIENCE_LENSES
from .models import (
    Artifact, AudienceLens, ConfidenceBand, EvidenceLink,
    InferenceClaim, Severity, Signal,
)


# ── Category → inherent risk weight (0.0–1.0) ─────────────────────
# Higher = more likely to produce real-world consequences for the user.
CATEGORY_RISK_WEIGHT: dict[str, float] = {
    "controversial_phrase": 0.90,
    "public_association": 0.85,
    "loaded_language": 0.80,
    "emotional_appeal": 0.75,
    "timeline_gap": 0.70,
    "inconsistent_title": 0.70,
    "stale_bio": 0.65,
    "unclear_credential": 0.65,
    "workstream_fragmentation": 0.60,
    "content_anomaly": 0.55,
    "frequent_topic": 0.40,
    "project_velocity": 0.30,
    "ai_ml_content": 0.35,
    "software_engineering": 0.30,
    "research_signals": 0.30,
}

# ── Severity → numeric weight ─────────────────────────────────────
SEVERITY_WEIGHT: dict[Severity, float] = {
    Severity.CRITICAL: 1.0,
    Severity.HIGH: 0.75,
    Severity.MEDIUM: 0.50,
    Severity.LOW: 0.25,
}


# ═══════════════════════════════════════════════════════════════════
# Structural deduction helpers
# ═══════════════════════════════════════════════════════════════════

def _a_an(text: str) -> str:
    """Return 'a' or 'an' based on the first word's initial sound."""
    if not text:
        return "a"
    first = text.lstrip().split()[0].lower()
    if first[0] in "aeiou":
        return "an"
    return "a"


def _A_An(text: str) -> str:
    """Capitalized variant of _a_an for sentence-start positions."""
    return _a_an(text).capitalize()


def _safe_meta(signal: Signal, key: str, default=None):
    """Safely extract a metadata value from a signal."""
    meta = signal.metadata or {}
    return meta.get(key, default)


def _artifact_by_id(artifacts: List[Artifact], aid: UUID) -> Optional[Artifact]:
    """Find an artifact by its UUID.""" 
    for a in artifacts:
        if a.id == aid:
            return a
    return None


def _artifact_type_label(artifacts: List[Artifact], aid: UUID) -> str:
    """Human-readable label for an artifact: 'PDF resume', 'Markdown note', etc."""
    a = _artifact_by_id(artifacts, aid)
    if not a:
        return f"artifact {str(aid)[:8]}"
    type_label = (a.type or "file").replace("_", " ").title()
    return type_label


def _artifact_date(artifact: Artifact) -> Optional[str]:
    """Extract a date string from an artifact's metadata."""
    return artifact.metadata.get("date") or artifact.metadata.get("created")


def _parse_date(ds: Optional[str]) -> Optional[datetime]:
    """Parse an ISO date string, returning None on failure. Always returns timezone-aware."""
    if not ds:
        return None
    try:
        s = str(ds).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _days_ago(ds: Optional[str]) -> Optional[int]:
    """How many days ago was this date string? None if unparseable."""
    dt = _parse_date(ds)
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).days


def _date_range_str(artifacts: List[Artifact]) -> Tuple[Optional[str], Optional[str]]:
    """Earliest and latest date strings from a list of artifacts."""
    dates = []
    for a in artifacts:
        d = _parse_date(_artifact_date(a))
        if d:
            dates.append(d)
    if not dates:
        return None, None
    dates.sort()
    return dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d")


def _source_type_diversity(artifacts: List[Artifact]) -> float:
    """0.0–1.0 score: how many DIFFERENT source types contribute evidence."""
    if not artifacts:
        return 0.0
    types = {a.type for a in artifacts if a.type}
    # Normalize: 1 type → 0.2, 5+ types → 1.0
    return min(1.0, len(types) / 5.0)


def _recency_penalty(artifacts: List[Artifact], max_age_days: int = 365) -> float:
    """0.0–1.0: penalty for stale evidence. 0 = all recent, 1 = all ancient."""
    if not artifacts:
        return 1.0
    penalties = []
    for a in artifacts:
        days = _days_ago(_artifact_date(a))
        if days is None:
            penalties.append(0.5)  # unknown = moderate penalty
        else:
            penalties.append(min(1.0, days / max_age_days))
    return sum(penalties) / len(penalties)


# ═══════════════════════════════════════════════════════════════════
# Structural claim builders — one per signal category
# ═══════════════════════════════════════════════════════════════════

def _deduce_frequent_topic(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    """Deduce a claim from topic frequency patterns in signal data."""
    ws_name = _safe_meta(signal, "workstream_name", _safe_meta(signal, "workstream_id", "unknown"))
    topics = _safe_meta(signal, "topics", [])
    file_count = _safe_meta(signal, "file_count", len(artifacts))
    cluster_confidence = _safe_meta(signal, "confidence", None)

    if not topics:
        return (
            f"{_A_An(lens.name)} {lens.name.lower()} examining your '{ws_name}' workstream "
            f"({file_count} files) may notice sustained activity but lack "
            f"topical specificity — making interpretation ambiguous."
        )

    top_three = topics[:3]
    topic_list = ", ".join(top_three)
    primary = top_three[0].replace("_", " ")

    if cluster_confidence is not None and cluster_confidence >= 0.7:
        return (
            f"Your '{ws_name}' workstream contains {file_count} files "
            f"spanning topics including {topic_list}. "
            f"{_A_An(lens.name)} {lens.name.lower()} may read this as sustained, high-confidence "
            f"investment in {primary}."
        )
    else:
        return (
            f"Your '{ws_name}' workstream spans {file_count} files "
            f"across {topic_list}. "
            f"{_A_An(lens.name)} {lens.name.lower()} may notice topical breadth but "
            f"the cluster confidence is {cluster_confidence:.0%} — "
            f"suggesting the focus may be less clear than the volume implies."
        )


def _deduce_project_velocity(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    """Deduce a claim about project velocity from signal metadata and artifact dates."""
    ws_name = _safe_meta(signal, "workstream_name", "unknown")
    file_count = _safe_meta(signal, "file_count", len(artifacts))
    confidence = _safe_meta(signal, "confidence", 0.5)

    earliest, latest = _date_range_str(artifacts)
    date_clause = ""
    if earliest and latest:
        date_clause = f" between {earliest} and {latest}"

    if confidence >= 0.85:
        return (
            f"Your '{ws_name}' workstream produced {file_count} files"
            f"{date_clause} with {confidence:.0%} cluster confidence. "
            f"{_A_An(lens.name)} {lens.name.lower()} may interpret this as high execution velocity "
            f"with strong topical coherence."
        )
    else:
        return (
            f"Your '{ws_name}' workstream generated {file_count} files"
            f"{date_clause}. "
            f"{_A_An(lens.name)} {lens.name.lower()} may see moderate output velocity, "
            f"though the cluster confidence ({confidence:.0%}) suggests some "
            f"topical scatter that could dilute the signal."
        )


def _deduce_workstream_fragmentation(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    """Deduce a claim about fragmented/scattered work."""
    ws_name = _safe_meta(signal, "workstream_name", "unknown")
    file_count = _safe_meta(signal, "file_count", len(artifacts))
    confidence = _safe_meta(signal, "confidence", 0.3)

    return (
        f"Your '{ws_name}' workstream contains {file_count} files but clusters "
        f"at only {confidence:.0%} confidence. "
        f"{_A_An(lens.name)} {lens.name.lower()} may interpret this as scattered effort "
        f"across loosely related topics rather than focused execution. "
        f"Without clearer grouping, the signal for {lens.priorities[0].replace('_', ' ')} "
        f"may be diluted."
    )


def _deduce_detector_signal(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact],
    detected_attr: str, interpretation: str,
) -> str:
    """Shared structural deduction for detector-based signals (ai_ml, swe, research, etc.)."""
    ws_name = _safe_meta(signal, "workstream_name", "unknown")
    detection_count = _safe_meta(signal, "detection_count", 0)
    evidence_labels = _safe_meta(signal, "evidence_labels", [])
    file_count = _safe_meta(signal, "file_count", len(artifacts))

    evidence_clause = ""
    if evidence_labels:
        samples = evidence_labels[:3]
        evidence_clause = f"Evidence includes: {'; '.join(samples)}. "

    return (
        f"Content detectors found {detection_count} {detected_attr} patterns "
        f"across {file_count} files in your '{ws_name}' workstream. "
        f"{evidence_clause}"
        f"{_A_An(lens.name)} {lens.name.lower()} may interpret this as {interpretation}."
    )


def _deduce_loaded_language(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    ws_name = _safe_meta(signal, "workstream_name", "unknown")
    detection_count = _safe_meta(signal, "detection_count", 0)
    evidence_labels = _safe_meta(signal, "evidence_labels", [])

    evidence_clause = ""
    if evidence_labels:
        samples = evidence_labels[:3]
        evidence_clause = f"Samples include: {'; '.join(samples)}. "

    return (
        f"Signal detectors flagged {detection_count} instances of loaded or "
        f"emotionally charged language in your '{ws_name}' content. "
        f"{evidence_clause}"
        f"{_A_An(lens.name)} {lens.name.lower()} scanning this content may register heightened "
        f"emotional tone, which could be read as passionate engagement or as "
        f"potential bias depending on context."
    )


def _deduce_emotional_appeal(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    ws_name = _safe_meta(signal, "workstream_name", "unknown")
    detection_count = _safe_meta(signal, "detection_count", 0)
    evidence_labels = _safe_meta(signal, "evidence_labels", [])

    evidence_clause = ""
    if evidence_labels:
        samples = evidence_labels[:3]
        evidence_clause = f"Examples: {'; '.join(samples)}. "

    return (
        f"Detectors found {detection_count} emotional-appeal patterns "
        f"in your '{ws_name}' content. "
        f"{evidence_clause}"
        f"{_A_An(lens.name)} {lens.name.lower()} may read this as persuasive writing or, "
        f"alternatively, as content that prioritizes emotional resonance "
        f"over factual grounding — the interpretation depends on the "
        f"specific contexts cited."
    )


def _deduce_content_anomaly(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    ws_name = _safe_meta(signal, "workstream_name", "unknown")
    detection_count = _safe_meta(signal, "detection_count", 0)
    evidence_labels = _safe_meta(signal, "evidence_labels", [])

    anomaly_type = "structural irregularity"
    if detection_count > 10:
        anomaly_type = "repeated structural irregularity"
    elif detection_count > 3:
        anomaly_type = "noticeable structural pattern"

    evidence_clause = ""
    if evidence_labels:
        samples = evidence_labels[:2]
        evidence_clause = f" (e.g., {', '.join(samples)})"

    return (
        f"Content analysis detected {detection_count} instances of "
        f"{anomaly_type} in your '{ws_name}' workstream"
        f"{evidence_clause}. "
        f"{_A_An(lens.name)} {lens.name.lower()} reviewing this content may note formatting "
        f"or structural inconsistencies that could distract from the "
        f"substance."
    )


def _deduce_timeline_gap(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    """Deduce a claim about a timeline gap using actual artifact dates."""
    gap_days = _safe_meta(signal, "gap_days")
    gap_months = _safe_meta(signal, "gap_months")

    # If metadata carried explicit gap info, use it
    if gap_days is not None:
        gap_text = f"{gap_days} days"
        if gap_months is not None and gap_months >= 1:
            gap_text = f"approximately {gap_months} month{'s' if gap_months != 1 else ''}"
        domain = _safe_meta(signal, "domain", "professional activity")
        return (
            f"Evidence shows a {gap_text} gap in {domain}. "
            f"{_A_An(lens.name)} {lens.name.lower()} may question this discontinuity "
            f"in your timeline, especially if it spans a period where "
            f"continuity is expected."
        )

    # Otherwise, derive from artifacts
    if len(artifacts) >= 2:
        earliest, latest = _date_range_str(artifacts)
        if earliest and latest:
            return (
                f"Your evidence artifacts span {earliest} to {latest}. "
                f"{_A_An(lens.name)} {lens.name.lower()} may notice this range and, if "
                f"significant gaps exist within it, question what occurred "
                f"in the unrepresented periods."
            )

    # Fallback: use signal description but add structural context
    return (
        f"{_A_An(lens.name)} {lens.name.lower()} may question the {signal.description} "
        f"gap in your timeline. Without dated artifacts to anchor "
        f"this period, the reading remains hypothetical — "
        f"this is an inference from absence, not presence."
    )


def _deduce_stale_bio(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    """Deduce claim about stale biographical content using artifact age."""
    # Find the artifact that triggered this signal
    stale_artifact = None
    for a in artifacts:
        if a.id in signal.source_artifact_ids:
            stale_artifact = a
            break

    age_days = None
    age_str = "unknown age"
    if stale_artifact:
        age_days = _days_ago(_artifact_date(stale_artifact))
        if age_days is not None:
            if age_days > 730:
                age_str = f"over {age_days // 365} years old"
            elif age_days > 365:
                age_str = f"over a year old ({age_days} days)"
            elif age_days > 90:
                age_str = f"{age_days} days old"
            else:
                age_str = f"{age_days} days old (recent but may still be outdated)"

    artifact_label = "bio/profile content"
    if stale_artifact:
        artifact_label = _artifact_type_label(artifacts, stale_artifact.id)

    return (
        f"Your {artifact_label} is {age_str}. "
        f"{_A_An(lens.name)} {lens.name.lower()} may read this as outdated context that "
        f"no longer reflects your current situation. "
        f"Stale self-descriptions can create a gap between who you are "
        f"now and who the evidence presents."
    )


def _deduce_inconsistent_title(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    """Deduce claim about inconsistent titles/roles across sources."""
    titles = _safe_meta(signal, "titles", [])
    source_count = _safe_meta(signal, "source_count", 0) or len(artifacts)

    if titles and len(titles) >= 2:
        title_list = ", ".join(f'"{t}"' for t in titles[:3])
        return (
            f"Title varies across {source_count} sources: {title_list}. "
            f"{_A_An(lens.name)} {lens.name.lower()} may find this inconsistency in "
            f"professional self-presentation notable. It could signal "
            f"role evolution, platform-specific tailoring, or misalignment "
            f"that a reader cannot distinguish without additional context."
        )
    else:
        return (
            f"{_A_An(lens.name)} {lens.name.lower()} may find your {signal.description} "
            f"inconsistent across platforms. Without explicit alignment, "
            f"this variation creates ambiguity about your current role."
        )


def _deduce_public_association(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    """Deduce claim about public associations from entity extraction."""
    entity = _safe_meta(signal, "entity_name", signal.description)
    association_count = _safe_meta(signal, "association_count", len(artifacts))
    context = _safe_meta(signal, "association_context", "public references")

    # Extract specific artifact references
    evidence_refs = []
    for a in artifacts[:3]:
        label = _artifact_type_label(artifacts, a.id)
        evidence_refs.append(label)
    evidence_list = ", ".join(evidence_refs) if evidence_refs else "multiple sources"

    return (
        f"Your digital footprint references '{entity}' in "
        f"{association_count} contexts ({evidence_list}). "
        f"{_A_An(lens.name)} {lens.name.lower()} may associate you with {entity} based on "
        f"{context}. The strength of this association depends on the "
        f"nature of the references — proximity, endorsement, or mere "
        f"mention carry different weights."
    )


def _deduce_controversial_phrase(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    """Deduce claim about potentially controversial content with specific citation."""
    phrase = _safe_meta(signal, "flagged_phrase", signal.description)
    context = _safe_meta(signal, "flag_context", "public content")

    # Find the artifact containing this phrase
    source_ref = "an artifact"
    for a in artifacts:
        if a.id in signal.source_artifact_ids:
            source_ref = _artifact_type_label(artifacts, a.id)
            break

    return (
        f"The content '{phrase}' in {source_ref} may be flagged by a "
        f"{lens.name.lower()} as potentially sensitive or controversial "
        f"in the context of {context}. "
        f"This is a surface reading — intent and context that are obvious "
        f"to you may not be visible to an outside reader."
    )


def _deduce_unclear_credential(
    signal: Signal, lens: AudienceLens, artifacts: List[Artifact]
) -> str:
    """Deduce claim about unclear or unverifiable credentials."""
    credential_type = _safe_meta(signal, "credential_type", "credential")
    source_label = _safe_meta(signal, "credential_source", "your profile")
    ambiguity = _safe_meta(signal, "ambiguity_detail", "lacks verification context")

    return (
        f"Your {credential_type} at {source_label} {ambiguity}. "
        f"{_A_An(lens.name)} {lens.name.lower()} may find this unclear or unverified. "
        f"Without corroborating evidence — such as dates, issuing body, "
        f"or verifiable references — this credential may carry less "
        f"weight than it deserves."
    )


# ── Category → deduction function map ──────────────────────────────
DEDUCTION_MAP: dict[str, callable] = {
    "frequent_topic": _deduce_frequent_topic,
    "project_velocity": _deduce_project_velocity,
    "workstream_fragmentation": _deduce_workstream_fragmentation,
    "ai_ml_content": lambda s, l, a: _deduce_detector_signal(
        s, l, a, "AI/ML", "meaningful engagement with artificial intelligence and machine learning topics"
    ),
    "software_engineering": lambda s, l, a: _deduce_detector_signal(
        s, l, a, "software engineering", "active technical development work"
    ),
    "research_signals": lambda s, l, a: _deduce_detector_signal(
        s, l, a, "research", "sustained research activity or academic engagement"
    ),
    "loaded_language": _deduce_loaded_language,
    "emotional_appeal": _deduce_emotional_appeal,
    "content_anomaly": _deduce_content_anomaly,
    "timeline_gap": _deduce_timeline_gap,
    "stale_bio": _deduce_stale_bio,
    "inconsistent_title": _deduce_inconsistent_title,
    "public_association": _deduce_public_association,
    "controversial_phrase": _deduce_controversial_phrase,
    "unclear_credential": _deduce_unclear_credential,
}


# ═══════════════════════════════════════════════════════════════════
# InferenceCardGenerator — rewritten with structural deduction
# ═══════════════════════════════════════════════════════════════════

class InferenceCardGenerator:
    """Generates structurally-deduced inference claims for a specific audience lens.

    Every claim is built from actual signal data (topics, detection counts,
    evidence labels, artifact IDs, dates) — NOT from string templates.
    """

    def __init__(self, lens_id: str):
        self.lens = AUDIENCE_LENSES.get(lens_id)
        if not self.lens:
            raise ValueError(f"Unknown audience lens: {lens_id}")

    # ── Public API ─────────────────────────────────────────────────

    def generate_claims(
        self,
        signals: List[Signal],
        artifacts: List[Artifact],
        existing_claims: Optional[List[InferenceClaim]] = None,
    ) -> List[InferenceClaim]:
        """Generate inference claims from signals for this audience lens."""
        claims = []
        existing_claims = existing_claims or []

        for signal in signals:
            claim = self._signal_to_claim(signal, artifacts)
            if claim and self._passes_lens_filter(claim):
                claim = self._add_counterargument(claim, artifacts, existing_claims)
                claims.append(claim)

        return self._sort_by_impact(claims)

    # ── Private: signal → claim conversion ──────────────────────────

    def _signal_to_claim(
        self,
        signal: Signal,
        artifacts: List[Artifact],
    ) -> Optional[InferenceClaim]:
        """Convert a signal into a structurally-deduced inference claim."""
        # Find artifacts relevant to this signal
        relevant_artifacts = [
            a for a in artifacts if a.id in signal.source_artifact_ids
        ]

        evidence_count = len(relevant_artifacts)
        if evidence_count < self.lens.confidence_rules.get("min_evidence_count", 1):
            return None

        # Structural deduction: build claim text from signal data
        claim_text = self._deduce_claim(signal, relevant_artifacts)

        # Multi-factor confidence computation
        confidence = self._compute_confidence(signal, relevant_artifacts)

        # Evidence: supporting = relevant artifacts, weakening = found structurally
        supporting = [a.id for a in relevant_artifacts]
        weakening = self._find_weakening_evidence(signal, artifacts)

        # Recency: computed from artifact dates
        recency = self._compute_recency(relevant_artifacts)

        # Actionability: structural rules
        actionability = self._compute_actionability(signal)

        # Consequence: derived from severity × lens × category
        consequence = self._predict_consequence(signal, self.lens)

        return InferenceClaim(
            id=uuid4(),
            title=f"{self.lens.name}: {signal.category.replace('_', ' ').title()}",
            audience_lens=self.lens.id,
            claim=claim_text,
            confidence_band=confidence,
            evidence_count=evidence_count,
            supporting_evidence=supporting,
            weakening_evidence=weakening[:3],
            source_gaps=self._identify_source_gaps(signal),
            recency=recency,
            severity=signal.severity,
            actionability=actionability,
            possible_consequence=consequence,
            counterargument="",  # filled by _add_counterargument
            repair_options=[],
            model_version="optic-v2-structural",
            not_a_verdict=True,
        )

    # ── Structural claim deduction ─────────────────────────────────

    def _deduce_claim(
        self, signal: Signal, artifacts: List[Artifact]
    ) -> str:
        """Build a claim from structural deduction on signal data.

        Routes to a category-specific deduction function that extracts
        concrete data points (topics, detection counts, evidence labels,
        artifact IDs, dates) and constructs a specific claim.
        """
        deduction_fn = DEDUCTION_MAP.get(signal.category)

        if deduction_fn:
            return deduction_fn(signal, self.lens, artifacts)

        # Unknown category: describe what we DO know structurally
        artifact_ids = [str(aid)[:8] for aid in signal.source_artifact_ids[:5]]
        artifacts_ref = ", ".join(artifact_ids) if artifact_ids else "unknown sources"

        return (
            f"A {self.lens.name.lower()} analyzing {len(artifacts)} "
            f"artifacts ({artifacts_ref}) may interpret "
            f"'{signal.description}' as a {signal.severity.value}-severity signal. "
            f"Category '{signal.category}' is not yet modeled for structural "
            f"deduction — this claim is derived from available signal metadata."
        )

    # ── Multi-factor confidence ─────────────────────────────────────

    def _compute_confidence(
        self,
        signal: Signal,
        artifacts: List[Artifact],
    ) -> ConfidenceBand:
        """Compute confidence band using MULTIPLE structural factors.

        Factors:
        1. Evidence count (base score)
        2. Evidence source diversity (bonus)
        3. Recency (penalty for stale)
        4. Signal severity (higher severity needs more evidence for high conf)
        5. Lens-specific rules
        """
        rules = self.lens.confidence_rules
        min_evidence = rules.get("min_evidence_count", 2)
        count = len(artifacts)

        # Base: evidence count score (0.0–1.0)
        if count >= min_evidence * 3:
            base = 0.90
        elif count >= min_evidence * 2:
            base = 0.70
        elif count >= min_evidence:
            base = 0.50
        else:
            base = 0.30

        # Diversity bonus: multiple source types strengthen confidence
        diversity = _source_type_diversity(artifacts)
        base = min(1.0, base + diversity * 0.15)

        # Recency penalty: stale evidence weakens confidence
        max_age = rules.get("max_recency_days", 365)
        recency_p = _recency_penalty(artifacts, max_age)
        base = base * (1.0 - recency_p * 0.4)

        # Severity modifier: CRITICAL signals need more evidence to claim high confidence
        if signal.severity == Severity.CRITICAL and base < 0.60:
            base = 0.35  # downgrade: not enough evidence for critical claim
        elif signal.severity == Severity.HIGH and base < 0.50:
            base = 0.30

        # Lens-specific downgrades
        if rules.get("downgrade_for_contradictions") and signal.metadata.get("has_contradiction"):
            base *= 0.7

        # Map to band
        if base >= 0.70:
            return ConfidenceBand.HIGH
        elif base >= 0.40:
            return ConfidenceBand.MEDIUM
        return ConfidenceBand.LOW

    # ── Structural counterargument ──────────────────────────────────

    def _add_counterargument(
        self,
        claim: InferenceClaim,
        artifacts: List[Artifact],
        existing_claims: List[InferenceClaim],
    ) -> InferenceClaim:
        """Generate a counterargument rooted in actual evidence.

        Structural approach:
        1. If weakening evidence exists, cite it specifically by type
        2. If source gaps exist, describe what evidence is MISSING
        3. If alternative claims exist for same lens, reference them
        4. Otherwise: state the evidential limitation honestly
        """
        # Find weakening artifacts with labels
        weakening = [
            a for a in artifacts
            if a.id in claim.weakening_evidence
        ]

        # Find contradictory claims for the same lens
        conflicting_claims = [
            c for c in existing_claims
            if c.audience_lens == claim.audience_lens
            and c.id != claim.id
            and c.confidence_band in (ConfidenceBand.MEDIUM, ConfidenceBand.HIGH)
        ]

        parts: list[str] = []

        # 1. Cite specific weakening evidence
        if weakening:
            w_labels = [
                f"{_artifact_type_label(artifacts, w.id)}"
                for w in weakening[:2]
            ]
            parts.append(
                f"However, {len(weakening)} source{'s' if len(weakening) != 1 else ''} "
                f"({', '.join(w_labels)}) provide context that may weaken this reading."
            )

        # 2. Describe missing evidence
        if claim.source_gaps:
            gap_desc = claim.source_gaps[0].lower()
            parts.append(
                f"No {gap_desc} is available — this reading is based solely on "
                f"the {claim.evidence_count} source{'s' if claim.evidence_count != 1 else ''} "
                f"currently imported."
            )

        # 3. Reference conflicting claims
        if conflicting_claims and not weakening:
            conflict_count = min(len(conflicting_claims), 3)
            conflict_titles = [c.title for c in conflicting_claims[:3]]
            parts.append(
                f"Alternative readings exist: {', '.join(conflict_titles)}. "
                f"Consider these for a more complete picture."
            )

        # 4. Honest fallback
        if not parts:
            parts.append(
                f"No directly contradictory evidence was found in the "
                f"{claim.evidence_count} source{'s' if claim.evidence_count != 1 else ''} "
                f"examined. This reading is a hypothesis derived from available "
                f"signals — additional sources may change or weaken this "
                f"interpretation. Not a verdict."
            )

        claim.counterargument = " ".join(parts)
        return claim

    # ── Supporting methods ──────────────────────────────────────────

    def _passes_lens_filter(self, claim: InferenceClaim) -> bool:
        """Check if the claim passes the lens's forbidden output rules."""
        claim_lower = claim.claim.lower()
        for forbidden in self.lens.forbidden_outputs:
            if forbidden.lower() in claim_lower:
                return False
        return True

    def _find_weakening_evidence(
        self,
        signal: Signal,
        artifacts: List[Artifact],
    ) -> List[UUID]:
        """Find artifacts that may structurally weaken the signal.

        Strategy:
        - Artifacts of a DIFFERENT type from the same time period
        - Artifacts that are significantly more recent (context has changed)
        - Artifacts from a different workstream that touch the same topic
        """
        weakening = []
        signal_artifact_ids = set(signal.source_artifact_ids)

        for a in artifacts:
            if a.id in signal_artifact_ids:
                continue

            # Different type, same time period = alternative context
            if self._is_relevant_alternative(a, signal):
                weakening.append(a.id)

        return weakening

    def _is_relevant_alternative(
        self,
        artifact: Artifact,
        signal: Signal,
    ) -> bool:
        """Check if an artifact provides alternative context for a signal."""
        # Same time period but different artifact type
        signal_dates = signal.metadata.get("artifact_dates", {})
        artifact_date = _artifact_date(artifact)

        if artifact_date and signal_dates:
            for sd in signal_dates.values():
                if sd:
                    try:
                        days_diff = abs(_date_diff(artifact_date, str(sd)))
                        if days_diff < 90:
                            return True
                    except (ValueError, TypeError):
                        pass

        # Also flag recent artifacts that supersede stale ones
        if signal.category in ("stale_bio", "timeline_gap", "inconsistent_title"):
            age = _days_ago(artifact_date)
            if age is not None and age < 30:
                return True

        return False

    def _identify_source_gaps(self, signal: Signal) -> List[str]:
        """Identify what kinds of evidence sources are missing.

        Typesafe: compares against known SourceType values from lens preferences.
        """
        gaps = []
        present_types = set()

        # Collect present source types from metadata
        signal_source_types = signal.metadata.get("source_types", [])
        if isinstance(signal_source_types, list):
            present_types = {str(t).lower() for t in signal_source_types}
        elif isinstance(signal_source_types, str):
            present_types = {signal_source_types.lower()}

        for preferred in self.lens.evidence_preferences:
            if preferred.lower() not in present_types:
                gaps.append(f"Missing {preferred.replace('_', ' ')} evidence")

        return gaps[:3]

    def _compute_recency(self, artifacts: List[Artifact]) -> str:
        """Determine recency of the evidence from artifact dates."""
        if not artifacts:
            return "unknown"

        now = datetime.now(timezone.utc)
        ages: list[int] = []
        for a in artifacts:
            dt = _parse_date(_artifact_date(a))
            if dt is not None:
                ages.append((now - dt).days)

        if not ages:
            return "unknown"

        avg_age = sum(ages) / len(ages)
        if avg_age < 90:
            return "recent"
        elif avg_age < 365:
            return "mixed"
        return "stale"

    def _compute_actionability(self, signal: Signal) -> str:
        """Compute actionability from signal category — structural rules."""
        actionable_categories = {
            "stale_bio", "inconsistent_title", "old_username",
            "public_metadata", "missing_proof", "credential_ambiguity",
            "timeline_gap", "controversial_phrase", "loaded_language",
            "unclear_credential",
        }
        medium_categories = {
            "public_association", "workstream_fragmentation",
            "content_anomaly", "emotional_appeal",
        }
        if signal.category in actionable_categories:
            return "high"
        elif signal.category in medium_categories:
            return "medium"
        return "low"

    def _predict_consequence(
        self,
        signal: Signal,
        lens: AudienceLens,
    ) -> str:
        """Predict possible consequence using STRUCTURAL deduction.

        Computed as: severity_weight × lens.risk_sensitivity × category_risk_weight.

        This produces a risk_score (0.0–1.0) that maps to a consequence tier
        with a concrete prediction specific to the lens and signal.
        """
        cat_risk = CATEGORY_RISK_WEIGHT.get(signal.category, 0.40)
        sev_weight = SEVERITY_WEIGHT.get(signal.severity, 0.25)
        risk_score = sev_weight * lens.risk_sensitivity * cat_risk

        # Lens-specific consequence framing
        LENS_FRAMING: dict[str, str] = {
            "recruiter": "May affect hiring decisions or role-fit assessment",
            "investor": "May affect funding decisions or trust assessment",
            "collaborator": "May affect team formation or partnership decisions",
            "creator": "May affect audience trust or brand perception",
            "privacy": "May expand exposure surface or enable data-broker profiling",
            "platform": "May affect algorithmic categorization or ad targeting",
            "search": "May affect search-result appearance or public discoverability",
            "institution": "May affect application review or credential verification",
            "stranger": "May shape first impression from public fragments",
        }
        framing = LENS_FRAMING.get(lens.id, "May affect how this audience perceives you")

        # Severity-specific consequence banding
        if signal.severity == Severity.CRITICAL:
            return f"High likelihood: {framing}. Immediate review recommended."
        elif risk_score >= 0.60:
            return f"Moderate-to-high likelihood: {framing}."
        elif risk_score >= 0.30:
            return f"Moderate likelihood: {framing}. Context-dependent."
        else:
            return f"Low likelihood: {framing}. May be negligible in practice."

    @staticmethod
    def _sort_by_impact(claims: List[InferenceClaim]) -> List[InferenceClaim]:
        """Sort claims by severity then confidence."""
        severity_order = {
            Severity.CRITICAL: 0, Severity.HIGH: 1,
            Severity.MEDIUM: 2, Severity.LOW: 3,
        }
        confidence_order = {
            ConfidenceBand.HIGH: 0, ConfidenceBand.MEDIUM: 1, ConfidenceBand.LOW: 2,
        }
        return sorted(
            claims,
            key=lambda c: (
                severity_order.get(c.severity, 3),
                confidence_order.get(c.confidence_band, 2),
            )
        )


# ── Module-level utility ───────────────────────────────────────────
@staticmethod
def _date_diff(d1: str, d2: str) -> int:
    """Difference in days between two ISO date strings."""
    try:
        dt1 = datetime.fromisoformat(d1.replace("Z", "+00:00"))
        dt2 = datetime.fromisoformat(d2.replace("Z", "+00:00"))
        return abs((dt1 - dt2).days)
    except (ValueError, TypeError):
        return 999
