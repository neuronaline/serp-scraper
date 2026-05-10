"""Cache abstraction layer for SERP scraper."""

import hashlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Environment variables
ENV_CACHE_DIR = "SERP_CACHE_DIR"
ENV_CACHE_TTL = "SERP_CACHE_TTL"  # Default TTL in seconds
ENV_CACHE_ENABLED = "SERP_CACHE_ENABLED"  # "true" or "false"

# Defaults
DEFAULT_CACHE_DIR = ".cache/serp"
DEFAULT_CACHE_TTL = 86400  # 24 hours


class CacheBase(ABC):
    """Abstract cache interface."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache. Returns None if not found or expired."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int) -> None:
        """Set value in cache with TTL in seconds."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a specific key from cache."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all cache entries."""
        pass

    def make_key(self, *args, **kwargs) -> str:
        """Create a cache key from arguments.

        Args:
            *args: Positional arguments to include in key
            **kwargs: Keyword arguments to include in key

        Returns:
            SHA256 hash hex string
        """
        data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()


class DiskCache(CacheBase):
    """Disk-based JSON cache implementation.

    Cache entries are stored as individual JSON files in the specified directory.
    Each file contains the key, value, creation time, and expiration time.

    Example cache file (.cache/serp/abc123.json):
    {
        "key": "...",
        "value": {...},
        "expires_at": 1234567890.123,
        "created_at": 1234567890.123
    }
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        default_ttl: int = DEFAULT_CACHE_TTL,
    ):
        """Initialize disk cache.

        Args:
            cache_dir: Directory to store cache files. Defaults to .cache/serp
            default_ttl: Default time-to-live in seconds. Defaults to 24 hours.
        """
        cache_dir = cache_dir or os.getenv(ENV_CACHE_DIR, DEFAULT_CACHE_DIR) or DEFAULT_CACHE_DIR
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        ttl_env = os.getenv(ENV_CACHE_TTL)
        if ttl_env:
            try:
                self.default_ttl = int(ttl_env)
            except ValueError:
                logger.warning(f"Invalid SERP_CACHE_TTL value '{ttl_env}', using default {default_ttl}")
                self.default_ttl = default_ttl
        else:
            self.default_ttl = default_ttl

    def _get_path(self, key: str) -> Path:
        """Get file path for a cache key.

        Uses the full SHA256 hash key as filename.
        """
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value if found and not expired, None otherwise
        """
        path = self._get_path(key)
        if not path.exists():
            return None

        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        # Check expiration
        expires_at = data.get("expires_at", 0)
        if time.time() > expires_at:
            try:
                path.unlink()
            except OSError:
                pass
            return None

        return data.get("value")

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time-to-live in seconds. Defaults to instance default_ttl.
        """
        if ttl is None:
            ttl = self.default_ttl

        path = self._get_path(key)
        data = {
            "key": key,
            "value": value,
            "expires_at": time.time() + ttl,
            "created_at": time.time(),
        }

        with open(path, "w") as f:
            json.dump(data, f, default=str)

    def delete(self, key: str) -> None:
        """Delete a specific key from cache.

        Args:
            key: Cache key to delete
        """
        path = self._get_path(key)
        if path.exists():
            path.unlink()

    def clear(self) -> None:
        """Clear all cache entries in the cache directory."""
        for path in self.cache_dir.glob("*.json"):
            path.unlink()


class NullCache(CacheBase):
    """A cache implementation that does nothing.

    Used when caching is disabled.
    """

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        pass

    def delete(self, key: str) -> None:
        pass

    def clear(self) -> None:
        pass


# Global cache instance
_cache: Optional[CacheBase] = None


def get_cache() -> CacheBase:
    """Get or create global cache instance.

    Returns:
        CacheBase instance (DiskCache if enabled, NullCache if disabled)
    """
    global _cache
    if _cache is None:
        enabled = os.getenv(ENV_CACHE_ENABLED, "true").lower() == "true"
        if enabled:
            _cache = DiskCache()
        else:
            _cache = NullCache()
    return _cache


def reset_cache() -> None:
    """Reset the global cache instance.

    Useful for testing or when cache settings change.
    """
    global _cache
    _cache = None


def clear_cache() -> None:
    """Clear all cache entries."""
    get_cache().clear()


def clear_cache_url(url: str) -> None:
    """Clear cache for a specific URL.

    Args:
        url: URL to clear from cache
    """
    cache = get_cache()
    key = cache.make_key(url=url)
    cache.delete(key)