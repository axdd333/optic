"""Signal auditor — orchestrates detection across multiple detectors.

The SignalAuditor runs a configurable set of detectors against
a signal and aggregates the results into an AuditResult.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import SignalAudit, AuditResult, SignalSource, Severity
from .detectors import SignalDetector


@dataclass
class AuditConfig:
    """Configuration for the signal auditor.

    Attributes:
        name: Name of this audit configuration.
        detectors: List of detector names to use (empty = use all available).
        min_confidence: Minimum confidence threshold to include a detection.
        max_detections_per_signal: Maximum detections to keep per signal.
        include_metadata: Whether to include full metadata in results.
    """
    name: str = "default"
    detectors: list[str] = field(default_factory=list)
    min_confidence: float = 0.0
    max_detections_per_signal: int = 50
    include_metadata: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "AuditConfig":
        return cls(**json.loads(Path(path).read_text()))


class SignalAuditor:
    """Orchestrates signal auditing across multiple detectors.

    Usage:
        auditor = SignalAuditor()
        auditor.add_detector(PatternDetector.default_bias_patterns())

        audit = auditor.audit("some text content", SignalSource.TEXT)
        result = auditor.audit_multiple([...])
    """

    def __init__(self, config: AuditConfig | None = None):
        self.config = config or AuditConfig()
        self._detectors: dict[str, SignalDetector] = {}

    def add_detector(self, detector: SignalDetector) -> None:
        """Register a detector with the auditor."""
        self._detectors[detector.name] = detector

    def add_detectors(self, *detectors: SignalDetector) -> None:
        """Register multiple detectors."""
        for d in detectors:
            self.add_detector(d)

    @property
    def detectors(self) -> dict[str, SignalDetector]:
        return self._detectors

    def _get_active_detectors(self) -> list[SignalDetector]:
        """Get the list of detectors to use based on config."""
        if not self.config.detectors:
            return list(self._detectors.values())
        return [self._detectors[name] for name in self.config.detectors if name in self._detectors]

    def audit(
        self,
        content: str,
        source: SignalSource,
        content_summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SignalAudit:
        """Audit a single signal using all registered detectors.

        Args:
            content: The signal content to analyze.
            source: Type of signal being audited.
            content_summary: Optional summary of the content.
            metadata: Optional metadata about the signal.

        Returns:
            A SignalAudit with all detections.
        """
        audit = SignalAudit(
            id=str(uuid4()),
            source=source,
            content_summary=content_summary or content[:100],
            metadata=metadata or {},
        )

        active_detectors = self._get_active_detectors()
        for detector in active_detectors:
            detections = detector.detect(content, source, metadata)
            for det in detections:
                if det.confidence >= self.config.min_confidence:
                    audit.add_detection(det)

        # Sort by severity (critical first), then by confidence
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        audit.detections.sort(key=lambda d: (severity_order.get(d.severity, 5), -d.confidence))

        # Cap at max_detections
        if len(audit.detections) > self.config.max_detections_per_signal:
            audit.detections = audit.detections[: self.config.max_detections_per_signal]

        return audit

    def audit_multiple(
        self,
        signals: list[tuple[str, SignalSource, str, dict[str, Any]]],
    ) -> AuditResult:
        """Audit multiple signals and produce an aggregated result.

        Args:
            signals: List of (content, source, summary, metadata) tuples.

        Returns:
            An aggregated AuditResult.
        """
        audits: list[SignalAudit] = []
        total_severity_score = 0.0
        severity_weights = {
            Severity.CRITICAL: 1.0,
            Severity.HIGH: 0.8,
            Severity.MEDIUM: 0.5,
            Severity.LOW: 0.3,
            Severity.INFO: 0.1,
        }

        for content, source, summary, metadata in signals:
            audit = self.audit(content, source, summary, metadata)
            audits.append(audit)

            # Calculate severity score for this signal
            for det in audit.detections:
                total_severity_score += severity_weights.get(det.severity, 0.0)

        # Normalize score to 0.0 - 1.0 range
        total_possible = len(signals) * 50  # arbitrary max
        score = min(1.0, total_severity_score / max(1, total_possible))

        # Generate summary and recommendations
        summary, recommendations = self._generate_summary(audits)

        result = AuditResult(
            audit_id=str(uuid4()),
            signals=audits,
            summary=summary,
            recommendations=recommendations,
            score=score,
        )

        return result

    def _generate_summary(
        self,
        audits: list[SignalAudit],
    ) -> tuple[str, list[str]]:
        """Generate a summary and recommendations based on audit results."""
        total_signals = len(audits)
        total_detections = sum(len(a.detections) for a in audits)
        critical = sum(
            1 for a in audits for d in a.detections
            if d.severity == Severity.CRITICAL
        )
        high = sum(
            1 for a in audits for d in a.detections
            if d.severity == Severity.HIGH
        )

        summary = (
            f"Audited {total_signals} signal(s). Found {total_detections} detection(s): "
            f"{critical} critical, {high} high."
        )

        recommendations = []
        if critical > 0:
            recommendations.append(f"Immediately review the {critical} critical detection(s).")
        if high > 0:
            recommendations.append(f"Prioritize investigation of the {high} high-severity detection(s).")
        if total_detections == 0:
            recommendations.append("No issues detected in this batch.")

        return summary, recommendations
