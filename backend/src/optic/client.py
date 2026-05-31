"""Python client SDK for the Optic API.

Provides synchronous and asynchronous clients for all Optic API endpoints.
Uses ``httpx`` under the hood with configurable retry logic and timeouts.

Typical usage::

    from optic.client import OpticClient

    client = OpticClient(base_url="http://localhost:8000")
    health = client.health_check()
    result = client.audit("Some content to audit")
    print(result)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OpticClientError(Exception):
    """Base exception for OpticClient errors."""


class OpticClient:
    """Synchronous client for the Optic Signal Audit API.

    Wraps all public API endpoints with retry logic, timeouts, and
    optional per‑method configuration overrides.

    Args:
        base_url: Root URL of the Optic API (e.g. ``http://localhost:8000``).
        timeout: Default request timeout in seconds (default ``30.0``).
        max_retries: Number of automatic retries on transient failures
            (default ``3``). Set to ``0`` to disable retries.
        retry_delay: Base delay in seconds between retries; uses
            exponential backoff (default ``1.0``).
        api_key: Optional API key sent as ``Authorization: Bearer <key>``.
        headers: Additional HTTP headers to include on every request.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        api_key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        _headers = headers or {}
        if api_key:
            _headers.setdefault("Authorization", f"Bearer {api_key}")

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers=_headers,
        )

    # ── Internal helpers ───────────────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Issue an HTTP request with automatic retry on transient errors.

        Retryable statuses: 429 (rate limit), 502, 503, 504.
        """
        last_exc: Exception | None = None

        for attempt in range(1 + self.max_retries):
            try:
                resp = self._client.request(method, path, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning(
                    "Request %s %s failed (attempt %d/%d): %s",
                    method, path, attempt + 1, 1 + self.max_retries, exc,
                )
                last_exc = exc
                self._backoff(attempt)
                continue

            if resp.status_code in (429, 502, 503, 504) and attempt < self.max_retries:
                logger.warning(
                    "Request %s %s returned %d (attempt %d/%d)",
                    method, path, resp.status_code, attempt + 1, 1 + self.max_retries,
                )
                self._backoff(attempt)
                continue

            # On the last attempt, if we get a retryable status, fail gracefully
            if resp.status_code in (429, 502, 503, 504):
                raise OpticClientError(
                    f"Request {method} {path} failed with status {resp.status_code} "
                    f"after {1 + self.max_retries} attempts"
                )

            resp.raise_for_status()
            return resp

        raise OpticClientError(
            f"Request {method} {path} failed after {1 + self.max_retries} attempts"
        ) from last_exc

    def _backoff(self, attempt: int) -> None:
        """Exponential backoff with jitter."""
        import time
        import random

        delay = self.retry_delay * (2**attempt) + random.uniform(0, 0.5)
        time.sleep(delay)

    # ── System endpoints ───────────────────────────────────────────────

    def health_check(self) -> dict[str, Any]:
        """GET /health — check if the API is reachable.

        Returns:
            Dict with keys ``status``, ``version``, ``service``, ``timestamp``.
        """
        resp = self._request("GET", "/health")
        return resp.json()

    # ── Audit endpoints ────────────────────────────────────────────────

    def audit(
        self,
        content: str,
        *,
        source: str = "text",
        content_summary: str = "",
        metadata: dict[str, Any] | None = None,
        include_ml: bool = False,
    ) -> dict[str, Any]:
        """POST /audit — audit a single signal.

        Args:
            content: The signal content to audit.
            source: Type of signal source (default ``"text"``).
            content_summary: Optional summary of the content.
            metadata: Optional metadata dict.
            include_ml: When ``True``, also run ML detection and merge results.

        Returns:
            Dict with keys ``id``, ``source``, ``content_summary``,
            ``created_at``, ``detections``, ``metadata``.
        """
        body: dict[str, Any] = {
            "content": content,
            "source": source,
        }
        if content_summary:
            body["content_summary"] = content_summary
        if metadata:
            body["metadata"] = metadata
        if include_ml:
            body["include_ml"] = True

        resp = self._request("POST", "/audit", json=body)
        return resp.json()

    def audit_batch(
        self,
        signals: list[dict[str, Any]],
        *,
        include_ml: bool = False,
    ) -> dict[str, Any]:
        """POST /audit/batch — audit multiple signals.

        Args:
            signals: List of signal dicts. Each should have at least
                ``{"content": "..."}`` and optionally ``source``,
                ``content_summary``, ``metadata``, ``include_ml``.
            include_ml: When ``True``, run ML detection on all signals
                (can be overridden per-signal).

        Returns:
            Dict with keys ``audit_id``, ``signals``, ``summary``,
            ``recommendations``, ``score``.
        """
        body: dict[str, Any] = {"signals": signals}
        if include_ml:
            body["include_ml"] = True

        resp = self._request("POST", "/audit/batch", json=body)
        return resp.json()

    def ml_audit(
        self,
        content: str,
        *,
        source: str = "text",
        confidence_threshold: float | None = None,
        enable_keyword_analysis: bool | None = None,
        enable_pattern_analysis: bool | None = None,
        enable_sentiment_divergence: bool | None = None,
    ) -> dict[str, Any]:
        """POST /audit/ml — run ML-based detection on a single text.

        Args:
            content: The text to analyze.
            source: Type of source (default ``"text"``).
            confidence_threshold: Override ML detector confidence threshold.
            enable_keyword_analysis: Enable keyword bias analysis.
            enable_pattern_analysis: Enable manipulation pattern analysis.
            enable_sentiment_divergence: Enable sentiment divergence detection.

        Returns:
            Dict with keys ``id``, ``content_summary``, ``source``,
            ``created_at``, ``detections``, ``config_used``.
        """
        body: dict[str, Any] = {"content": content, "source": source}
        if confidence_threshold is not None:
            body["confidence_threshold"] = confidence_threshold
        if enable_keyword_analysis is not None:
            body["enable_keyword_analysis"] = enable_keyword_analysis
        if enable_pattern_analysis is not None:
            body["enable_pattern_analysis"] = enable_pattern_analysis
        if enable_sentiment_divergence is not None:
            body["enable_sentiment_divergence"] = enable_sentiment_divergence

        resp = self._request("POST", "/audit/ml", json=body)
        return resp.json()

    def ml_audit_batch(
        self,
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """POST /audit/ml/batch — run ML detection on multiple texts.

        Args:
            signals: List of signal dicts, each with at least
                ``{"content": "..."}`` and optionally ``source``,
                ``confidence_threshold``, etc.

        Returns:
            Dict with keys ``audit_id``, ``signals``, ``score``,
            ``recommendations``, ``errors``.
        """
        resp = self._request("POST", "/audit/ml/batch", json={"signals": signals})
        return resp.json()

    # ── Retrieval endpoints ────────────────────────────────────────────

    def get_audit(self, audit_id: str) -> dict[str, Any]:
        """GET /audit/{audit_id} — retrieve a previous audit by ID.

        Args:
            audit_id: The audit ID returned by ``audit()`` or ``ml_audit()``.

        Returns:
            Dict with full audit details.
        """
        resp = self._request("GET", f"/audit/{audit_id}")
        return resp.json()

    def list_history(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """GET /history — list audit history items.

        Args:
            limit: Max items to return (default ``20``).
            offset: Number of items to skip (default ``0``).

        Returns:
            List of history item dicts with keys ``id``, ``source``,
            ``content_summary``, ``created_at``, ``detection_count``.
        """
        resp = self._request("GET", "/history", params={"limit": limit, "offset": offset})
        return resp.json()

    def get_report(
        self,
        audit_id: str,
        *,
        format: str = "html",
        download: bool = False,
    ) -> str | bytes:
        """GET /api/audits/{audit_id}/report — generate a report.

        Args:
            audit_id: The audit ID.
            format: Report format — ``"html"``, ``"json"``, or ``"pdf"``.
            download: When ``True``, stream as a downloadable file.

        Returns:
            Report content as string (html/json) or bytes (pdf).
        """
        resp = self._request(
            "GET",
            f"/api/audits/{audit_id}/report",
            params={"format": format, "download": "true" if download else "false"},
        )
        content = resp.content
        if format != "pdf":
            return content.decode("utf-8")
        return content

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> OpticClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class AsyncOpticClient:
    """Asynchronous client for the Optic API.

    Mirrors :class:`OpticClient` but uses ``httpx.AsyncClient`` and
    ``await``-based methods.

    Args:
        base_url: Root URL of the Optic API.
        timeout: Default request timeout in seconds (default ``30.0``).
        max_retries: Number of automatic retries on transient failures
            (default ``3``).
        retry_delay: Base delay in seconds between retries; uses
            exponential backoff (default ``1.0``).
        api_key: Optional API key sent as ``Authorization: Bearer <key>``.
        headers: Additional HTTP headers to include on every request.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        api_key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        _headers = headers or {}
        if api_key:
            _headers.setdefault("Authorization", f"Bearer {api_key}")

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            headers=_headers,
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        import asyncio
        import random

        last_exc: Exception | None = None

        for attempt in range(1 + self.max_retries):
            try:
                resp = await self._client.request(method, path, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                logger.warning(
                    "Request %s %s failed (attempt %d/%d): %s",
                    method, path, attempt + 1, 1 + self.max_retries, exc,
                )
                last_exc = exc
                await asyncio.sleep(self.retry_delay * (2**attempt) + random.uniform(0, 0.5))
                continue

            if resp.status_code in (429, 502, 503, 504) and attempt < self.max_retries:
                logger.warning(
                    "Request %s %s returned %d (attempt %d/%d)",
                    method, path, resp.status_code, attempt + 1, 1 + self.max_retries,
                )
                await asyncio.sleep(self.retry_delay * (2**attempt) + random.uniform(0, 0.5))
                continue

            # On the last attempt, if we get a retryable status, fail gracefully
            if resp.status_code in (429, 502, 503, 504):
                raise OpticClientError(
                    f"Request {method} {path} failed with status {resp.status_code} "
                    f"after {1 + self.max_retries} attempts"
                )

            resp.raise_for_status()
            return resp

        raise OpticClientError(
            f"Request {method} {path} failed after {1 + self.max_retries} attempts"
        ) from last_exc

    async def health_check(self) -> dict[str, Any]:
        resp = await self._request("GET", "/health")
        return resp.json()

    async def audit(
        self,
        content: str,
        *,
        source: str = "text",
        content_summary: str = "",
        metadata: dict[str, Any] | None = None,
        include_ml: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"content": content, "source": source}
        if content_summary:
            body["content_summary"] = content_summary
        if metadata:
            body["metadata"] = metadata
        if include_ml:
            body["include_ml"] = True
        resp = await self._request("POST", "/audit", json=body)
        return resp.json()

    async def audit_batch(
        self,
        signals: list[dict[str, Any]],
        *,
        include_ml: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"signals": signals}
        if include_ml:
            body["include_ml"] = True
        resp = await self._request("POST", "/audit/batch", json=body)
        return resp.json()

    async def ml_audit(
        self,
        content: str,
        *,
        source: str = "text",
        confidence_threshold: float | None = None,
        enable_keyword_analysis: bool | None = None,
        enable_pattern_analysis: bool | None = None,
        enable_sentiment_divergence: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"content": content, "source": source}
        if confidence_threshold is not None:
            body["confidence_threshold"] = confidence_threshold
        if enable_keyword_analysis is not None:
            body["enable_keyword_analysis"] = enable_keyword_analysis
        if enable_pattern_analysis is not None:
            body["enable_pattern_analysis"] = enable_pattern_analysis
        if enable_sentiment_divergence is not None:
            body["enable_sentiment_divergence"] = enable_sentiment_divergence
        resp = await self._request("POST", "/audit/ml", json=body)
        return resp.json()

    async def ml_audit_batch(self, signals: list[dict[str, Any]]) -> dict[str, Any]:
        resp = await self._request("POST", "/audit/ml/batch", json={"signals": signals})
        return resp.json()

    async def get_audit(self, audit_id: str) -> dict[str, Any]:
        resp = await self._request("GET", f"/audit/{audit_id}")
        return resp.json()

    async def list_history(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/history", params={"limit": limit, "offset": offset})
        return resp.json()

    async def get_report(
        self,
        audit_id: str,
        *,
        format: str = "html",
        download: bool = False,
    ) -> str | bytes:
        resp = await self._request(
            "GET",
            f"/api/audits/{audit_id}/report",
            params={"format": format, "download": "true" if download else "false"},
        )
        content = resp.content
        if format != "pdf":
            return content.decode("utf-8")
        return content

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AsyncOpticClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
