"""Optic signal analysis module.

Optic audits the perceived signal, not the person.
This module provides data models, detection algorithms, and audit report structures.
"""

from .models import SignalAudit, SignalSource, AuditResult, Detection, Severity
from .detectors import SignalDetector, PatternDetector, AnomalyDetector, ThresholdDetector
from .auditor import SignalAuditor, AuditConfig
from .ml_detector import MLDetector, create_ml_detector

__all__ = [
    "SignalAudit",
    "SignalSource",
    "AuditResult",
    "Detection",
    "Severity",
    "SignalDetector",
    "PatternDetector",
    "AnomalyDetector",
    "ThresholdDetector",
    "SignalAuditor",
    "AuditConfig",
    "MLDetector",
    "create_ml_detector",
]
