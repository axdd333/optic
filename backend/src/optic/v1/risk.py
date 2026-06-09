"""
Optic V1 — Risk Engine
======================
Dynamic risk generation from contradictions, stale context,
and exposure records. Replaces hardcoded risks with evidence-backed
RiskFlag objects derived from actual audit data.

Sources:
  A. Each contradiction → a risk (severity = contradiction severity)
  B. Stale artifacts (> 90 days old) → freshness risks
  C. High-confidence claims from sensitive lenses → exposure risks
  D. Workstream fragmentation → narrative fragmentation risk
  E. Low-confidence claims → missing proof risk
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from .models import (
    ConfidenceBand,
    RiskCategory,
    RiskFlag,
    Severity,
)

# ── Contradiction category → RiskCategory mapping ──────────────────

_CONTRADICTION_TO_RISK_MAP: Dict[str, RiskCategory] = {
    # New canonical categories
    "audience_drift": RiskCategory.AUDIENCE_MISMATCH,
    "evidence_conflict": RiskCategory.TIMELINE_GAP,
    "temporal_decay": RiskCategory.STALE_CONTEXT,
    "identity_fragmentation": RiskCategory.IDENTITY_MISMATCH,
    "claim_opposition": RiskCategory.NARRATIVE_FRAGMENTATION,
    # Legacy categories (backward compatibility)
    "job_title_mismatch": RiskCategory.IDENTITY_MISMATCH,
    "timeline_gap": RiskCategory.TIMELINE_GAP,
    "timeline_conflict": RiskCategory.TIMELINE_GAP,
    "stale_context": RiskCategory.STALE_CONTEXT,
    "profile_mismatch": RiskCategory.IDENTITY_MISMATCH,
}

# Lenses with risk_sensitivity >= 0.7 — HIGH-confidence claims from
# these lenses represent genuine exposure risk
_HIGH_RISK_LENSES: set = {"recruiter", "creator", "stranger", "privacy"}


# ── Helpers ────────────────────────────────────────────────────────

def _compute_file_age_days(file_path: str, now: datetime) -> Optional[int]:
    """Return age in days of a file on disk, or None if not stat-able."""
    try:
        p = Path(file_path)
        if not p.exists():
            return None
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        return (now - mtime).days
    except (OSError, ValueError):
        return None


def _map_contradiction_to_risk_category(contradiction_category: str) -> RiskCategory:
    """Map a contradiction category to the appropriate RiskCategory."""
    return _CONTRADICTION_TO_RISK_MAP.get(
        contradiction_category, RiskCategory.NARRATIVE_FRAGMENTATION
    )


def _coerce_list(value) -> list:
    """Coerce a value to a list, handling JSON-encoded strings."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except (json.JSONDecodeError, TypeError):
            return [value]
    return []


def _coerce_uuid(value) -> Optional[UUID]:
    """Coerce a value to UUID, returning None on failure."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError):
        return None


# ── Main engine ────────────────────────────────────────────────────

def risk_engine(
    contradictions: List[dict],
    claims: List[dict],
    artifacts: List[dict],
    workstream_cards: Optional[List[dict]] = None,
    now_iso: Optional[str] = None,
) -> List[RiskFlag]:
    """
    Generate RiskFlag objects from multiple evidence sources.

    Args:
        contradictions: Contradiction dicts from the audit pipeline.
        claims: Inference claim dicts from the audit pipeline.
        artifacts: Artifact dicts (with metadata.path for file age checks).
        workstream_cards: Optional workstream cluster metadata.
        now_iso: ISO timestamp for risk creation.

    Returns:
        List of RiskFlag objects (typically 5+ for a real audit).
    """
    if now_iso is None:
        now_iso = datetime.now(timezone.utc).isoformat()
    now = datetime.now(timezone.utc)
    risks: List[RiskFlag] = []
    seen_keys: set = set()  # dedup by (category, description[:80])

    workstream_cards = workstream_cards or []

    # ═══════════════════════════════════════════════════════════════
    # SOURCE A: Each contradiction → a RiskFlag
    # Severity comes directly from the contradiction's severity.
    # ═══════════════════════════════════════════════════════════════
    for cd in contradictions:
        cat = cd.get("category", "")
        risk_cat = _map_contradiction_to_risk_category(cat)
        desc = (cd.get("description") or cd.get("resolution_suggestion") or "")[:300]

        cids = _coerce_list(cd.get("claim_ids"))
        aids = _coerce_list(cd.get("artifact_ids"))
        aud = _coerce_list(cd.get("audience_affected"))

        sev_str = cd.get("severity", "low")
        try:
            sev = Severity(sev_str)
        except ValueError:
            sev = Severity.LOW

        dedup_key = f"{risk_cat.value}|{desc[:80]}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        risks.append(RiskFlag(
            id=uuid4(),
            category=risk_cat,
            description=desc,
            severity=sev,
            linked_claim_ids=[_coerce_uuid(c) for c in cids[:10] if _coerce_uuid(c)],
            linked_artifact_ids=[_coerce_uuid(a) for a in aids[:10] if _coerce_uuid(a)],
            audience_affected=aud,
            created_at=now_iso,
        ))

    # ═══════════════════════════════════════════════════════════════
    # SOURCE B: Stale context detection (artifacts > 90 days old)
    # Stats actual files on disk via metadata.path.
    # ═══════════════════════════════════════════════════════════════
    stale_count = 0
    for a in artifacts:
        meta = a.get("metadata") or {}
        file_path = meta.get("path") or ""
        if not file_path:
            continue

        age_days = _compute_file_age_days(file_path, now)
        if age_days is None:
            continue

        if age_days > 90:
            stale_count += 1
            aid = a.get("id", "")
            fname = Path(file_path).name
            aid_uuid = _coerce_uuid(aid)

            if age_days > 365:
                sev = Severity.HIGH
                desc = (
                    f"Stale artifact: '{fname}' is {age_days} days "
                    f"({age_days // 365}y) old — may misrepresent current activity"
                )
            elif age_days > 180:
                sev = Severity.MEDIUM
                desc = f"Stale artifact: '{fname}' is {age_days} days old — may appear outdated"
            else:
                sev = Severity.LOW
                desc = f"Aging artifact: '{fname}' is {age_days} days old — approaching staleness"

            dedup_key = f"stale_context|{fname}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            risks.append(RiskFlag(
                id=uuid4(),
                category=RiskCategory.STALE_CONTEXT,
                description=desc[:300],
                severity=sev,
                linked_artifact_ids=[aid_uuid] if aid_uuid else [],
                audience_affected=["stranger", "recruiter", "institution"],
                created_at=now_iso,
            ))

    # If no individual stale files detected, check workstream summaries
    # for stale content keywords
    if stale_count == 0 and workstream_cards:
        stale_keywords = {"archive", "legacy", "old", "deprecated", "inactive"}
        for card in workstream_cards[:3]:
            ws_name = card.get("name", "")
            summary = (card.get("summary") or "")[:200]
            if any(kw in summary.lower() for kw in stale_keywords):
                dedup_key = f"stale_context|ws:{ws_name}"
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    risks.append(RiskFlag(
                        id=uuid4(),
                        category=RiskCategory.STALE_CONTEXT,
                        description=(
                            f"Workstream '{ws_name}' contains potentially "
                            f"stale content: {summary[:120]}"
                        ),
                        severity=Severity.LOW,
                        audience_affected=["stranger", "recruiter"],
                        created_at=now_iso,
                    ))

    # ═══════════════════════════════════════════════════════════════
    # SOURCE C: Exposure risks from high-confidence claims on
    #           sensitive audience lenses (risk_sensitivity >= 0.7)
    # ═══════════════════════════════════════════════════════════════
    for claim in claims:
        lens_id = claim.get("audience_lens", "")
        conf = claim.get("confidence_band", "")
        claim_text = (claim.get("claim") or "")[:150]
        cid = claim.get("id", "")

        # Only flag HIGH-confidence claims on high-risk lenses
        if lens_id not in _HIGH_RISK_LENSES:
            continue
        if conf not in ("high", "HIGH"):
            continue

        dedup_key = f"overexposure|{lens_id}|{claim_text[:80]}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        cid_uuid = _coerce_uuid(cid)
        risks.append(RiskFlag(
            id=uuid4(),
            category=RiskCategory.OVEREXPOSURE,
            description=f"High-confidence exposure for {lens_id}: {claim_text}",
            severity=Severity.MEDIUM,
            linked_claim_ids=[cid_uuid] if cid_uuid else [],
            audience_affected=[lens_id],
            created_at=now_iso,
        ))

    # ═══════════════════════════════════════════════════════════════
    # SOURCE D: Workstream fragmentation → narrative risk
    # ═══════════════════════════════════════════════════════════════
    if len(workstream_cards) > 5:
        dedup_key = "narrative_fragmentation|workstream_count"
        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            sev = Severity.MEDIUM if len(workstream_cards) > 8 else Severity.LOW
            risks.append(RiskFlag(
                id=uuid4(),
                category=RiskCategory.NARRATIVE_FRAGMENTATION,
                description=(
                    f"High workstream fragmentation: {len(workstream_cards)} distinct "
                    f"clusters detected. May dilute narrative coherence for recruiters "
                    f"and collaborators."
                ),
                severity=sev,
                audience_affected=["recruiter", "collaborator", "investor"],
                created_at=now_iso,
            ))

    # ═══════════════════════════════════════════════════════════════
    # SOURCE E: Missing proof detection (claims with LOW confidence)
    # ═══════════════════════════════════════════════════════════════
    missing_proof_lenses: set = set()
    for claim in claims:
        conf = claim.get("confidence_band", "")
        if conf in ("low", "LOW"):
            lens = claim.get("audience_lens", "")
            if lens:
                missing_proof_lenses.add(lens)

    if missing_proof_lenses:
        dedup_key = "missing_proof|lenses"
        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            sorted_lenses = sorted(missing_proof_lenses)[:5]
            risks.append(RiskFlag(
                id=uuid4(),
                category=RiskCategory.MISSING_PROOF,
                description=(
                    f"Weak evidence for {len(missing_proof_lenses)} audience "
                    f"lens{'es' if len(missing_proof_lenses) != 1 else ''}: "
                    f"{', '.join(sorted_lenses)}. "
                    f"Add more sources to strengthen inferences."
                ),
                severity=Severity.MEDIUM,
                audience_affected=sorted_lenses,
                created_at=now_iso,
            ))

    # ═══════════════════════════════════════════════════════════════
    # Honest minimum: if < 3 risks total, add a truthful note
    # ═══════════════════════════════════════════════════════════════
    if len(risks) < 3:
        risks.append(RiskFlag(
            id=uuid4(),
            category=RiskCategory.MISSING_PROOF,
            description=(
                "Limited audit data available. Run a full file scan to enable "
                "comprehensive risk detection across all 23 risk categories."
            ),
            severity=Severity.LOW,
            audience_affected=["all"],
            created_at=now_iso,
        ))

    return risks
