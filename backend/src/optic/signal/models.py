"""Data models for signal audits, sources, and detections."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    """Severity level of a signal detection."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SignalSource(str, Enum):
    """Source types for signals being audited."""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    SOCIAL_MEDIA = "social_media"
    NEWS_ARTICLE = "news_article"
    SPEECH = "speech"
    METADATA = "metadata"
    NETWORK = "network"
    OTHER = "other"


@dataclass
class Detection:
    """A single detection found during an audit.

    Attributes:
        attribute: What was detected (e.g., 'bias', 'manipulation', 'misinformation').
        severity: Severity level of the detection.
        confidence: Confidence score (0.0 to 1.0).
        location: Where in the signal the detection occurred (text snippet, timestamp, etc.).
        description: Human-readable description of the detection.
        metadata: Additional structured context.
    """
    attribute: str
    severity: Severity
    confidence: float
    location: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attribute": self.attribute,
            "severity": self.severity.value,
            "confidence": round(self.confidence, 4),
            "location": self.location,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Detection":
        return cls(
            attribute=d["attribute"],
            severity=Severity(d["severity"]),
            confidence=d["confidence"],
            location=d.get("location", ""),
            description=d.get("description", ""),
            metadata=d.get("metadata", {}),
        )


@dataclass
class SignalAudit:
    """An audit of a single signal.

    Attributes:
        id: Unique audit identifier.
        source: The type of signal being audited.
        content_summary: Brief summary of the signal content.
        created_at: When the audit was created.
        detections: List of detections found during audit.
        metadata: Additional context about the audit.
    """
    id: str
    source: SignalSource
    content_summary: str = ""
    created_at: str = ""
    detections: list[Detection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    @property
    def max_severity(self) -> Severity:
        """Highest severity level across all detections."""
        if not self.detections:
            return Severity.INFO
        severity_order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        max_idx = max(severity_order.index(d.severity) for d in self.detections)
        return severity_order[max_idx]

    @property
    def detection_count(self) -> int:
        return len(self.detections)

    def add_detection(self, detection: Detection) -> None:
        self.detections.append(detection)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source.value,
            "content_summary": self.content_summary,
            "created_at": self.created_at,
            "max_severity": self.max_severity.value,
            "detection_count": self.detection_count,
            "detections": [d.to_dict() for d in self.detections],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict) -> "SignalAudit":
        return cls(
            id=d["id"],
            source=SignalSource(d.get("source", "other")),
            content_summary=d.get("content_summary", ""),
            created_at=d.get("created_at", ""),
            detections=[Detection.from_dict(dd) for dd in d.get("detections", [])],
            metadata=d.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, content: str) -> "SignalAudit":
        return cls.from_dict(json.loads(content))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def load(cls, path: str | Path) -> "SignalAudit":
        return cls.from_json(Path(path).read_text())


@dataclass
class AuditResult:
    """Aggregated result of an audit across multiple signals.

    Attributes:
        audit_id: Identifier for this result set.
        signals: List of signal audits included.
        summary: Overall summary of the audit findings.
        recommendations: Recommended actions based on findings.
        score: Overall audit score (0.0 = clean, 1.0 = critical).
        created_at: When the result was generated.
    """
    audit_id: str
    signals: list[SignalAudit] = field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)
    score: float = 0.0
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    def add_signal(self, audit: SignalAudit) -> None:
        """Add a signal audit to this result."""
        self.signals.append(audit)

    @property
    def total_detections(self) -> int:
        return sum(s.detection_count for s in self.signals)

    @property
    def critical_count(self) -> int:
        return sum(
            1 for s in self.signals for d in s.detections
            if d.severity == Severity.CRITICAL
        )

    @property
    def high_count(self) -> int:
        return sum(
            1 for s in self.signals for d in s.detections
            if d.severity == Severity.HIGH
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "score": round(self.score, 4),
            "total_detections": self.total_detections,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "signals": [s.to_dict() for s in self.signals],
            "created_at": self.created_at,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, d: dict) -> "AuditResult":
        return cls(
            audit_id=d["audit_id"],
            signals=[SignalAudit.from_dict(s) for s in d.get("signals", [])],
            summary=d.get("summary", ""),
            recommendations=d.get("recommendations", []),
            score=d.get("score", 0.0),
            created_at=d.get("created_at", ""),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())
