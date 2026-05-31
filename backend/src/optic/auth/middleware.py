"""API key authentication middleware for FastAPI.

Validates API keys from the X-API-Key header, integrates with the
RateLimiter for per-key rate limiting, and provides a FastAPI dependency
for getting the authenticated key info.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from optic.auth.manager import APIKeyManager
from optic.auth.limiter import RateLimiter, RateLimitExceeded

logger = logging.getLogger(__name__)

# Headers
API_KEY_HEADER = "X-API-Key"
API_KEY_ID_HEADER = "X-API-Key-ID"


def _resolve_rate_limit(api_key_manager: APIKeyManager, raw_key: str) -> int:
    """Resolve rate limit for a raw API key by looking up its info."""
    info = api_key_manager.validate_key(raw_key)
    if info is None:
        return 0  # Invalid key = no requests allowed
    return info.rate_limit_per_minute


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that validates API keys and enforces rate limits.

    Skips authentication for:
    - /health endpoint
    - /docs, /redoc, /openapi.json endpoints
    - Any path in the skip_paths list

    Requires X-API-Key header for all other endpoints. Returns 401 if
    the key is missing or invalid, 429 if rate limited.
    """

    def __init__(
        self,
        app,
        api_key_manager: APIKeyManager,
        rate_limiter: Optional[RateLimiter] = None,
        skip_paths: Optional[set[str]] = None,
    ) -> None:
        super().__init__(app)
        self._api_key_manager = api_key_manager
        self._rate_limiter = rate_limiter or RateLimiter(
            default_limit=100,
            window_seconds=60,
            limit_resolver=lambda key: _resolve_rate_limit(api_key_manager, key),
        )
        self._skip_paths = skip_paths or {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/metrics",
            "/dashboard",
        }

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public endpoints
        if request.url.path in self._skip_paths or request.url.path.startswith("/dashboard"):
            return await call_next(request)

        # Skip auth for OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Extract API key from header
        raw_key = request.headers.get(API_KEY_HEADER)
        if not raw_key:
            logger.warning(
                "Missing API key on %s %s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing X-API-Key header"},
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Validate the key
        key_info = self._api_key_manager.validate_key(raw_key)
        if key_info is None:
            logger.warning(
                "Invalid API key on %s %s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or revoked API key"},
                headers={"WWW-Authenticate": "ApiKey"},
            )

        # Store key info in request state for downstream handlers
        request.state.api_key_id = key_info.key_id
        request.state.api_key_name = key_info.name

        # Rate limit per key
        try:
            self._rate_limiter.check(raw_key)
        except RateLimitExceeded as e:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": str(e),
                    "retry_after_seconds": int(e.window_seconds - (__import__("time").time() % e.window_seconds)),
                },
                headers={
                    "Retry-After": str(e.window_seconds),
                    API_KEY_ID_HEADER: key_info.key_id,
                },
            )

        # Process the request
        response = await call_next(request)

        # Attach rate limit headers
        remaining = self._rate_limiter.remaining(raw_key)
        response.headers["X-RateLimit-Limit"] = str(key_info.rate_limit_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(
            int(__import__("time").time() + 60)
        )
        response.headers[API_KEY_ID_HEADER] = key_info.key_id

        return response


async def get_api_key(request: Request) -> str:
    """FastAPI dependency to get the authenticated API key ID.

    Usage:
        @app.get("/protected")
        async def protected(key_id: str = Depends(get_api_key)):
            ...
    """
    key_id = getattr(request.state, "api_key_id", None)
    if key_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return key_id
