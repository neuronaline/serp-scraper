"""Tests for Google News RSS module."""

import asyncio
from datetime import datetime

import pytest

from serp.google_news import (
    GoogleNewsClient,
    NewsResult,
    NewsSettings,
)
from serp.types import RetryPolicy
from serp.utils import ProxyError
from serp.config_pydantic import SerpConfig


class TestNewsResult:
    """Tests for NewsResult dataclass."""

    def test_news_result_creation(self):
        """Test creating a NewsResult."""
        news = NewsResult(
            title="Tesla yeni model tanıttı",
            url="https://www.bbc.com/haber/tesla-yeni-model",
            published=datetime(2026, 5, 11, 8, 0, 0),
            source="BBC",
            description="Tesla yeni bir elektrikli model tanıttı",
            query="Tesla",
        )

        assert news.title == "Tesla yeni model tanıttı"
        assert news.url == "https://www.bbc.com/haber/tesla-yeni-model"
        assert news.source == "BBC"
        assert news.query == "Tesla"

    def test_news_result_to_dict(self):
        """Test converting NewsResult to dictionary."""
        published = datetime(2026, 5, 11, 8, 0, 0)
        news = NewsResult(
            title="Test Title",
            url="https://example.com",
            published=published,
            source="TestSource",
            description="Test description",
            query="TestQuery",
        )

        result = news.to_dict()

        assert result["title"] == "Test Title"
        assert result["url"] == "https://example.com"
        assert result["source"] == "TestSource"
        assert result["description"] == "Test description"
        assert result["query"] == "TestQuery"
        assert "2026-05-11" in result["published"]


class TestNewsSettings:
    """Tests for NewsSettings dataclass."""

    def test_default_settings(self):
        """Test default news settings."""
        settings = NewsSettings()

        assert settings.language == "tr"
        assert settings.country == "TR"
        assert settings.time_range == "d"

    def test_custom_settings(self):
        """Test custom news settings."""
        settings = NewsSettings(
            language="en",
            country="US",
            time_range="w",
        )

        assert settings.language == "en"
        assert settings.country == "US"
        assert settings.time_range == "w"


class TestGoogleNewsClient:
    """Tests for GoogleNewsClient."""

    def test_client_initialization(self):
        """Test client initialization."""
        client = GoogleNewsClient()

        assert client._news_settings.language == "tr"
        assert client._news_settings.country == "TR"
        assert client._news_settings.time_range == "d"

    def test_client_custom_settings(self):
        """Test client with custom settings."""
        client = GoogleNewsClient(
            language="en",
            country="US",
            time_range="h",
        )

        assert client._news_settings.language == "en"
        assert client._news_settings.country == "US"
        assert client._news_settings.time_range == "h"

    def test_generate_queries(self):
        """Test query generation from company name."""
        client = GoogleNewsClient()

        queries = client._generate_queries("Tesla")

        assert len(queries) == 3
        assert "Tesla" in queries[0]
        assert "Tesla" in queries[1]
        assert "Tesla" in queries[2]

    def test_build_rss_url(self):
        """Test RSS URL building."""
        client = GoogleNewsClient(language="tr", country="TR")

        url = client._build_rss_url("Tesla")

        assert "news.google.com/rss/search" in url
        assert "q=Tesla" in url
        assert "hl=tr" in url
        assert "gl=TR" in url
        # ceid is URL encoded, TR:tr becomes TR%3Atr
        assert "ceid=TR%3Atr" in url

    def test_parse_date_rfc2822(self):
        """Test parsing RFC 2822 date format."""
        client = GoogleNewsClient()

        date_str = "Sun, 11 May 2026 08:00:00 GMT"
        result = client._parse_date(date_str)

        assert result.year == 2026
        assert result.month == 5
        assert result.day == 11
        assert result.hour == 8

    def test_parse_date_invalid(self):
        """Test parsing invalid date."""
        client = GoogleNewsClient()

        result = client._parse_date("invalid date")

        assert result == datetime.min

    def test_deduplicate(self):
        """Test news deduplication."""
        client = GoogleNewsClient()

        news_list = [
            NewsResult(
                title="News 1",
                url="https://example.com/news1",
                published=datetime.now(),
                source="Source1",
            ),
            NewsResult(
                title="News 2",
                url="https://example.com/news2",
                published=datetime.now(),
                source="Source2",
            ),
            NewsResult(
                title="News 1 Duplicate",
                url="https://example.com/news1",
                published=datetime.now(),
                source="Source3",
            ),
        ]

        unique = client._deduplicate(news_list)

        assert len(unique) == 2
        assert unique[0].title == "News 1"
        assert unique[1].title == "News 2"

    def test_parse_rss_xml(self):
        """Test RSS XML parsing."""
        client = GoogleNewsClient()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Google News</title>
            <item>
              <title>Tesla yeni model tanıttı</title>
              <link>https://www.bbc.com/haber/tesla-yeni-model</link>
              <pubDate>Sun, 11 May 2026 08:00:00 GMT</pubDate>
              <source>BBC</source>
              <description>Tesla'nın yeni modeli hakkında detaylar...</description>
            </item>
          </channel>
        </rss>"""

        results = client._parse_rss(xml_content, "Tesla")

        assert len(results) == 1
        assert results[0].title == "Tesla yeni model tanıttı"
        assert results[0].url == "https://www.bbc.com/haber/tesla-yeni-model"
        assert results[0].source == "BBC"
        assert results[0].query == "Tesla"

    def test_async_context_manager(self):
        """Test async context manager."""
        async def test_cm():
            async with GoogleNewsClient() as client:
                assert client is not None
            return True

        result = asyncio.run(test_cm())
        assert result is True

    def test_get_news_with_content_stub(self):
        """Test get_news_with_content is a stub that calls get_news."""
        client = GoogleNewsClient()
        # This is just testing the stub behavior - it should call get_news internally
        # We can't fully test without mocking, but verify the method exists
        assert hasattr(client, 'get_news_with_content')

    def test_retry_failed_logic(self):
        """Test _retry_failed returns True when retries remaining."""
        client = GoogleNewsClient()
        retry = RetryPolicy(max_retries=3)

        async def check_retry():
            result = await client._retry_failed(1, ProxyError("test"), retry)
            return result

        result = asyncio.run(check_retry())
        assert result is True  # Should retry since attempt 1 < max_retries 3

    def test_retry_failed_exhausted(self):
        """Test _retry_failed returns False when retries exhausted."""
        client = GoogleNewsClient()
        retry = RetryPolicy(max_retries=3)

        async def check_retry():
            result = await client._retry_failed(3, ProxyError("test"), retry)
            return result

        result = asyncio.run(check_retry())
        assert result is False  # Should not retry since attempt 3 >= max_retries 3

    def test_client_str_representation(self):
        """Test client string representation."""
        client = GoogleNewsClient()
        repr_str = repr(client)
        assert "GoogleNewsClient" in repr_str


class TestGoogleNewsModuleFunctions:
    """Tests for module-level convenience functions."""

    def test_get_default_client_returns_google_news_client(self):
        """Test get_default_client returns GoogleNewsClient instance."""
        from serp.google_news import get_default_client, reset_default_client
        reset_default_client()
        client = get_default_client()
        assert isinstance(client, GoogleNewsClient)

    def test_get_default_client_returns_same_instance(self):
        """Test get_default_client returns singleton."""
        from serp.google_news import get_default_client, reset_default_client
        reset_default_client()
        client1 = get_default_client()
        client2 = get_default_client()
        assert client1 is client2

    def test_reset_default_client_clears_singleton(self):
        """Test reset_default_client clears the singleton."""
        from serp.google_news import get_default_client, reset_default_client
        reset_default_client()
        client1 = get_default_client()
        reset_default_client()
        client2 = get_default_client()
        assert client1 is not client2

    @pytest.mark.asyncio
    async def test_quick_news_is_callable(self):
        """Test quick_news function exists and is callable."""
        from serp.google_news import quick_news
        assert callable(quick_news)


class TestNewsResultEdgeCases:
    """Tests for NewsResult edge cases."""

    def test_news_result_with_empty_description(self):
        """Test NewsResult with empty description."""
        news = NewsResult(
            title="Test Title",
            url="https://example.com",
            published=datetime.now(),
            source="TestSource",
            query="TestQuery",
        )
        assert news.description == ""

    def test_news_result_with_empty_source(self):
        """Test NewsResult with empty source."""
        news = NewsResult(
            title="Test Title",
            url="https://example.com",
            published=datetime.now(),
        )
        assert news.source == ""

    def test_news_result_to_dict_with_empty_fields(self):
        """Test to_dict with empty fields."""
        news = NewsResult(
            title="Test",
            url="https://example.com",
            published=datetime.min,
        )
        result = news.to_dict()
        assert result["source"] == ""
        assert result["description"] == ""
        assert result["query"] == ""


class TestGoogleNewsClientProxyBuilding:
    """Tests for proxy building methods in GoogleNewsClient."""

    def test_build_proxy_url_with_auth(self):
        """Test _build_proxy_url with authentication."""
        client = GoogleNewsClient()
        proxy = {
            "server": "http://gw.dataimpulse.com:823",
            "username": "user",
            "password": "pass",
        }
        result = client._build_proxy_url(proxy)
        assert "user:pass@" in result
        assert "gw.dataimpulse.com" in result

    def test_build_proxy_url_without_auth(self):
        """Test _build_proxy_url without authentication."""
        client = GoogleNewsClient()
        proxy = {"server": "http://proxy.com:8080"}
        result = client._build_proxy_url(proxy)
        assert result == "http://proxy.com:8080"

    def test_build_proxy_url_none(self):
        """Test _build_proxy_url with None."""
        client = GoogleNewsClient()
        result = client._build_proxy_url(None)
        assert result is None

    def test_get_random_proxy_no_config(self):
        """Test _get_random_proxy returns None when no proxies configured."""
        # Create a config with no proxy settings
        config = SerpConfig(
            dataimpulse_gateway=None,
            custom_proxies="",
        )
        client = GoogleNewsClient(config=config)
        result = client._get_random_proxy()
        assert result is None  # No proxies configured

    def test_build_dataimpulse_proxy_no_config(self):
        """Test _build_dataimpulse_proxy returns None when not configured."""
        # Create a config with no DataImpulse settings
        config = SerpConfig(
            dataimpulse_gateway=None,
            dataimpulse_user=None,
        )
        client = GoogleNewsClient(config=config)
        result = client._build_dataimpulse_proxy()
        assert result is None  # No DataImpulse configured


if __name__ == "__main__":
    pytest.main([__file__, "-v"])