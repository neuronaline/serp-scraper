"""Rate limiting middleware.

Global rate limiting per endpoint (not per API key).
Uses sliding window algorithm with asyncio locks.
"""

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from api.config import get_settings, RateLimitConfig


class RateLimiter:
    """Global rate limiter for endpoints.

    Uses a sliding window approach to track requests per endpoint.
    Rate limiting is global (all API keys combined).
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """Initialize the rate limiter.

        Args:
            config: Rate limit configuration. Uses settings if not provided.
        """
        if config is None:
            settings = get_settings()
            config = settings.rate_limit

        self._config = config
        self._counters: dict[str, list[datetime]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def _get_limit(self, endpoint: str) -> int:
        """Get the rate limit for an endpoint."""
        return getattr(self._config, endpoint, self._config.default)

    async def acquire(self, endpoint: str) -> tuple[int, int]:
        """Acquire a slot for the endpoint.

        Raises HTTPException 429 if rate limit is exceeded.

        Args:
            endpoint: The endpoint name (e.g., "search", "fetch", "news")

        Returns:
            Tuple of (remaining_requests, reset_seconds)

        Raises:
            HTTPException: 429 if rate limit is exceeded
        """
        limit = self._get_limit(endpoint)

        async with self._lock:
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(minutes=1)

            # Clean old entries outside the window
            self._counters[endpoint] = [
                t for t in self._counters[endpoint] if t > window_start
            ]

            # If at limit, calculate reset time and raise outside lock
            if len(self._counters[endpoint]) >= limit:
                oldest = min(self._counters[endpoint])
                # Time until oldest request exits the 1-minute window
                reset_delta = (now - oldest) + timedelta(minutes=1)
                reset_seconds = max(1, int(reset_delta.total_seconds()))
                # Release lock before raising exception
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for /{endpoint}. Try again in {reset_seconds} seconds.",
                    headers={"Retry-After": str(reset_seconds)},
                )

            # Add current request timestamp
            self._counters[endpoint].append(datetime.now(timezone.utc))

            remaining = limit - len(self._counters[endpoint])
            # Calculate actual reset time based on oldest request in window
            if self._counters[endpoint]:
                oldest = min(self._counters[endpoint])
                reset_delta = (oldest - now) + timedelta(minutes=1)
                reset_seconds = max(1, int(reset_delta.total_seconds()))
            else:
                reset_seconds = 60
            return remaining, reset_seconds

    async def get_remaining(self, endpoint: str) -> int:
        """Get the remaining requests for an endpoint.

        Args:
            endpoint: The endpoint name

        Returns:
            Number of remaining requests in the current window
        """
        limit = self._get_limit(endpoint)
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=1)

        async with self._lock:
            recent = [t for t in self._counters[endpoint] if t > window_start]
            return max(0, limit - len(recent))

    async def close(self) -> None:
        """Clean up resources."""
        self._counters.clear()


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the global rate limiter (for testing)."""
    global _rate_limiter
    if _rate_limiter is not None:
        asyncio.run(_rate_limiter.close())
    _rate_limiter = None
