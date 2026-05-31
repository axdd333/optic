"""FastAPI application factory for Optic."""

from __future__ import annotations

import json
import logging
import time
import uuid
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response

# ── Rate-limiting and metrics state ──────────────────────────────────
_RATE_LIMIT_STORE: dict[str, list[float]] = {}  # ip -> [timestamps]
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 100  # per window

# ── Prometheus-style metrics ─────────────────────────────────────────
_metrics: dict[str, Any] = {
    "request_count": 0,
    "error_count": 0,
    "total_duration_ms": 0.0,
    "duration_buckets": {
        "0.01": 0,
        "0.05": 0,
        "0.1": 0,
        "0.5": 0,
        "1.0": 0,
        "5.0": 0,
        "10.0": 0,
        "+Inf": 0,
    },
    "endpoint_counts": {},
    "status_code_counts": {},
}


class RateLimitExceeded(Exception):
    pass


from starlette.middleware.base import BaseHTTPMiddleware

from optic.api.models import (
    AuditBatchRequest,
    AuditResultResponse,
    AuditSingleRequest,
    DetectionResponse,
    HealthResponse,
    SignalAuditResponse,
    AuditHistoryItem,
    MLAuditSingleRequest,
    MLAuditBatchRequest,
    MLAuditResponse,
    MLAuditBatchResponse,
)
from optic.auth import APIKeyManager, APIKeyMiddleware
from optic.signal import (
    SignalAuditor,
    SignalSource,
    PatternDetector,
    AnomalyDetector,
    ThresholdDetector,
    AuditConfig,
)
from optic.signal.ml_detector import MLDetector, create_ml_detector

# Import dashboard router (interactive HTMX dashboard)
from optic.api.dashboard import create_dashboard_router

logger = logging.getLogger(__name__)

# In-memory audit history store
_audit_history: dict[str, dict[str, Any]] = {}
_AUDIT_HISTORY_FILE = Path.home() / ".optic" / "audit_history.json"


def _load_history():
    """Load audit history from disk."""
    global _audit_history
    if _AUDIT_HISTORY_FILE.exists():
        try:
            _audit_history = json.loads(_AUDIT_HISTORY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            _audit_history = {}
    else:
        _audit_history = {}


def _save_history():
    """Save audit history to disk."""
    try:
        _AUDIT_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _AUDIT_HISTORY_FILE.write_text(json.dumps(_audit_history, indent=2, default=str))
    except OSError as e:
        logger.error(f"Failed to save audit history to {_AUDIT_HISTORY_FILE}: {e}")


def _create_default_auditor() -> SignalAuditor:
    """Create a SignalAuditor with all default detectors."""
    config = AuditConfig(
        name="default",
        min_confidence=0.0,
        max_detections_per_signal=50,
        include_metadata=True,
    )
    auditor = SignalAuditor(config=config)
    auditor.add_detector(PatternDetector.default_bias_patterns())
    auditor.add_detector(AnomalyDetector())
    auditor.add_detector(ThresholdDetector())
    return auditor


def _resolve_source(source_str: str) -> SignalSource:
    """Resolve a source string to a SignalSource enum, falling back to TEXT."""
    source_str = source_str.upper().replace(" ", "_")
    for s in SignalSource:
        if s.value == source_str.lower().replace(" ", "_"):
            return s
    # Try matching by name
    try:
        return SignalSource[source_str]
    except (KeyError, ValueError):
        logger.warning(f"Unknown source '{source_str}', falling back to TEXT")
        return SignalSource.TEXT


def _audit_to_response(audit_hash: dict) -> SignalAuditResponse:
    """Convert an audit dict to a response model."""
    return SignalAuditResponse(
        id=audit_hash.get("id", ""),
        source=audit_hash.get("source", ""),
        content_summary=audit_hash.get("content_summary", ""),
        created_at=audit_hash.get("created_at", ""),
        detections=[
            DetectionResponse(**d) for d in audit_hash.get("detections", [])
        ],
        metadata=audit_hash.get("metadata", {}),
    )


def create_application() -> FastAPI:
    """Create and configure the Optic API application."""
    _load_history()

    app = FastAPI(
        title="Optic Signal Audit API",
        description="Audit the perceived signal, not the person.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Middleware ────────────────────────────────────────────────────────

    class RequestTimingMiddleware(BaseHTTPMiddleware):
        """Log request duration for all requests, with structured metrics tracking."""

        async def dispatch(self, request: Request, call_next):
            start = time.time()
            response = await call_next(request)
            elapsed = time.time() - start
            elapsed_ms = elapsed * 1000
            status_code = response.status_code
            path = request.url.path
            method = request.method
            req_id = getattr(request.state, "request_id", "unknown")

            # Update metrics
            _metrics["request_count"] += 1
            _metrics["total_duration_ms"] += elapsed_ms
            _metrics["endpoint_counts"][f"{method} {path}"] = (
                _metrics["endpoint_counts"].get(f"{method} {path}", 0) + 1
            )
            _metrics["status_code_counts"][str(status_code)] = (
                _metrics["status_code_counts"].get(str(status_code), 0) + 1
            )
            if status_code >= 400:
                _metrics["error_count"] += 1

            # Bucket duration
            for bucket in ["0.01", "0.05", "0.1", "0.5", "1.0", "5.0", "10.0"]:
                if elapsed_ms <= float(bucket) * 1000:
                    _metrics["duration_buckets"][bucket] += 1
                    break
            else:
                _metrics["duration_buckets"]["+Inf"] += 1

            # Structured logging
            log_data = {
                "event": "request",
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": f"{elapsed_ms:.1f}",
                "request_id": req_id,
            }
            if elapsed > 1.0:
                log_data["slow"] = True
                logger.warning(json.dumps(log_data))
            else:
                logger.info(json.dumps(log_data))

            return response

    class RequestIDMiddleware(BaseHTTPMiddleware):
        """Attach a unique request ID header to every response."""

        async def dispatch(self, request: Request, call_next):
            request_id = str(uuid.uuid4())
            request.state.request_id = request_id
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

    class RateLimitMiddleware(BaseHTTPMiddleware):
        """Rate-limit requests per IP address using a sliding window."""

        async def dispatch(self, request: Request, call_next):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            window_start = now - _RATE_LIMIT_WINDOW

            # Purge old entries
            timestamps = _RATE_LIMIT_STORE.get(client_ip, [])
            timestamps = [t for t in timestamps if t > window_start]

            if len(timestamps) >= _RATE_LIMIT_MAX_REQUESTS:
                logger.warning(
                    "Rate limit exceeded for %s — %d requests in %ds window",
                    client_ip,
                    len(timestamps),
                    _RATE_LIMIT_WINDOW,
                )
                return Response(
                    content=json.dumps({
                        "detail": "Rate limit exceeded. Try again later.",
                        "retry_after_seconds": int(window_start + _RATE_LIMIT_WINDOW - now + 1),
                    }),
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(int(_RATE_LIMIT_WINDOW))},
                )

            timestamps.append(now)
            _RATE_LIMIT_STORE[client_ip] = timestamps

            response = await call_next(request)
            remaining = _RATE_LIMIT_MAX_REQUESTS - len(timestamps)
            response.headers["X-RateLimit-Limit"] = str(_RATE_LIMIT_MAX_REQUESTS)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(now + _RATE_LIMIT_WINDOW))
            return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # API key authentication (create default admin key on first run)
    _key_manager = APIKeyManager()
    if not _key_manager.list_keys():
        admin_id, admin_key = _key_manager.create_key(
            name="admin-default",
            rate_limit_per_minute=1000,
            metadata={"auto_generated": True},
        )
        logger.info(
            json.dumps({
                "event": "api_key_auto_generated",
                "key_id": admin_id,
                "warning": "Store this key securely — it will not be shown again",
            })
        )
        logger.info(f"Default admin key created: {admin_id}={admin_key}")

    app.add_middleware(APIKeyMiddleware, api_key_manager=_key_manager)

    # Export key manager for test access
    app.state.key_manager = _key_manager

    auditor = _create_default_auditor()

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health_check():
        """Health check endpoint."""
        logger.info(json.dumps({"event": "health_check"}))
        return HealthResponse(
            status="ok",
            version="0.1.0",
            service="optic",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @app.get("/metrics", tags=["system"])
    async def metrics():
        """Prometheus-style metrics endpoint exposing request count, duration histogram, and error rate."""
        total = _metrics["request_count"]
        errors = _metrics["error_count"]
        error_rate = round(errors / total, 4) if total > 0 else 0.0
        avg_duration = round(_metrics["total_duration_ms"] / total, 1) if total > 0 else 0.0

        lines = [
            "# HELP optic_request_count Total number of requests processed",
            "# TYPE optic_request_count counter",
            f"optic_request_count {total}",
            "",
            "# HELP optic_error_count Total number of error responses (status >= 400)",
            "# TYPE optic_error_count counter",
            f"optic_error_count {errors}",
            "",
            "# HELP optic_error_rate Fraction of requests that resulted in errors",
            "# TYPE optic_error_rate gauge",
            f"optic_error_rate {error_rate}",
            "",
            "# HELP optic_request_duration_ms Average request duration in milliseconds",
            "# TYPE optic_request_duration_ms gauge",
            f"optic_request_duration_ms {avg_duration}",
            "",
            "# HELP optic_request_duration_buckets Request duration histogram buckets (ms)",
            "# TYPE optic_request_duration_buckets histogram",
        ]
        for bucket, count in sorted(
            _metrics["duration_buckets"].items(),
            key=lambda x: float(x[0]) if x[0] != "+Inf" else float("inf"),
        ):
            le = bucket if bucket == "+Inf" else f"{float(bucket) * 1000:.0f}"
            lines.append(f'optic_request_duration_buckets{{le="{le}"}} {count}')

        lines.append("")
        lines.append("# HELP optic_endpoint_counts Request count per endpoint (method path)")
        lines.append("# TYPE optic_endpoint_counts counter")
        for endpoint, count in sorted(_metrics["endpoint_counts"].items()):
            lines.append(f'optic_endpoint_counts{{endpoint="{endpoint}"}} {count}')

        lines.append("")
        lines.append("# HELP optic_status_code_counts Request count per HTTP status code")
        lines.append("# TYPE optic_status_code_counts counter")
        for code, count in sorted(_metrics["status_code_counts"].items()):
            lines.append(f'optic_status_code_counts{{code="{code}"}} {count}')

        return Response(
            content="\n".join(lines) + "\n",
            media_type="text/plain; version=0.0.4",
        )

    # ── ML Detection ──────────────────────────────────────────────────────

    ml_detector = create_ml_detector()

    def _detection_to_response(d: Any, source_tag: str = "rule") -> DetectionResponse:
        return DetectionResponse(
            attribute=d.attribute,
            severity=d.severity.value if hasattr(d.severity, 'value') else str(d.severity),
            confidence=d.confidence,
            location=d.location or "",
            description=d.description or "",
            source=source_tag,
            metadata=d.metadata or {},
        )

    def _make_ml_detector(base: MLDetector, **overrides: Any) -> MLDetector:
        """Create an MLDetector with optional overrides on top of a base instance."""
        overridden = {k: v for k, v in overrides.items() if v is not None}
        if not overridden:
            return base
        return MLDetector(
            confidence_threshold=overridden.get("confidence_threshold", base.confidence_threshold),
            enable_keyword_analysis=overridden.get("enable_keyword_analysis", base.enable_keyword_analysis),
            enable_pattern_analysis=overridden.get("enable_pattern_analysis", base.enable_pattern_analysis),
            enable_sentiment_divergence=overridden.get("enable_sentiment_divergence", base.enable_sentiment_divergence),
        )

    def _run_ml_if_requested(content: str, source: SignalSource, request: AuditSingleRequest, ml_detector: MLDetector) -> list[DetectionResponse]:
        """Run ML detection if include_ml is True, returning tagged detections."""
        if not request.include_ml:
            return []

        cfg = request.ml_config
        detector = _make_ml_detector(
            ml_detector,
            confidence_threshold=cfg.confidence_threshold if cfg else None,
            enable_keyword_analysis=cfg.enable_keyword_analysis if cfg else None,
            enable_pattern_analysis=cfg.enable_pattern_analysis if cfg else None,
            enable_sentiment_divergence=cfg.enable_sentiment_divergence if cfg else None,
        )
        try:
            ml_results = detector.detect(content, source)
            return [_detection_to_response(d, source_tag="ml") for d in ml_results]
        except Exception as e:
            logger.warning(f"ML detection failed (non-fatal): {e}")
            return []

    @app.post("/audit/ml", response_model=MLAuditResponse, tags=["ml-audit"])
    async def ml_audit_single(request: MLAuditSingleRequest):
        """Run ML-based detection on a single text."""
        source = _resolve_source(request.source)

        # Use shared instance where possible, override specific params
        detector = _make_ml_detector(
            ml_detector,
            confidence_threshold=request.confidence_threshold,
            enable_keyword_analysis=request.enable_keyword_analysis,
            enable_pattern_analysis=request.enable_pattern_analysis,
            enable_sentiment_divergence=request.enable_sentiment_divergence,
        )

        try:
            detections = detector.detect(request.content, source)
        except Exception as e:
            logger.error(f"ML audit failed: {e}")
            raise HTTPException(status_code=500, detail=f"ML audit failed: {str(e)}")

        audit_id = f"ml-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{abs(hash(request.content)) % 10000:04d}"

        config_used = {
            "confidence_threshold": detector.confidence_threshold,
            "enable_keyword_analysis": detector.enable_keyword_analysis,
            "enable_pattern_analysis": detector.enable_pattern_analysis,
            "enable_sentiment_divergence": detector.enable_sentiment_divergence,
        }

        return MLAuditResponse(
            id=audit_id,
            content_summary=request.content[:80],
            source=source.value,
            created_at=datetime.now(timezone.utc).isoformat(),
            detections=[_detection_to_response(d) for d in detections],
            config_used=config_used,
        )

    @app.post("/audit/ml/batch", response_model=MLAuditBatchResponse, tags=["ml-audit"])
    async def ml_audit_batch(request: MLAuditBatchRequest):
        """Run ML-based detection on multiple texts."""
        if not request.signals:
            raise HTTPException(status_code=422, detail="Batch must contain at least one signal")

        for i, sig in enumerate(request.signals):
            if not sig.content or not sig.content.strip():
                raise HTTPException(status_code=422, detail=f"Signal {i} has empty content")

        all_responses: list[MLAuditResponse] = []
        errors: list[dict[str, Any]] = []

        for idx, sig in enumerate(request.signals):
            source = _resolve_source(sig.source)
            try:
                detector = _make_ml_detector(
                    ml_detector,
                    confidence_threshold=sig.confidence_threshold,
                    enable_keyword_analysis=sig.enable_keyword_analysis,
                    enable_pattern_analysis=sig.enable_pattern_analysis,
                    enable_sentiment_divergence=sig.enable_sentiment_divergence,
                )
                detections = detector.detect(sig.content, source)
            except Exception as e:
                logger.warning(f"Batch item {idx} ML audit failed (isolated): {e}")
                errors.append({"index": idx, "error": str(e)})
                continue

            audit_id = f"ml-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{abs(hash(sig.content)) % 10000:04d}"
            config_used = {
                "confidence_threshold": detector.confidence_threshold,
                "enable_keyword_analysis": detector.enable_keyword_analysis,
                "enable_pattern_analysis": detector.enable_pattern_analysis,
                "enable_sentiment_divergence": detector.enable_sentiment_divergence,
            }
            all_responses.append(MLAuditResponse(
                id=audit_id,
                content_summary=sig.content[:80],
                source=source.value,
                created_at=datetime.now(timezone.utc).isoformat(),
                detections=[_detection_to_response(d) for d in detections],
                config_used=config_used,
            ))

        # Calculate aggregate score (mean confidence across all detections)
        all_confs = [d.confidence for r in all_responses for d in r.detections]
        aggregate_score = (sum(all_confs) / len(all_confs)) if all_confs else 0.0

        recommendations = []
        if aggregate_score > 0.5:
            recommendations.append("High ML-detected signal manipulation — manual review recommended")
        if any("dog_whistle" in d.attribute for r in all_responses for d in r.detections):
            recommendations.append("Dog whistle language detected — escalate to policy review")

        return MLAuditBatchResponse(
            audit_id=f"ml-batch-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            signals=all_responses,
            score=round(aggregate_score, 3),
            recommendations=recommendations,
            errors=errors,
        )

    @app.post("/audit", response_model=SignalAuditResponse, tags=["audit"])
    async def audit_single(request: AuditSingleRequest):
        """Audit a single signal and return detections."""
        if not request.content or not request.content.strip():
            raise HTTPException(status_code=422, detail="Content must not be empty")

        source = _resolve_source(request.source)

        try:
            audit = auditor.audit(
                content=request.content,
                source=source,
                content_summary=request.content_summary,
                metadata=request.metadata,
            )
        except Exception as e:
            logger.error(f"Audit failed: {e}")
            raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")

        # Build combined detections from rule-based audit
        combined_detections = [
            DetectionResponse(
                attribute=d.attribute,
                severity=d.severity.value if hasattr(d.severity, 'value') else str(d.severity),
                confidence=d.confidence,
                location=d.location or "",
                description=d.description or "",
                source="rule",
                metadata=d.metadata or {},
            )
            for d in audit.detections
        ]

        # Add ML detections if requested
        ml_detections = _run_ml_if_requested(request.content, source, request, ml_detector)
        combined_detections.extend(ml_detections)

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        combined_detections.sort(key=lambda d: (severity_order.get(d.severity, 5), -d.confidence))

        # Store in history
        audit_hash = {
            "id": audit.id,
            "source": audit.source.value,
            "content_summary": audit.content_summary,
            "created_at": audit.created_at,
            "detections": [d.model_dump() for d in combined_detections],
            "metadata": audit.metadata,
        }
        _audit_history[audit.id] = audit_hash
        _save_history()

        return SignalAuditResponse(
            id=audit_hash["id"],
            source=audit_hash["source"],
            content_summary=audit_hash["content_summary"],
            created_at=audit_hash["created_at"],
            detections=combined_detections,
            metadata=audit_hash["metadata"],
        )

    @app.post("/audit/batch", response_model=AuditResultResponse, tags=["audit"])
    async def audit_batch(request: AuditBatchRequest):
        """Audit multiple signals in a single batch."""
        if not request.signals:
            raise HTTPException(status_code=422, detail="Batch must contain at least one signal")

        for i, sig in enumerate(request.signals):
            if not sig.content or not sig.content.strip():
                raise HTTPException(status_code=422, detail=f"Signal {i} has empty content")

        signals = []
        for sig in request.signals:
            source = _resolve_source(sig.source)
            signals.append((sig.content, source, sig.content_summary, sig.metadata, sig))

        try:
            result = auditor.audit_multiple([(c, s, cs, m) for c, s, cs, m, _ in signals])
        except Exception as e:
            logger.error(f"Batch audit failed: {e}")
            raise HTTPException(status_code=500, detail=f"Batch audit failed: {str(e)}")

        # Merge ML detections if requested
        batch_ml_config = request.ml_config
        all_signals_responses = []
        for i, audit in enumerate(result.signals):
            _, source, _, _, orig_sig = signals[i]
            combined_detections = [
                DetectionResponse(
                    attribute=d.attribute,
                    severity=d.severity.value if hasattr(d.severity, 'value') else str(d.severity),
                    confidence=d.confidence,
                    location=d.location or "",
                    description=d.description or "",
                    source="rule",
                    metadata=d.metadata or {},
                )
                for d in audit.detections
            ]

            # Apply batch-level include_ml or per-signal include_ml
            orig_sig.include_ml = orig_sig.include_ml or request.include_ml
            ml_detections = _run_ml_if_requested(orig_sig.content, source, orig_sig, ml_detector)
            combined_detections.extend(ml_detections)

            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            combined_detections.sort(key=lambda d: (severity_order.get(d.severity, 5), -d.confidence))

            audit_hash = {
                "id": audit.id,
                "source": audit.source.value,
                "content_summary": audit.content_summary,
                "created_at": audit.created_at,
                "detections": [d.model_dump() for d in combined_detections],
                "metadata": audit.metadata,
            }
            _audit_history[audit.id] = audit_hash

            all_signals_responses.append(SignalAuditResponse(
                id=audit_hash["id"],
                source=audit_hash["source"],
                content_summary=audit_hash["content_summary"],
                created_at=audit_hash["created_at"],
                detections=combined_detections,
                metadata=audit_hash["metadata"],
            ))

        _save_history()

        return AuditResultResponse(
            audit_id=result.audit_id,
            signals=all_signals_responses,
            summary=result.summary,
            recommendations=result.recommendations,
            score=result.score,
        )

    @app.get("/audit/{audit_id}", response_model=SignalAuditResponse, tags=["audit"])
    async def get_audit(audit_id: str):
        """Retrieve a previously performed audit by ID."""
        audit_hash = _audit_history.get(audit_id)
        if not audit_hash:
            raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")
        return _audit_to_response(audit_hash)

    @app.get("/history", response_model=list[AuditHistoryItem], tags=["audit"])
    async def list_history(limit: int = 20, offset: int = 0):
        """List all audit history items, most recent first."""
        items = []
        for aid, ah in sorted(
            _audit_history.items(),
            key=lambda x: x[1].get("created_at", ""),
            reverse=True,
        ):
            items.append(
                AuditHistoryItem(
                    id=aid,
                    source=ah.get("source", ""),
                    content_summary=ah.get("content_summary", ""),
                    created_at=ah.get("created_at", ""),
                    detection_count=len(ah.get("detections", [])),
                )
            )

        return items[offset: offset + limit]

    # ── Report Generator ─────────────────────────────────────────────────

    @app.get(
        "/api/audits/{audit_id}/report",
        tags=["reports"],
    )
    async def get_report(
        audit_id: str,
        format: str = Query(
            "html",
            description="Report format: html, json, or pdf",
            pattern="^(html|json|pdf)$",
        ),
        download: bool = Query(
            False, description="Download the report as a file"
        ),
    ):
        """Generate a report for a previously performed audit in the requested format."""
        audit_hash = _audit_history.get(audit_id)
        if not audit_hash:
            raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")

        report_data = dict(audit_hash)
        report_data.setdefault("score", None)
        report_data.setdefault("recommendations", [])

        reporter = _build_reporter()

        if format == "json":
            content = reporter.to_json(report_data)
            media_type = "application/json"
            filename = f"optic_report_{audit_id}.json"
        elif format == "pdf":
            try:
                content = reporter.to_pdf(report_data)
            except RuntimeError as e:
                raise HTTPException(status_code=501, detail=str(e))
            media_type = "application/pdf"
            filename = f"optic_report_{audit_id}.pdf"
        else:  # html
            content = reporter.to_html(report_data)
            media_type = "text/html"
            filename = f"optic_report_{audit_id}.html"

        if download:
            from fastapi.responses import StreamingResponse
            import io

            if isinstance(content, bytes):
                stream = io.BytesIO(content)
            else:
                stream = io.BytesIO(content.encode("utf-8"))

            return StreamingResponse(
                iter([stream.getvalue()]),
                media_type=media_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )

        return Response(content=content, media_type=media_type)

    # ── Interactive Dashboard (HTMX) ─────────────────────────────────────
    # Include the interactive dashboard router with SSE support
    dash_router = create_dashboard_router(
        audit_history=_audit_history,
        auditor_factory=_create_default_auditor,
        ml_detector=ml_detector,
    )
    app.include_router(dash_router)

    return app


def _build_reporter():
    """Build a ReportGenerator with the correct template directory."""
    from optic.reporter import ReportGenerator

    return ReportGenerator()


# Convenience instance
app = create_application()
