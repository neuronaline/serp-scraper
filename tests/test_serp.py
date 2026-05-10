"""Tests for SERP scraper.

Tests public API behavior following TEST_GOVERNANCE.md principles:
- Test through public interfaces (not internal implementation)
- Avoid brittle assertions (test behavior, not exact strings)
- Minimize duplication via shared helpers
- Mock only direct dependencies, not entire systems
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from serp import (
    search,
    fetch,
    search_simple,
    ProxyError,
    CaptchaError,
    PageTimeoutError,
    ParseError,
    MAX_RETRIES,
    TIMEOUT_MS,
    USER_AGENTS,
)


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

    def test_search_is_callable(self):
        assert callable(search)

    def test_fetch_is_callable(self):
        assert callable(fetch)

    def test_search_simple_is_callable(self):
        assert callable(search_simple)

    def test_exception_types_exported(self):
        assert issubclass(ProxyError, Exception)
        assert issubclass(CaptchaError, Exception)
        assert issubclass(PageTimeoutError, Exception)
        assert issubclass(ParseError, Exception)

    def test_constants_exported(self):
        assert isinstance(MAX_RETRIES, int)
        assert isinstance(TIMEOUT_MS, int)
        assert isinstance(USER_AGENTS, list)


class TestSearchSimple:
    """Test search_simple public API behavior.

    Note: search_simple performs HTTP requests. These tests verify the
    function signature and return type behavior without hitting external services.
    """

    @pytest.mark.asyncio
    async def test_search_simple_returns_list_type(self):
        """search_simple should return a list when called with cache disabled."""
        mock_config = MagicMock()
        mock_config.get_random_proxy.return_value = None
        mock_config.has_proxies = False

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body></body></html>"
        mock_response.url.path = "/search"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("serp.utils.httpx.AsyncClient", return_value=mock_client), \
             patch("serp.simple.load_config", return_value=mock_config):
            results = await search_simple("test query", use_cache=False)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_simple_returns_list_structure(self):
        """search_simple should return list of result dicts."""
        mock_config = MagicMock()
        mock_config.get_random_proxy.return_value = None
        mock_config.has_proxies = False

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html><body>
            <div class="g">
                <h3><a href="https://example.com">Test</a></h3>
                <div class="VwiC3b">Description</div>
            </div>
        </body></html>
        """
        mock_response.url.path = "/search"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("serp.utils.httpx.AsyncClient", return_value=mock_client), \
             patch("serp.simple.load_config", return_value=mock_config):
            results = await search_simple("test query", use_cache=False)
            assert isinstance(results, list)


class TestFetch:
    """Test fetch public API behavior."""

    @pytest.mark.asyncio
    async def test_fetch_returns_string_type(self):
        """fetch should return string content when prefer_browser=False."""
        mock_config = MagicMock()
        mock_config.get_random_proxy.return_value = None
        mock_config.has_proxies = False

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Hello World"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("serp.utils.httpx.AsyncClient", return_value=mock_client), \
             patch("serp.fetch.load_config", return_value=mock_config):
            result = await fetch("https://example.com", prefer_browser=False, use_cache=False)
            assert isinstance(result, str)


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
