"""Tests for SERP scraper core module."""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from serp import (
    ProxyError,
    CaptchaError,
    PageTimeoutError,
    ParseError,
    MAX_RETRIES,
    TIMEOUT_MS,
    USER_AGENTS,
    set_log_level,
    quick_search,
    quick_fetch,
    quick_search_http,
    get_default_client,
    reset_default_client,
    SerpClient,
    SerpConfig,
    SearchResult,
    RetryPolicy,
    ProxySettings,
    CacheSettings,
    SearchSettings,
    LoggingSettings,
)
from serp.config_pydantic import reset_default_config


class TestConstants:
    """Module constants are properly defined."""

    def test_constants_positive_and_populated(self):
        assert MAX_RETRIES > 0
        assert TIMEOUT_MS > 0
        assert isinstance(USER_AGENTS, list) and len(USER_AGENTS) > 0
        assert all(isinstance(ua, str) for ua in USER_AGENTS)


class TestExceptions:
    """Custom exceptions inherit from Exception and preserve messages."""

    @pytest.mark.parametrize("exc_class,msg", [
        (ProxyError, "proxy failed"),
        (CaptchaError, "captcha detected"),
        (PageTimeoutError, "timeout occurred"),
        (ParseError, "parse failed"),
    ])
    def test_exception_inherits_and_preserves_message(self, exc_class, msg):
        assert issubclass(exc_class, Exception)
        assert str(exc_class(msg)) == msg


class TestSearchResult:
    """SearchResult is a frozen dataclass with to_dict()."""

    def test_creation_and_to_dict(self):
        result = SearchResult(rank=1, title="T", url="https://e.com", description="D", source="google")
        assert result.rank == 1 and result.title == "T"
        d = result.to_dict()
        assert d == {"rank": 1, "title": "T", "url": "https://e.com", "description": "D", "source": "google"}

    def test_default_source_google(self):
        assert SearchResult(rank=1, title="T", url="https://e.com").source == "google"

    def test_immutable(self):
        result = SearchResult(rank=1, title="T", url="https://e.com")
        with pytest.raises(AttributeError):
            result.rank = 2


class TestRetryPolicy:
    """RetryPolicy with linear and exponential delay calculation."""

    def test_defaults(self):
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.delay_min == 0.5
        assert p.delay_max == 2.0
        assert p.exponential_backoff is False

    def test_calculate_delay_linear(self):
        p = RetryPolicy(delay_min=1.0, delay_max=2.0, exponential_backoff=False)
        delays = [p.calculate_delay(1) for _ in range(10)]
        assert all(1.0 <= d <= 2.0 for d in delays)

    def test_calculate_delay_exponential_capped(self):
        p = RetryPolicy(delay_min=1.0, delay_max=4.0, exponential_backoff=True)
        delay = p.calculate_delay(2)
        assert delay <= 4.0


class TestDataclassSettings:
    """Consolidated tests for settings dataclasses."""

    def test_proxy_settings_defaults(self):
        s = ProxySettings()
        assert s.custom_proxies == []
        assert s.dataimpulse_gateway is None
        assert s.strategy == "dataimpulse_first"

    def test_cache_settings_defaults(self):
        s = CacheSettings()
        assert s.enabled is True
        assert s.cache_dir == ".cache/serp"
        assert s.ttl == 86400

    def test_search_settings_defaults(self):
        s = SearchSettings()
        assert s.source == "auto"
        assert s.timeout == 30
        assert s.headless is False

    def test_logging_settings_defaults(self):
        s = LoggingSettings()
        assert s.level == "WARNING"
        assert s.enabled is True


class TestSerpConfig:
    """SerpConfig validation and nested object creation."""

    def test_defaults(self):
        reset_default_config()
        config = SerpConfig()
        assert config.log_level == "WARNING"
        assert config.max_retries == 3
        assert config.cache_enabled is True
        assert config.timeout == 30

    def test_validates_max_retries_clamped(self):
        assert SerpConfig(max_retries=0).max_retries == 1
        assert SerpConfig(max_retries=100).max_retries == 10

    def test_validates_timeout_clamped(self):
        assert SerpConfig(timeout=1).timeout == 5
        assert SerpConfig(timeout=200).timeout == 120

    def test_nested_objects_created(self):
        config = SerpConfig(cache_enabled=True, cache_ttl=7200)
        assert isinstance(config.cache, CacheSettings)
        assert config.cache.ttl == 7200
        assert isinstance(config.retry, RetryPolicy)
        assert isinstance(config.search, SearchSettings)
        assert isinstance(config.proxy, ProxySettings)


class TestUtilityFunctions:
    """Tests for utility helpers."""

    def test_random_user_agent(self):
        from serp.utils import _random_user_agent
        ua = _random_user_agent()
        assert isinstance(ua, str) and ua in USER_AGENTS

    def test_calculate_backoff_delay(self):
        from serp.utils import _calculate_backoff_delay
        delay = _calculate_backoff_delay(1)
        assert 0.5 <= delay <= 2.0

    def test_extract_bing_real_url_passthrough(self):
        from serp.utils import _extract_bing_real_url
        url = "https://example.com"
        assert _extract_bing_real_url(url) == url

    def test_extract_bing_real_url_decodes_redirect(self):
        """Bing redirect URLs encode the real URL with a 2-char prefix + base64."""
        from serp.utils import _extract_bing_real_url
        redirect = "https://www.bing.com/ck/a?u=a1aHR0cHM6Ly9leGFtcGxlLmNvbQ"
        result = _extract_bing_real_url(redirect)
        assert result == "https://example.com"


class TestSetLogLevel:
    """set_log_level should not raise for any input."""

    @pytest.mark.parametrize("level", ["DEBUG", 20, "INVALID"])
    def test_does_not_raise(self, level):
        set_log_level(level)  # Should not raise


class TestSerpClient:
    """Tests for SerpClient initialization and search."""

    def test_initialization_defaults(self):
        client = SerpClient()
        assert client._config is not None
        assert client._config.cache.enabled is True

    def test_initialization_with_config(self):
        config = SerpConfig(cache_enabled=False, max_retries=5)
        client = SerpClient(config=config)
        assert client._config is config
        assert client._config.cache.enabled is False

    def test_initialization_with_params(self):
        client = SerpClient(use_cache=False, max_retries=5, timeout=60)
        assert client._config.cache.enabled is False
        assert client._config.retry.max_retries == 5
        assert client._config.search.timeout == 60

    def test_sync_context_manager(self):
        with SerpClient() as client:
            assert client is not None

    def test_async_context_manager(self):
        async def run():
            async with SerpClient() as client:
                assert client is not None
        asyncio.run(run())

    @pytest.mark.asyncio
    async def test_search_with_mock(self):
        client = SerpClient(use_cache=False)
        mock_results = [
            SearchResult(rank=1, title="R1", url="https://e.com/1"),
            SearchResult(rank=2, title="R2", url="https://e.com/2"),
        ]
        with patch.object(client, '_search_browser', new_callable=AsyncMock, return_value=mock_results):
            results = await client.search("test")
            assert len(results) == 2
            assert results[0].title == "R1"

    @pytest.mark.asyncio
    async def test_search_respects_cache(self):
        config = SerpConfig(cache_enabled=True, cache_ttl=3600)
        client = SerpClient(config=config)
        cached_data = [{"rank": 1, "title": "Cached", "url": "https://e.com"}]
        with patch.object(client._cache, 'get', return_value=cached_data):
            results = await client.search("test", use_cache=True)
            assert len(results) == 1
            assert results[0].title == "Cached"


class TestModuleLevelFunctions:
    """Tests for singleton pattern and quick_* functions."""

    def test_singleton_pattern(self):
        reset_default_client()
        c1 = get_default_client()
        c2 = get_default_client()
        assert c1 is c2 and isinstance(c1, SerpClient)

    def test_reset_creates_new_instance(self):
        reset_default_client()
        c1 = get_default_client()
        reset_default_client()
        c2 = get_default_client()
        assert c1 is not c2

    def test_quick_functions_exist(self):
        assert callable(quick_search)
        assert callable(quick_fetch)
        assert callable(quick_search_http)
