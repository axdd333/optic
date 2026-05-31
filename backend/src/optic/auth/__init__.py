"""Optic authentication and rate limiting module.

Provides API key management, request authentication middleware,
and per-key rate limiting.
"""

from .manager import APIKeyManager, APIKeyInfo, KeyStatus
from .limiter import RateLimiter, RateLimitExceeded
from .middleware import APIKeyMiddleware, get_api_key

__all__ = [
    "APIKeyManager",
    "APIKeyInfo",
    "KeyStatus",
    "RateLimiter",
    "RateLimitExceeded",
    "APIKeyMiddleware",
    "get_api_key",
]
