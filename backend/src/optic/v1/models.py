"""
Optic V1 — Canonical Data Models
=================================
Every inference must cite evidence. Every inference must expose uncertainty.
Every inference must show counterarguments. No universal identity score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════

class AuditMode(str, Enum):
    FOUNDER = "founder"
    CAREER = "career"
    STUDENT = "student"
    CREATOR = "creator"
    PRIVACY = "privacy"
    GENERAL = "general"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConfidenceBand(str, Enum):
    LOW = "low"         # plausible but weak, show as hypothesis
    MEDIUM = "medium"   # supported by multiple signals, caveated
    HIGH = "high"       # strongly supported, still not identity truth


class RiskCategory(str, Enum):
    STALE_CONTEXT = "stale_context"
    IDENTITY_MISMATCH = "identity_mismatch"
    TIMELINE_GAP = "timeline_gap"
    PROFESSIONAL_INCOHERENCE = "professional_incoherence"
    OVEREXPOSURE = "overexposure"
    SENSITIVE_INFERENCE = "sensitive_inference"
    LOCATION_LEAKAGE = "location_leakage"
    FINANCIAL_SIGNAL = "financial_signal"
    HEALTH_INFERENCE = "health_inference"
    POLITICAL_INFERENCE = "political_inference"
    CONTROVERSY_SURFACE = "controversy_surface"
    ASSOCIATION_RISK = "association_risk"
    SEARCH_CONTAMINATION = "search_contamination"
    IMPERSONATION_RISK = "impersonation_risk"
    DEAD_PROFILE = "dead_profile"
    UNCLAIMED_PROFILE = "unclaimed_profile"
    PLATFORM_BUCKET = "platform_bucket"
    AUDIENCE_MISMATCH = "audience_mismatch"
    TONE_MISMATCH = "tone_mismatch"
    MISSING_PROOF = "missing_proof"
    OLD_USERNAME = "old_username"
    PUBLIC_METADATA = "public_metadata"
    CREDENTIAL_AMBIGUITY = "credential_ambiguity"
    NARRATIVE_FRAGMENTATION = "narrative_fragmentation"
    MACHINE_SUMMARY_DISTORTION = "machine_summary_distortion"


class SourceType(str, Enum):
    URL = "url"
    HANDLE = "handle"
    FILE_UPLOAD = "file_upload"
    LINKEDIN_PROFILE = "linkedin_profile"
    GITHUB = "github"
    RESUME_PDF = "resume_pdf"
    X_ARCHIVE = "x_archive"
    GOOGLE_TAKEOUT = "google_takeout"
    META_EXPORT = "meta_export"
    INSTAGRAM_EXPORT = "instagram_export"
    TIKTOK_EXPORT = "tiktok_export"
    REDDIT_ARCHIVE = "reddit_archive"
    DISCORD_EXPORT = "discord_export"
    BROWSER_HISTORY = "browser_history"
    LOCAL_FOLDER = "local_folder"
    GMAIL_MBOX = "gmail_mbox"
    CALENDAR_ICS = "calendar_ics"
    SEARCH_RESULT = "search_result"
    SCREENSHOT = "screenshot"
    MANUAL_NOTE = "manual_note"


class SourceStatus(str, Enum):
    PENDING = "pending"
    IMPORTING = "importing"
    PARSING = "parsing"
    READY = "ready"
    FAILED = "failed"
    REVOKED = "revoked"


class RepairStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"
    REVERTED = "reverted"


# ═══════════════════════════════════════════════════════════════════
# Core Data Models
# ═══════════════════════════════════════════════════════════════════

@dataclass
class User:
    """The subject. V1 is user-side only."""
    id: UUID = field(default_factory=uuid4)
    email: str = ""
    settings: Dict[str, Any] = field(default_factory=dict)
    local_mode: bool = True  # default: local-first
    encryption_key_ref: str = ""  # reference to key, never stored
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ConsentReceipt:
    """Permission boundary for every source. Core invariant #2."""
    id: UUID = field(default_factory=uuid4)
    source_id: UUID = field(default_factory=uuid4)
    scope: List[str] = field(default_factory=list)  # ["parse", "embed", "infer", "export"]
    purpose: str = ""  # why this source is included
    retention_days: int = 90
    cloud_allowed: bool = False
    export_allowed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    revoked_at: Optional[str] = None


@dataclass
class Source:
    """A data source that feeds into the audit."""
    id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)
    type: SourceType = SourceType.URL
    provider: str = ""  # "linkedin", "github", "x", etc.
    import_method: str = ""  # "api", "upload", "url", "handle"
    user_label: str = ""  # human-readable name
    permission_scope: List[str] = field(default_factory=list)
    freshness: str = ""  # "recent", "stale", "archived"
    status: SourceStatus = SourceStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Artifact:
    """A raw unit of evidence."""
    id: UUID = field(default_factory=uuid4)
    source_id: UUID = field(default_factory=uuid4)
    type: str = ""  # "tweet", "post", "email", "pdf", "image", etc.
    raw_hash: str = ""  # sha256 of raw content
    encrypted_path: str = ""  # path to encrypted blob
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_public: bool = False
    content_preview: str = ""  # truncated preview, never full content in metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ParsedSpan:
    """Extracted text span or media feature with pointer to artifact."""
    id: UUID = field(default_factory=uuid4)
    artifact_id: UUID = field(default_factory=uuid4)
    text: str = ""
    language: str = "en"
    offset_start: int = 0
    offset_end: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


@dataclass
class Entity:
    """A person, account, org, project, or other identifiable thing."""
    id: UUID = field(default_factory=uuid4)
    type: str = ""  # "person", "account", "org", "school", "employer", "project", etc.
    name: str = ""
    canonical_handle: str = ""
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class Signal:
    """Low-level interpreted feature from artifacts."""
    id: UUID = field(default_factory=uuid4)
    category: str = ""  # "frequent_topic", "timeline_gap", "stale_bio", etc.
    description: str = ""
    severity: Severity = Severity.LOW
    source_artifact_ids: List[UUID] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class InferenceClaim:
    """A reading generated from signals for a specific audience."""
    id: UUID = field(default_factory=uuid4)
    title: str = ""
    audience_lens: str = ""  # "recruiter", "investor", etc.
    claim: str = ""
    confidence_band: ConfidenceBand = ConfidenceBand.LOW
    evidence_count: int = 0
    supporting_evidence: List[UUID] = field(default_factory=list)
    weakening_evidence: List[UUID] = field(default_factory=list)
    source_gaps: List[str] = field(default_factory=list)
    recency: str = ""  # "recent", "stale", "mixed"
    severity: Severity = Severity.LOW
    actionability: str = ""  # "high", "medium", "low"
    possible_consequence: str = ""
    counterargument: str = ""
    repair_options: List[UUID] = field(default_factory=list)
    model_version: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    not_a_verdict: bool = True  # always True


@dataclass
class EvidenceLink:
    """Links a claim to supporting or weakening evidence."""
    id: UUID = field(default_factory=uuid4)
    claim_id: UUID = field(default_factory=uuid4)
    artifact_id: UUID = field(default_factory=uuid4)
    span_id: Optional[UUID] = None
    quote: str = ""
    contribution_weight: float = 0.5  # 0.0–1.0
    polarity: str = "supporting"  # "supporting" or "weakening"


@dataclass
class Contradiction:
    """A conflict between claims, profiles, or evidence."""
    id: UUID = field(default_factory=uuid4)
    category: str = ""  # "job_title_mismatch", "timeline_conflict", etc.
    description: str = ""
    claim_ids: List[UUID] = field(default_factory=list)
    artifact_ids: List[UUID] = field(default_factory=list)
    severity: Severity = Severity.LOW
    audience_affected: List[str] = field(default_factory=list)
    resolution_suggestion: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RiskFlag:
    """A specific risk item for the user's profile."""
    id: UUID = field(default_factory=uuid4)
    category: RiskCategory = RiskCategory.STALE_CONTEXT
    description: str = ""
    severity: Severity = Severity.LOW
    linked_claim_ids: List[UUID] = field(default_factory=list)
    linked_artifact_ids: List[UUID] = field(default_factory=list)
    audience_affected: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RepairAction:
    """A concrete action the user can take to improve their signal."""
    id: UUID = field(default_factory=uuid4)
    title: str = ""
    affected_audience: List[str] = field(default_factory=list)
    linked_claim_id: Optional[UUID] = None
    linked_evidence_ids: List[UUID] = field(default_factory=list)
    impact: float = 0.5       # 0.0–1.0
    effort: float = 0.5       # 0.0–1.0
    urgency: float = 0.5      # 0.0–1.0
    reversibility: float = 0.5  # 0.0–1.0 (higher = more reversible)
    cost_cents: int = 0
    exact_steps: List[str] = field(default_factory=list)
    expected_effect: str = ""
    risk_of_overcorrecting: str = ""
    before_measurement: Dict[str, Any] = field(default_factory=dict)
    after_measurement: Dict[str, Any] = field(default_factory=dict)
    status: RepairStatus = RepairStatus.PENDING

    @property
    def priority(self) -> float:
        """Priority = impact × urgency × reversibility ÷ effort."""
        if self.effort == 0:
            return self.impact * self.urgency * self.reversibility
        return (self.impact * self.urgency * self.reversibility) / self.effort


@dataclass
class AudienceLens:
    """Configuration for an audience viewpoint."""
    id: str = ""  # "recruiter", "investor", "admissions", etc.
    name: str = ""
    icon: str = ""
    priorities: List[str] = field(default_factory=list)
    evidence_preferences: List[str] = field(default_factory=list)
    common_false_positives: List[str] = field(default_factory=list)
    risk_sensitivity: float = 0.5
    repair_preferences: List[str] = field(default_factory=list)
    forbidden_outputs: List[str] = field(default_factory=list)
    confidence_rules: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Report:
    """A complete audit report snapshot."""
    id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)
    version: int = 1
    audit_mode: AuditMode = AuditMode.GENERAL
    scope: List[str] = field(default_factory=list)
    source_count: int = 0
    artifact_count: int = 0
    claim_count: int = 0
    contradiction_count: int = 0
    risk_count: int = 0
    repair_count: int = 0
    sections: Dict[str, Any] = field(default_factory=dict)
    export_policy: Dict[str, bool] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    snapshot_id: Optional[str] = None
