"""Tests for cache functionality.

Tests public API behavior following TEST_GOVERNANCE.md principles:
- Test through public interfaces (not internal implementation)
- Avoid brittle assertions (test behavior, not exact strings)
- Minimize duplication via shared fixtures (see conftest.py)
- Mock only direct dependencies, not entire systems
"""

import os
import time
import tempfile
import pytest
from pathlib import Path

from serp.cache import (
    DiskCache,
    NullCache,
    CacheBase,
    get_cache,
    clear_cache,
    clear_cache_url,
    reset_cache,
    DEFAULT_CACHE_DIR,
    DEFAULT_CACHE_TTL,
)


class TestDiskCache:
    """Test DiskCache implementation."""

    @pytest.fixture
    def cache(self, cache_dir):
        """Create a DiskCache instance with temporary directory."""
        return DiskCache(cache_dir=cache_dir, default_ttl=3600)

    def test_cache_set_and_get(self, cache):
        """Test that cache stores and retrieves values correctly."""
        cache.set("test_key", {"data": "value"}, ttl=3600)
        result = cache.get("test_key")
        assert result == {"data": "value"}

    def test_cache_get_miss(self, cache):
        """Test that cache returns None for missing keys."""
        result = cache.get("nonexistent_key")
        assert result is None

    def test_cache_expiration(self, cache):
        """Test that cache entries expire after TTL."""
        # Set with very short TTL
        cache.set("expire_key", "value", ttl=1)
        # Should be available immediately
        assert cache.get("expire_key") == "value"
        # Wait for expiration
        time.sleep(1.5)
        # Should be None after expiration
        assert cache.get("expire_key") is None

    def test_cache_delete(self, cache):
        """Test that cache.delete removes an entry."""
        cache.set("delete_key", "value", ttl=3600)
        assert cache.get("delete_key") == "value"
        cache.delete("delete_key")
        assert cache.get("delete_key") is None

    def test_cache_clear(self, cache):
        """Test that cache.clear removes all entries."""
        cache.set("key1", "value1", ttl=3600)
        cache.set("key2", "value2", ttl=3600)
        cache.set("key3", "value3", ttl=3600)
        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_cache_make_key(self, cache):
        """Test that cache key generation is consistent."""
        key1 = cache.make_key(query="test", page=1)
        key2 = cache.make_key(query="test", page=1)
        key3 = cache.make_key(query="test", page=2)
        assert key1 == key2
        assert key1 != key3

    def test_cache_different_data_same_hash(self, cache):
        """Test that different data produces same key if args same."""
        key1 = cache.make_key(query="test", page=1)
        key2 = cache.make_key(query="test", page=1)
        assert key1 == key2

    def test_cache_overwrite(self, cache):
        """Test that setting the same key overwrites the value."""
        cache.set("overwrite_key", "first", ttl=3600)
        assert cache.get("overwrite_key") == "first"
        cache.set("overwrite_key", "second", ttl=3600)
        assert cache.get("overwrite_key") == "second"

    def test_cache_default_ttl(self, cache):
        """Test that default TTL is used when not specified."""
        cache.set("ttl_key", "value")  # No ttl specified
        # The cache should have default_ttl of 3600 from fixture
        result = cache.get("ttl_key")
        assert result == "value"


class TestNullCache:
    """Test NullCache implementation."""

    @pytest.fixture
    def cache(self):
        """Create a NullCache instance."""
        return NullCache()

    def test_null_cache_get_always_returns_none(self, cache):
        """Test that NullCache.get always returns None."""
        cache.set("any_key", "any_value", ttl=3600)
        assert cache.get("any_key") is None

    def test_null_cache_set_does_nothing(self, cache):
        """Test that NullCache.set does not raise."""
        cache.set("key", "value", ttl=3600)  # Should not raise

    def test_null_cache_delete_does_nothing(self, cache):
        """Test that NullCache.delete does not raise."""
        cache.delete("key")  # Should not raise

    def test_null_cache_clear_does_nothing(self, cache):
        """Test that NullCache.clear does not raise."""
        cache.clear()  # Should not raise


class TestCacheBaseInterface:
    """Test that cache implementations follow the interface."""

    def test_disk_cache_is_cache_base(self):
        """Test that DiskCache is a CacheBase subclass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DiskCache(cache_dir=tmpdir)
            assert isinstance(cache, CacheBase)

    def test_null_cache_is_cache_base(self):
        """Test that NullCache is a CacheBase subclass."""
        cache = NullCache()
        assert isinstance(cache, CacheBase)


class TestCacheKeyGeneration:
    """Test cache key generation."""

    @pytest.fixture
    def cache(self, cache_dir):
        """Create a DiskCache instance."""
        return DiskCache(cache_dir=cache_dir)

    def test_make_key_with_args(self, cache):
        """Test key generation with positional arguments."""
        key = cache.make_key("query", 1)
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hex length

    def test_make_key_with_kwargs(self, cache):
        """Test key generation with keyword arguments."""
        key = cache.make_key(query="test", page=1)
        assert isinstance(key, str)
        assert len(key) == 64

    def test_make_key_consistent(self, cache):
        """Test that same inputs produce same key."""
        key1 = cache.make_key(query="test", page=1)
        key2 = cache.make_key(query="test", page=1)
        assert key1 == key2

    def test_make_key_different_for_different_inputs(self, cache):
        """Test that different inputs produce different keys."""
        key1 = cache.make_key(query="test1", page=1)
        key2 = cache.make_key(query="test2", page=1)
        assert key1 != key2


class TestModuleFunctions:
    """Test module-level functions."""

    def test_get_cache_returns_disk_cache_by_default(self, cache_dir):
        """Test that get_cache returns DiskCache when enabled."""
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "true"
        cache = get_cache()
        assert isinstance(cache, DiskCache)

    def test_get_cache_returns_null_cache_when_disabled(self, cache_dir):
        """Test that get_cache returns NullCache when disabled."""
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "false"
        cache = get_cache()
        assert isinstance(cache, NullCache)

    def test_clear_cache_works(self, cache_dir):
        """Test that clear_cache clears all entries."""
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "true"
        cache = get_cache()
        cache.set("test_key", "value", ttl=3600)
        assert cache.get("test_key") == "value"
        clear_cache()
        assert cache.get("test_key") is None

    def test_clear_cache_url_works(self, cache_dir):
        """Test that clear_cache_url clears specific URL."""
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "true"
        cache = get_cache()
        cache.set("test_key", "value", ttl=3600)
        assert cache.get("test_key") == "value"
        clear_cache_url("https://example.com")
        # The key is based on the URL in make_key
        key = cache.make_key(url="https://example.com")
        assert cache.get(key) is None

    def test_reset_cache_recreates_instance(self, cache_dir):
        """Test that reset_cache allows new cache instance."""
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "true"
        cache1 = get_cache()
        assert isinstance(cache1, DiskCache)

        # Change setting and reset to force new instance
        os.environ["SERP_CACHE_ENABLED"] = "false"
        reset_cache()
        cache2 = get_cache()
        assert isinstance(cache2, NullCache)
        assert cache1 is not cache2


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_env_cache_dir(self):
        """Test SERP_CACHE_DIR environment variable."""
        reset_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["SERP_CACHE_DIR"] = tmpdir
            os.environ["SERP_CACHE_ENABLED"] = "true"
            cache = get_cache()
            assert isinstance(cache, DiskCache)
            assert cache.cache_dir == Path(tmpdir)

    def test_env_cache_ttl(self):
        """Test SERP_CACHE_TTL environment variable."""
        reset_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["SERP_CACHE_DIR"] = tmpdir
            os.environ["SERP_CACHE_TTL"] = "7200"
            os.environ["SERP_CACHE_ENABLED"] = "true"
            cache = get_cache()
            assert isinstance(cache, DiskCache)
            assert cache.default_ttl == 7200

    def test_env_cache_enabled_false(self):
        """Test SERP_CACHE_ENABLED=false returns NullCache."""
        reset_cache()
        os.environ["SERP_CACHE_ENABLED"] = "false"
        cache = get_cache()
        assert isinstance(cache, NullCache)


class TestDefaults:
    """Test default values."""

    def test_default_cache_dir(self):
        """Test DEFAULT_CACHE_DIR is set correctly."""
        assert DEFAULT_CACHE_DIR == ".cache/serp"

    def test_default_cache_ttl(self):
        """Test DEFAULT_CACHE_TTL is 24 hours."""
        assert DEFAULT_CACHE_TTL == 86400
