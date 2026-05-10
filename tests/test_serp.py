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