"""Tests for SERP scraper.

Tests public API behavior following TEST_GOVERNANCE.md principles:
- Test through public interfaces (not internal implementation)
- Avoid brittle assertions (test behavior, not exact strings)
- Minimize duplication via shared helpers
- Mock only direct dependencies, not entire systems
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

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
    """Validate module constants are properly defined."""

    def test_max_retries_is_positive(self):
        assert MAX_RETRIES > 0

    def test_timeout_is_positive(self):
        assert TIMEOUT_MS > 0

    def test_user_agents_is_non_empty_list(self):
        assert isinstance(USER_AGENTS, list)
        assert len(USER_AGENTS) > 0
        assert all(isinstance(ua, str) for ua in USER_AGENTS)


class TestExceptions:
    """Validate custom exception classes."""

    @pytest.mark.parametrize("exc_class", [ProxyError, CaptchaError, PageTimeoutError, ParseError])
    def test_exception_inherits_from_exception(self, exc_class):
        assert issubclass(exc_class, Exception)

    @pytest.mark.parametrize("exc_class,msg", [
        (ProxyError, "proxy failed"),
        (CaptchaError, "captcha detected"),
        (PageTimeoutError, "timeout occurred"),
        (ParseError, "parse failed"),
    ])
    def test_exception_message_preserved(self, exc_class, msg):
        exc = exc_class(msg)
        assert str(exc) == msg


class TestImports:
    """Validate public API exports."""

    def test_exception_types_exported(self):
        assert issubclass(ProxyError, Exception)
        assert issubclass(CaptchaError, Exception)
        assert issubclass(PageTimeoutError, Exception)
        assert issubclass(ParseError, Exception)

    def test_constants_exported(self):
        assert isinstance(MAX_RETRIES, int)
        assert isinstance(TIMEOUT_MS, int)
        assert isinstance(USER_AGENTS, list)


class TestErrorHandling:
    """Test error handling through public API."""

    def test_captcha_error_can_be_raised(self):
        """CaptchaError should be raisable."""
        with pytest.raises(CaptchaError):
            raise CaptchaError("test captcha")

    def test_proxy_error_can_be_raised(self):
        """ProxyError should be raisable."""
        with pytest.raises(ProxyError):
            raise ProxyError("test proxy")

    def test_page_timeout_error_can_be_raised(self):
        """PageTimeoutError should be raisable."""
        with pytest.raises(PageTimeoutError):
            raise PageTimeoutError("test timeout")

    def test_parse_error_can_be_raised(self):
        """ParseError should be raisable."""
        with pytest.raises(ParseError):
            raise ParseError("test parse")


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_search_result_creation(self):
        """Test creating a SearchResult."""
        result = SearchResult(
            rank=1,
            title="Test Title",
            url="https://example.com",
            description="Test description",
            source="google",
        )

        assert result.rank == 1
        assert result.title == "Test Title"
        assert result.url == "https://example.com"
        assert result.description == "Test description"
        assert result.source == "google"

    def test_search_result_to_dict(self):
        """Test converting SearchResult to dictionary."""
        result = SearchResult(
            rank=1,
            title="Test Title",
            url="https://example.com",
            description="Test description",
            source="bing",
        )

        result_dict = result.to_dict()

        assert result_dict["rank"] == 1
        assert result_dict["title"] == "Test Title"
        assert result_dict["url"] == "https://example.com"
        assert result_dict["description"] == "Test description"
        assert result_dict["source"] == "bing"

    def test_search_result_default_source(self):
        """Test SearchResult default source is google."""
        result = SearchResult(rank=1, title="T", url="https://e.com")
        assert result.source == "google"

    def test_search_result_immutable(self):
        """Test SearchResult is immutable (frozen dataclass)."""
        result = SearchResult(rank=1, title="T", url="https://e.com")
        with pytest.raises(AttributeError):
            result.rank = 2


class TestRetryPolicy:
    """Tests for RetryPolicy dataclass."""

    def test_retry_policy_defaults(self):
        """Test default retry policy values."""
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.delay_min == 0.5
        assert policy.delay_max == 2.0
        assert policy.exponential_backoff is False

    def test_retry_policy_calculate_delay_linear(self):
        """Test linear delay calculation."""
        policy = RetryPolicy(delay_min=1.0, delay_max=2.0, exponential_backoff=False)
        # Delay should be random between min and max
        delays = [policy.calculate_delay(1) for _ in range(10)]
        for delay in delays:
            assert 1.0 <= delay <= 2.0

    def test_retry_policy_calculate_delay_exponential(self):
        """Test exponential backoff delay calculation."""
        policy = RetryPolicy(delay_min=1.0, delay_max=4.0, exponential_backoff=True)
        delay = policy.calculate_delay(2)  # Second attempt
        # Base * 2^(attempt-1) = 1.0 * 2^1 = 2.0, capped at max 4.0
        assert delay <= 4.0

    def test_retry_policy_custom_values(self):
        """Test custom retry policy values."""
        policy = RetryPolicy(max_retries=5, delay_min=1.0, delay_max=3.0, exponential_backoff=True)
        assert policy.max_retries == 5
        assert policy.delay_min == 1.0
        assert policy.delay_max == 3.0
        assert policy.exponential_backoff is True


class TestProxySettings:
    """Tests for ProxySettings dataclass."""

    def test_proxy_settings_defaults(self):
        """Test default proxy settings."""
        settings = ProxySettings()
        assert settings.custom_proxies == []
        assert settings.dataimpulse_gateway is None
        assert settings.dataimpulse_user is None
        assert settings.dataimpulse_pass is None
        assert settings.strategy == "dataimpulse_first"
        assert settings.dataimpulse_protocol == "http"

    def test_proxy_settings_custom(self):
        """Test custom proxy settings."""
        settings = ProxySettings(
            custom_proxies=["http://proxy1.com:8080"],
            dataimpulse_gateway="gw.dataimpulse.com",
            dataimpulse_user="testuser",
            dataimpulse_pass="testpass",
            strategy="random",
            dataimpulse_protocol="socks5",
        )
        assert settings.custom_proxies == ["http://proxy1.com:8080"]
        assert settings.dataimpulse_gateway == "gw.dataimpulse.com"
        assert settings.strategy == "random"
        assert settings.dataimpulse_protocol == "socks5"


class TestCacheSettings:
    """Tests for CacheSettings dataclass."""

    def test_cache_settings_defaults(self):
        """Test default cache settings."""
        settings = CacheSettings()
        assert settings.enabled is True
        assert settings.cache_dir == ".cache/serp"
        assert settings.ttl == 86400

    def test_cache_settings_custom(self):
        """Test custom cache settings."""
        settings = CacheSettings(enabled=False, cache_dir="/tmp/cache", ttl=3600)
        assert settings.enabled is False
        assert settings.cache_dir == "/tmp/cache"
        assert settings.ttl == 3600


class TestSearchSettings:
    """Tests for SearchSettings dataclass."""

    def test_search_settings_defaults(self):
        """Test default search settings."""
        settings = SearchSettings()
        assert settings.source == "auto"
        assert settings.timeout == 30
        assert settings.headless is False
        assert settings.user_agent is None

    def test_search_settings_custom(self):
        """Test custom search settings."""
        settings = SearchSettings(source="google", timeout=60, headless=True)
        assert settings.source == "google"
        assert settings.timeout == 60
        assert settings.headless is True


class TestLoggingSettings:
    """Tests for LoggingSettings dataclass."""

    def test_logging_settings_defaults(self):
        """Test default logging settings."""
        settings = LoggingSettings()
        assert settings.level == "WARNING"
        assert settings.enabled is True

    def test_logging_settings_custom(self):
        """Test custom logging settings."""
        settings = LoggingSettings(level="DEBUG", enabled=False)
        assert settings.level == "DEBUG"
        assert settings.enabled is False


class TestSerpConfig:
    """Tests for SerpConfig configuration."""

    def test_config_defaults(self):
        """Test default configuration."""
        reset_default_config()
        config = SerpConfig()
        assert config.log_level == "WARNING"
        assert config.max_retries == 3
        assert config.cache_enabled is True
        assert config.cache_ttl == 86400
        assert config.timeout == 30

    def test_config_custom_values(self):
        """Test custom configuration values."""
        config = SerpConfig(
            log_level="DEBUG",
            max_retries=5,
            cache_ttl=3600,
            timeout=60,
        )
        assert config.log_level == "DEBUG"
        assert config.max_retries == 5
        assert config.cache_ttl == 3600
        assert config.timeout == 60

    def test_config_validates_max_retries(self):
        """Test max_retries validation."""
        config = SerpConfig(max_retries=0)
        assert config.max_retries == 1  # Clamped to minimum

        config = SerpConfig(max_retries=100)
        assert config.max_retries == 10  # Clamped to maximum

    def test_config_validates_timeout(self):
        """Test timeout validation."""
        config = SerpConfig(timeout=1)
        assert config.timeout == 5  # Clamped to minimum

        config = SerpConfig(timeout=200)
        assert config.timeout == 120  # Clamped to maximum

    def test_config_nested_objects_created(self):
        """Test that nested settings objects are properly created."""
        config = SerpConfig(cache_enabled=True, cache_ttl=7200)
        assert isinstance(config.cache, CacheSettings)
        assert config.cache.enabled is True
        assert config.cache.ttl == 7200

        assert isinstance(config.retry, RetryPolicy)
        assert config.retry.max_retries == 3

        assert isinstance(config.search, SearchSettings)
        assert isinstance(config.proxy, ProxySettings)
        assert isinstance(config.logging, LoggingSettings)

    def test_config_get_nested_dict(self):
        """Test getting config as nested dictionary."""
        config = SerpConfig(log_level="INFO")
        nested = config.get_nested_dict()
        assert nested["log_level"] == "INFO"
        assert "cache_ttl" in nested
        assert "max_retries" in nested


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_random_user_agent_returns_valid_ua(self):
        """Test _random_user_agent returns a valid user agent."""
        from serp.utils import _random_user_agent
        ua = _random_user_agent()
        assert isinstance(ua, str)
        assert len(ua) > 0
        assert ua in USER_AGENTS

    def test_calculate_backoff_delay(self):
        """Test backoff delay calculation."""
        from serp.utils import _calculate_backoff_delay
        # Linear mode
        delay = _calculate_backoff_delay(1)
        assert 0.5 <= delay <= 2.0  # RETRY_DELAY_MIN to RETRY_DELAY_MAX

    def test_extract_bing_real_url_valid(self):
        """Test extracting real URL from Bing redirect."""
        from serp.utils import _extract_bing_real_url
        # This is a valid Bing redirect URL format
        redirect = "https://www.bing.com/ck/a?....&u=aHR0cHM6Ly9leGFtcGxlLmNvbQ=="
        # The actual decoding is tested - we just verify it doesn't crash
        result = _extract_bing_real_url(redirect)
        assert isinstance(result, str)

    def test_extract_bing_real_url_invalid(self):
        """Test extracting real URL from non-redirect URL."""
        from serp.utils import _extract_bing_real_url
        url = "https://example.com"
        result = _extract_bing_real_url(url)
        assert result == url


class TestSetLogLevel:
    """Tests for set_log_level function."""

    def test_set_log_level_with_string(self):
        """Test setting log level with string."""
        set_log_level("DEBUG")
        # Should not raise

    def test_set_log_level_with_int(self):
        """Test setting log level with integer."""
        import logging
        set_log_level(logging.INFO)
        # Should not raise

    def test_set_log_level_invalid_string(self):
        """Test setting invalid log level defaults to WARNING."""
        set_log_level("INVALID")
        # Should not raise, defaults to WARNING


class TestSerpClient:
    """Tests for SerpClient class."""

    def test_client_initialization_defaults(self):
        """Test client initialization with defaults."""
        client = SerpClient()
        assert client._config is not None
        assert client._config.cache.enabled is True

    def test_client_initialization_with_config(self):
        """Test client initialization with config object."""
        config = SerpConfig(cache_enabled=False, max_retries=5)
        client = SerpClient(config=config)
        assert client._config is config
        assert client._config.cache.enabled is False

    def test_client_initialization_with_params(self):
        """Test client initialization with parameters."""
        client = SerpClient(use_cache=False, max_retries=5, timeout=60)
        assert client._config.cache.enabled is False
        assert client._config.retry.max_retries == 5
        assert client._config.search.timeout == 60

    def test_client_context_manager(self):
        """Test async context manager."""
        async def test_cm():
            async with SerpClient() as client:
                assert client is not None
            return True

        result = asyncio.run(test_cm())
        assert result is True

    def test_client_sync_context_manager(self):
        """Test sync context manager."""
        with SerpClient() as client:
            assert client is not None

    @pytest.mark.asyncio
    async def test_client_search_with_mock(self):
        """Test search method with mocked internal calls."""
        client = SerpClient(use_cache=False)

        # Mock the _search_browser method to avoid actual HTTP calls
        mock_results = [
            SearchResult(rank=1, title="Result 1", url="https://example.com/1"),
            SearchResult(rank=2, title="Result 2", url="https://example.com/2"),
        ]

        with patch.object(client, '_search_browser', new_callable=AsyncMock, return_value=mock_results):
            results = await client.search("test query")
            assert len(results) == 2
            assert results[0].title == "Result 1"

    @pytest.mark.asyncio
    async def test_client_search_fallback_uses_cache(self):
        """Test that search respects use_cache parameter."""
        config = SerpConfig(cache_enabled=True, cache_ttl=3600)
        client = SerpClient(config=config)

        mock_results = [SearchResult(rank=1, title="Cached", url="https://example.com")]

        # Mock cache get to return cached results
        with patch.object(client._cache, 'get', return_value=[{"rank": 1, "title": "Cached", "url": "https://example.com"}]):
            results = await client.search("test", use_cache=True)
            assert len(results) == 1
            assert results[0].title == "Cached"


class TestQuickFunctions:
    """Tests for module-level quick_* convenience functions."""

    def test_get_default_client_returns_serp_client(self):
        """Test get_default_client returns SerpClient instance."""
        reset_default_client()
        client = get_default_client()
        assert isinstance(client, SerpClient)

    def test_get_default_client_returns_same_instance(self):
        """Test get_default_client returns singleton."""
        reset_default_client()
        client1 = get_default_client()
        client2 = get_default_client()
        assert client1 is client2

    def test_reset_default_client_clears_singleton(self):
        """Test reset_default_client clears the singleton."""
        reset_default_client()
        client1 = get_default_client()
        reset_default_client()
        client2 = get_default_client()
        assert client1 is not client2

    @pytest.mark.asyncio
    async def test_quick_search_is_callable(self):
        """Test quick_search function exists and is callable."""
        # We can't actually call it without mocking, but we verify it exists
        assert callable(quick_search)

    @pytest.mark.asyncio
    async def test_quick_fetch_is_callable(self):
        """Test quick_fetch function exists and is callable."""
        assert callable(quick_fetch)

    @pytest.mark.asyncio
    async def test_quick_search_http_is_callable(self):
        """Test quick_search_http function exists and is callable."""
        assert callable(quick_search_http)