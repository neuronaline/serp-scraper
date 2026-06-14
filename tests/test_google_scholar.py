"""Tests for Google Scholar module."""

import pytest
from datetime import datetime

from serp.google_scholar import (
    ScholarClient,
    ScholarResult,
    ScholarSettings,
    get_default_client,
    reset_default_client,
)


class TestScholarResult:
    """Tests for ScholarResult dataclass."""

    def test_creation_with_all_fields(self):
        result = ScholarResult(
            title="Deep Learning", url="https://example.com/paper",
            scholar_url="https://scholar.google.com/scholar?q=info:abc",
            snippet="Abstract...", authors=["Smith", "Doe"],
            publication_year=2024, venue="NeurIPS",
            citation_count=150, pdf_url="https://example.com/paper.pdf",
            cluster_id="abc123",
        )
        assert result.title == "Deep Learning"
        assert result.authors == ["Smith", "Doe"]
        assert result.citation_count == 150
        assert result.publication_year == 2024

    def test_defaults(self):
        result = ScholarResult(title="Test", url="https://example.com")
        assert result.scholar_url == ""
        assert result.snippet == ""
        assert result.authors == []
        assert result.publication_year is None
        assert result.venue == ""
        assert result.citation_count == 0
        assert result.pdf_url is None

    def test_to_dict(self):
        result = ScholarResult(title="Paper", url="https://e.com", authors=["A"], publication_year=2024)
        d = result.to_dict()
        assert d["title"] == "Paper"
        assert d["url"] == "https://e.com"
        assert d["authors"] == ["A"]
        assert d["publication_year"] == 2024
        # Verify all keys present (including defaults)
        assert d["scholar_url"] == ""
        assert d["snippet"] == ""
        assert d["venue"] == ""
        assert d["citation_count"] == 0
        assert d["pdf_url"] is None
        assert d["cluster_id"] == ""


class TestScholarSettings:
    """Tests for ScholarSettings defaults and overrides."""

    def test_defaults(self):
        s = ScholarSettings()
        assert s.language == "en"
        assert s.year_from is None
        assert s.sort_by == "relevance"

    def test_custom(self):
        s = ScholarSettings(language="tr", year_from=2020, year_to=2024, sort_by="date")
        assert s.language == "tr"
        assert s.year_from == 2020
        assert s.sort_by == "date"


class TestScholarClient:
    """Tests for ScholarClient core methods."""

    def test_initialization_defaults(self):
        client = ScholarClient()
        assert client._scholar_settings.language == "en"
        assert client._scholar_settings.sort_by == "relevance"

    def test_custom_settings(self):
        client = ScholarClient(language="de", year_from=2020, year_to=2023, sort_by="date")
        assert client._scholar_settings.language == "de"
        assert client._scholar_settings.year_from == 2020

    def test_with_config(self):
        from serp.config_pydantic import SerpConfig
        config = SerpConfig(max_retries=5)
        client = ScholarClient(config=config)
        assert client._config is config
        assert client._config.retry.max_retries == 5

    def test_build_search_url_basic(self):
        client = ScholarClient()
        url = client._build_search_url("machine learning")
        assert "scholar.google.com" in url
        assert "q=machine+learning" in url
        assert "hl=en" in url

    def test_build_search_url_with_year_range(self):
        client = ScholarClient(year_from=2020, year_to=2024)
        url = client._build_search_url("deep learning")
        assert "as_ylo=2020" in url
        assert "as_yhi=2024" in url

    def test_build_search_url_sort_by_date(self):
        client = ScholarClient(sort_by="date")
        assert "sort=date" in client._build_search_url("test")

    def test_build_search_url_with_page(self):
        client = ScholarClient()
        url = client._build_search_url("test", page_num=2)
        assert "start=20" in url

    def test_build_search_url_advanced_params(self):
        client = ScholarClient()
        url = client._build_search_url("test", advanced_params={"as_epq": "exact phrase"})
        assert "as_epq=exact+phrase" in url

    def test_parse_metadata(self):
        client = ScholarClient()
        authors, year, venue = client._parse_metadata("Smith, John, Doe, Jane - Nature, 2024")
        assert "Smith" in authors and "Doe" in authors
        assert year == 2024
        assert "Nature" in venue

    def test_parse_metadata_empty(self):
        client = ScholarClient()
        authors, year, venue = client._parse_metadata("")
        assert authors == [] and year is None and venue == ""

    def test_parse_metadata_no_authors_format(self):
        """Metadata like 'Some Conference, 2024' with no ' - ' separator."""
        client = ScholarClient()
        authors, year, venue = client._parse_metadata("Some Conference, 2024")
        # No " - " separator → entire string treated as authors; year not extracted
        assert authors == ["Some Conference", "2024"]
        assert year is None
        assert venue == ""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        async with ScholarClient() as client:
            assert client is not None


class TestModuleFunctions:
    """Tests for module-level singleton pattern."""

    def test_singleton(self):
        reset_default_client()
        c1 = get_default_client()
        c2 = get_default_client()
        assert c1 is c2 and isinstance(c1, ScholarClient)

    def test_reset_creates_new(self):
        reset_default_client()
        c1 = get_default_client()
        reset_default_client()
        c2 = get_default_client()
        assert c1 is not c2


class TestProxyBuilding:
    """Test proxy-related methods."""

    def test_build_dataimpulse_proxy_no_config(self):
        from serp.config_pydantic import SerpConfig
        config = SerpConfig(dataimpulse_gateway=None, dataimpulse_user=None)
        client = ScholarClient(config=config)
        assert client._build_dataimpulse_proxy() is None

    def test_get_random_proxy_no_config(self):
        from serp.config_pydantic import SerpConfig
        config = SerpConfig(dataimpulse_gateway=None, custom_proxies="")
        client = ScholarClient(config=config)
        assert client._get_random_proxy() is None
