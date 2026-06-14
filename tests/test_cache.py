"""Tests for cache functionality."""

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
    """Test DiskCache core behavior."""

    @pytest.fixture
    def cache(self, cache_dir):
        return DiskCache(cache_dir=cache_dir, default_ttl=3600)

    def test_set_and_get(self, cache):
        cache.set("key", {"data": "value"}, ttl=3600)
        assert cache.get("key") == {"data": "value"}

    def test_get_miss(self, cache):
        assert cache.get("missing") is None

    def test_expiration(self, cache):
        cache.set("key", "value", ttl=1)
        assert cache.get("key") == "value"
        time.sleep(1.5)
        assert cache.get("key") is None

    def test_delete(self, cache):
        cache.set("key", "value", ttl=3600)
        cache.delete("key")
        assert cache.get("key") is None

    def test_clear(self, cache):
        cache.set("a", 1, ttl=3600)
        cache.set("b", 2, ttl=3600)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_overwrite(self, cache):
        cache.set("key", "first", ttl=3600)
        cache.set("key", "second", ttl=3600)
        assert cache.get("key") == "second"

    def test_make_key_consistent_and_distinct(self, cache):
        key_a = cache.make_key(query="test", page=1)
        key_b = cache.make_key(query="test", page=1)
        key_c = cache.make_key(query="test", page=2)
        assert key_a == key_b
        assert key_a != key_c
        assert isinstance(key_a, str) and len(key_a) == 64  # SHA256 hex

    def test_default_ttl_used_when_none(self, cache):
        cache.set("key", "value")  # No ttl → uses default_ttl=3600
        assert cache.get("key") == "value"


class TestNullCache:
    """NullCache is a no-op implementation."""

    def test_all_operations_are_noop(self):
        cache = NullCache()
        cache.set("key", "value", ttl=3600)
        assert cache.get("key") is None
        cache.delete("key")  # Should not raise
        cache.clear()  # Should not raise


class TestCacheBaseInterface:
    """Both implementations are CacheBase subclasses."""

    @pytest.mark.parametrize("make_cache", [
        lambda: DiskCache(cache_dir=tempfile.mkdtemp()),
        lambda: NullCache(),
    ])
    def test_is_cache_base(self, make_cache):
        assert isinstance(make_cache(), CacheBase)


class TestModuleFunctions:
    """Test module-level get_cache / clear_cache / reset_cache."""

    def test_get_cache_returns_disk_when_enabled(self, cache_dir):
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "true"
        assert isinstance(get_cache(), DiskCache)

    def test_get_cache_returns_null_when_disabled(self, cache_dir):
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "false"
        assert isinstance(get_cache(), NullCache)

    def test_clear_cache(self, cache_dir):
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "true"
        cache = get_cache()
        cache.set("key", "value", ttl=3600)
        clear_cache()
        assert cache.get("key") is None

    def test_clear_cache_url(self, cache_dir):
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "true"
        cache = get_cache()
        cache.set("key", "value", ttl=3600)
        clear_cache_url("https://example.com")
        key = cache.make_key(url="https://example.com")
        assert cache.get(key) is None

    def test_reset_cache_allows_new_instance(self, cache_dir):
        reset_cache()
        os.environ["SERP_CACHE_DIR"] = cache_dir
        os.environ["SERP_CACHE_ENABLED"] = "true"
        cache1 = get_cache()

        os.environ["SERP_CACHE_ENABLED"] = "false"
        reset_cache()
        cache2 = get_cache()
        assert isinstance(cache2, NullCache)
        assert cache1 is not cache2


class TestEnvironmentVariables:
    """Test that env vars configure the cache correctly."""

    def test_cache_dir_from_env(self):
        reset_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["SERP_CACHE_DIR"] = tmpdir
            os.environ["SERP_CACHE_ENABLED"] = "true"
            cache = get_cache()
            assert isinstance(cache, DiskCache)
            assert cache.cache_dir == Path(tmpdir)

    def test_cache_ttl_from_env(self):
        reset_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["SERP_CACHE_DIR"] = tmpdir
            os.environ["SERP_CACHE_TTL"] = "7200"
            os.environ["SERP_CACHE_ENABLED"] = "true"
            cache = get_cache()
            assert cache.default_ttl == 7200
