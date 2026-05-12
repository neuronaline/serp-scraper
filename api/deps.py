"""Dependency injection for FastAPI."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from passlib.context import CryptContext

from api.config import get_settings
from api.middleware.rate_limit import get_rate_limiter

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
header_scheme = APIKeyHeader(name="X-API-Key")

# Global semaphore for request pool
_request_semaphore: Optional[asyncio.Semaphore] = None


def get_semaphore() -> asyncio.Semaphore:
    """Get the global request semaphore."""
    global _request_semaphore
    if _request_semaphore is None:
        settings = get_settings()
        _request_semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
    return _request_semaphore


async def verify_api_key(
    key: Annotated[str, Depends(header_scheme)],
) -> str:
    """Verify the API key from the X-API-Key header.

    Args:
        key: The API key from the header

    Returns:
        The verified API key

    Raises:
        HTTPException: If the key is invalid
    """
    settings = get_settings()
    hashed_keys = settings.get_api_keys()

    if not hashed_keys:
        import warnings
        warnings.warn(
            "API running without authentication - not suitable for production. "
            "Set API_KEYS_HASHED environment variable to enable authentication."
        )
        # Allow unauthenticated access only if explicitly permitted
        if not settings.allow_no_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API authentication is not configured. Set API_KEYS_HASHED environment variable.",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        return key

    for stored_hash in hashed_keys:
        if pwd_context.verify(key, stored_hash):
            return key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key",
        headers={"WWW-Authenticate": "ApiKey"},
    )


@asynccontextmanager
async def rate_limited_request():
    """Context manager for rate-limited request processing.

    Acquires the global semaphore to limit concurrent requests.
    This ensures requests are processed sequentially up to the pool limit.
    """
    semaphore = get_semaphore()
    async with semaphore:
        yield


# Type alias for dependency injection
ApiKey = Annotated[str, Depends(verify_api_key)]


async def get_verified_api_key(
    key: Annotated[str, Depends(verify_api_key)],
) -> str:
    """Dependency that ensures API key is verified before proceeding.

    This wrapper exists to make the dependency explicit in the router signatures.
    """
    return key


@dataclass
class RateLimitInfo:
    """Rate limit information returned by the rate limit dependency."""

    remaining: int
    reset_seconds: int


async def _rate_limit_dependency(
    _verified_key: Annotated[str, Depends(verify_api_key)],
    endpoint: str,
) -> RateLimitInfo:
    """Acquire rate limit slot AFTER API key is verified.

    This dependency depends on verify_api_key to ensure the API key
    is validated BEFORE consuming a rate limit slot.

    Args:
        _verified_key: The verified API key (ensures verification happens first)
        endpoint: The endpoint name for rate limiting

    Returns:
        RateLimitInfo with remaining requests and reset time
    """
    rate_limiter = get_rate_limiter()
    remaining, reset_seconds = await rate_limiter.acquire(endpoint)
    return RateLimitInfo(remaining=remaining, reset_seconds=reset_seconds)


# Create separate dependencies for each endpoint to support FastAPI DI caching
async def search_rate_limit(
    _verified_key: Annotated[str, Depends(verify_api_key)],
) -> RateLimitInfo:
    """Rate limit dependency for /search endpoint."""
    return await _rate_limit_dependency(_verified_key, "search")


async def fetch_rate_limit(
    _verified_key: Annotated[str, Depends(verify_api_key)],
) -> RateLimitInfo:
    """Rate limit dependency for /fetch endpoint."""
    return await _rate_limit_dependency(_verified_key, "fetch")


async def news_rate_limit(
    _verified_key: Annotated[str, Depends(verify_api_key)],
) -> RateLimitInfo:
    """Rate limit dependency for /news endpoint."""
    return await _rate_limit_dependency(_verified_key, "news")
