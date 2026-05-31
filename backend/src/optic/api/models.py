"""Pydantic request/response models for the Optic API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class MLConfig(BaseModel):
    """Optional configuration overrides for ML detection."""

    confidence_threshold: float | None = Field(None, ge=0.0, le=1.0, description="Override MLDetector confidence threshold")
    enable_keyword_analysis: bool | None = Field(None, description="Enable keyword bias analysis")
    enable_pattern_analysis: bool | None = Field(None, description="Enable manipulation pattern analysis")
    enable_sentiment_divergence: bool | None = Field(None, description="Enable sentiment divergence detection")


class DetectionResponse(BaseModel):
    """A single detection found during an audit."""

    attribute: str
    severity: str
    confidence: float
    location: str = ""
    description: str = ""
    source: str = "rule"  # 'rule' or 'ml' — indicates which detector produced this detection
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalAuditResponse(BaseModel):
    """Response model for a single signal audit."""

    id: str
    source: str
    content_summary: str
    created_at: str
    detections: list[DetectionResponse] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditResultResponse(BaseModel):
    """Response model for an aggregated audit result."""

    audit_id: str
    signals: list[SignalAuditResponse] = Field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
    score: float = 0.0


class AuditSingleRequest(BaseModel):
    """Request to audit a single signal."""

    content: str = Field(..., min_length=1, description="The signal content to audit")
    source: str = Field("text", description="Type of signal source")
    content_summary: str = Field("", description="Optional summary of the content")
    metadata: dict[str, Any] = Field(default_factory=dict)
    include_ml: bool = Field(False, description="When true, also run ML detection and merge results")
    ml_config: MLConfig | None = Field(None, description="Optional overrides for ML detection settings")


class AuditBatchRequest(BaseModel):
    """Request to audit multiple signals in one batch."""

    signals: list[AuditSingleRequest] = Field(..., min_length=1, max_length=100)
    include_ml: bool = Field(False, description="When true, also run ML detection on all signals")
    ml_config: MLConfig | None = Field(None, description="Optional overrides for ML detection settings")


class AuditHistoryItem(BaseModel):
    """A single item in the audit history."""

    id: str
    source: str
    content_summary: str
    created_at: str
    detection_count: int
    score: float | None = None


class MLAuditSingleRequest(BaseModel):
    """Request to run ML detection on a single text."""

    content: str = Field(..., min_length=1, description="The text to analyze")
    source: str = Field("text", description="Type of signal source")
    confidence_threshold: float | None = Field(None, ge=0.0, le=1.0, description="Override MLDetector confidence threshold")
    enable_keyword_analysis: bool | None = Field(None, description="Enable keyword bias analysis")
    enable_pattern_analysis: bool | None = Field(None, description="Enable manipulation pattern analysis")
    enable_sentiment_divergence: bool | None = Field(None, description="Enable sentiment divergence detection")


class MLAuditBatchRequest(BaseModel):
    """Request to run ML detection on multiple texts."""

    signals: list[MLAuditSingleRequest] = Field(..., min_length=1, max_length=100)


class MLAuditResponse(BaseModel):
    """Response from ML-based audit."""

    id: str
    content_summary: str
    source: str
    created_at: str
    detections: list[DetectionResponse] = Field(default_factory=list)
    config_used: dict[str, Any] = Field(default_factory=dict)


class MLAuditBatchResponse(BaseModel):
    """Response from batch ML audit."""

    audit_id: str
    signals: list[MLAuditResponse] = Field(default_factory=list)
    score: float = 0.0
    recommendations: list[str] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list, description="Isolated per-item errors")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
    service: str = "optic"
    timestamp: str = ""
