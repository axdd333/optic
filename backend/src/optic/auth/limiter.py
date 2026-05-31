"""Per-key rate limiter with sliding window support.

Tracks request counts per API key (or other identifier) using a sliding
time window and enforces configurable limits.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when a rate limit is exceeded."""

    def __init__(self, key_id: str, limit: int, window_seconds: int) -> None:
        self.key_id = key_id
        self.limit = limit
        self.window_seconds = window_seconds
        retry_after = int(window_seconds - (time.time() % window_seconds))
        super().__init__(
            f"Rate limit exceeded for key '{key_id}': {limit} req/{window_seconds}s. "
            f"Retry after {retry_after}s."
        )


class RateLimiter:
    """Sliding-window rate limiter per identifier (API key, IP, etc.)."""

    def __init__(
        self,
        default_limit: int = 100,
        window_seconds: int = 60,
        limit_resolver: Optional[Callable[[str], int]] = None,
    ) -> None:
        """
        Args:
            default_limit: Default max requests per window.
            window_seconds: Size of the sliding window in seconds.
            limit_resolver: Optional callable that takes an identifier and returns
                a custom rate limit. Allows per-key limits.
        """
        self._default_limit = default_limit
        self._window_seconds = window_seconds
        self._limit_resolver = limit_resolver
        self._store: dict[str, list[float]] = {}  # identifier -> [timestamps]
        self._total_blocks: int = 0

    @property
    def total_blocks(self) -> int:
        """Total number of rate-limited requests."""
        return self._total_blocks

    def _get_limit(self, identifier: str) -> int:
        """Get the rate limit for an identifier, resolving custom limits."""
        if self._limit_resolver:
            custom = self._limit_resolver(identifier)
            if custom is not None and custom > 0:
                return custom
        return self._default_limit

    def check(self, identifier: str) -> None:
        """Check if the identifier has exceeded its rate limit.

        Raises:
            RateLimitExceeded: if the limit has been exceeded.
        """
        now = time.time()
        window_start = now - self._window_seconds

        # Purge old timestamps
        timestamps = self._store.get(identifier, [])
        timestamps = [t for t in timestamps if t > window_start]

        limit = self._get_limit(identifier)
        if len(timestamps) >= limit:
            self._total_blocks += 1
            logger.warning(
                "Rate limit exceeded for %s: %d requests in %ds window (limit=%d)",
                identifier,
                len(timestamps),
                self._window_seconds,
                limit,
            )
            raise RateLimitExceeded(identifier, limit, self._window_seconds)

        timestamps.append(now)
        self._store[identifier] = timestamps

    def remaining(self, identifier: str) -> int:
        """Get the remaining number of requests for the identifier."""
        now = time.time()
        window_start = now - self._window_seconds
        timestamps = [t for t in self._store.get(identifier, []) if t > window_start]
        limit = self._get_limit(identifier)
        return max(0, limit - len(timestamps))

    def reset(self, identifier: str) -> None:
        """Reset the rate limit counter for an identifier."""
        self._store.pop(identifier, None)
