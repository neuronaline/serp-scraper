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

    def test_creation_and_to_dict(self):
        published = datetime(2026, 5, 11, 8, 0, 0)
        news = NewsResult(
            title="Tesla announced", url="https://bbc.com/tesla",
            published=published, source="BBC",
            description="New model details", query="Tesla",
        )
        assert news.title == "Tesla announced"
        assert news.source == "BBC"

        d = news.to_dict()
        assert d["title"] == "Tesla announced"
        assert d["source"] == "BBC"
        assert "2026-05-11" in d["published"]

    def test_defaults(self):
        """Optional fields default to empty strings."""
        news = NewsResult(title="T", url="https://example.com", published=datetime.min)
        assert news.description == ""
        assert news.source == ""
        assert news.query == ""
        d = news.to_dict()
        assert d["source"] == ""
        assert d["description"] == ""


class TestGoogleNewsClient:
    """Tests for GoogleNewsClient core methods."""

    def test_initialization_defaults(self):
        client = GoogleNewsClient()
        assert client._news_settings.language == "tr"
        assert client._news_settings.country == "TR"
        assert client._news_settings.time_range == "d"

    def test_custom_settings(self):
        client = GoogleNewsClient(language="en", country="US", time_range="h")
        assert client._news_settings.language == "en"
        assert client._news_settings.country == "US"
        assert client._news_settings.time_range == "h"

    def test_generate_queries(self):
        client = GoogleNewsClient()
        queries = client._generate_queries("Tesla")
        assert len(queries) == 3
        assert all("Tesla" in q for q in queries)

    def test_build_rss_url(self):
        client = GoogleNewsClient(language="tr", country="TR")
        url = client._build_rss_url("Tesla")
        assert "news.google.com/rss/search" in url
        assert "q=Tesla" in url
        assert "hl=tr" in url
        assert "gl=TR" in url

    def test_parse_date_rfc2822(self):
        client = GoogleNewsClient()
        result = client._parse_date("Sun, 11 May 2026 08:00:00 GMT")
        assert result.year == 2026 and result.month == 5 and result.day == 11

    def test_parse_date_invalid_returns_min(self):
        client = GoogleNewsClient()
        assert client._parse_date("invalid") == datetime.min

    def test_deduplicate_by_url(self):
        client = GoogleNewsClient()
        now = datetime.now()
        news_list = [
            NewsResult(title="News 1", url="https://example.com/1", published=now, source="S1"),
            NewsResult(title="News 2", url="https://example.com/2", published=now, source="S2"),
            NewsResult(title="Dup", url="https://example.com/1", published=now, source="S3"),
        ]
        unique = client._deduplicate(news_list)
        assert len(unique) == 2

    def test_parse_rss_xml(self):
        client = GoogleNewsClient()
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><title>Google News</title>
          <item>
            <title>Tesla announced</title>
            <link>https://bbc.com/tesla</link>
            <pubDate>Sun, 11 May 2026 08:00:00 GMT</pubDate>
            <source>BBC</source>
            <description>Details...</description>
          </item>
        </channel></rss>"""
        results = client._parse_rss(xml, "Tesla")
        assert len(results) == 1
        assert results[0].title == "Tesla announced"
        assert results[0].source == "BBC"
        assert results[0].query == "Tesla"

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        async with GoogleNewsClient() as client:
            assert client is not None

    def test_retry_failed_logic(self):
        client = GoogleNewsClient()
        retry = RetryPolicy(max_retries=3)

        async def check(attempt):
            return await client._retry_failed(attempt, ProxyError("err"), retry)

        assert asyncio.run(check(1)) is True   # retries remaining
        assert asyncio.run(check(3)) is False   # retries exhausted


class TestProxyBuilding:
    """Test proxy URL construction."""

    def test_build_proxy_url_with_auth(self):
        client = GoogleNewsClient()
        result = client._build_proxy_url({
            "server": "http://gw.dataimpulse.com:823",
            "username": "user", "password": "pass",
        })
        assert "user:pass@" in result
        assert "gw.dataimpulse.com" in result

    def test_build_proxy_url_without_auth(self):
        client = GoogleNewsClient()
        result = client._build_proxy_url({"server": "http://proxy.com:8080"})
        assert result == "http://proxy.com:8080"

    def test_build_proxy_url_none(self):
        client = GoogleNewsClient()
        assert client._build_proxy_url(None) is None

    def test_get_random_proxy_no_config(self):
        config = SerpConfig(dataimpulse_gateway=None, custom_proxies="")
        client = GoogleNewsClient(config=config)
        assert client._get_random_proxy() is None

    def test_build_dataimpulse_proxy_no_config(self):
        config = SerpConfig(dataimpulse_gateway=None, dataimpulse_user=None)
        client = GoogleNewsClient(config=config)
        assert client._build_dataimpulse_proxy() is None


class TestModuleFunctions:
    """Tests for module-level singleton and convenience functions."""

    def test_singleton_pattern(self):
        from serp.google_news import get_default_client, reset_default_client
        reset_default_client()
        c1 = get_default_client()
        c2 = get_default_client()
        assert c1 is c2

    def test_reset_creates_new_instance(self):
        from serp.google_news import get_default_client, reset_default_client
        reset_default_client()
        c1 = get_default_client()
        reset_default_client()
        c2 = get_default_client()
        assert c1 is not c2

    def test_get_default_client_type(self):
        from serp.google_news import get_default_client, reset_default_client
        reset_default_client()
        assert isinstance(get_default_client(), GoogleNewsClient)
