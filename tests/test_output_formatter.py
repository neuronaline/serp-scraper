"""Tests for output formatter module.

Tests public API behavior following TEST_GOVERNANCE.md principles:
- Test through public interfaces
- Avoid brittle assertions
- Focus on structure and behavior
"""

import json
import pytest
from datetime import datetime

from serp.output_formatter import (
    OutputError,
    OutputFormatter,
    TextFormatter,
    JSONFormatter,
    OUTPUT_TEXT,
    OUTPUT_JSON,
)


class TestOutputError:
    """Tests for OutputError dataclass."""

    def test_output_error_creation(self):
        """Test creating an OutputError."""
        error = OutputError(code="TEST_ERROR", message="Test message")
        assert error.code == "TEST_ERROR"
        assert error.message == "Test message"

    def test_output_error_to_dict(self):
        """Test converting OutputError to dictionary."""
        error = OutputError(code="TEST_ERROR", message="Test message")
        result = error.to_dict()
        assert result == {"code": "TEST_ERROR", "message": "Test message"}


class TestTextFormatterSearchResults:
    """Tests for TextFormatter.format_search_results."""

    def test_format_search_results_basic(self):
        """Test basic search results formatting."""
        from serp.types import SearchResult

        results = [
            SearchResult(rank=1, title="Title 1", url="https://example.com/1", description="Desc 1"),
            SearchResult(rank=2, title="Title 2", url="https://example.com/2", description="Desc 2"),
        ]

        output = TextFormatter.format_search_results(
            results=results,
            query="test query",
            source="google",
        )

        assert "SEARCH RESULTS" in output
        assert "Query: test query" in output
        assert "Source: Google" in output
        assert "Count: 2" in output
        assert "Title 1" in output
        assert "Title 2" in output

    def test_format_search_results_with_error(self):
        """Test formatting search results with error."""
        error = OutputError(code="TEST_ERROR", message="Test error occurred")
        output = TextFormatter.format_search_results(
            results=[],
            query="test",
            error=error,
        )

        assert "ERROR: TEST_ERROR" in output
        assert "Test error occurred" in output

    def test_format_search_results_no_source(self):
        """Test formatting without source."""
        from serp.types import SearchResult

        results = [SearchResult(rank=1, title="T", url="https://example.com")]
        output = TextFormatter.format_search_results(results=results, query="test")

        assert "Auto (Google -> Bing)" in output

    def test_format_search_results_empty(self):
        """Test formatting empty results."""
        output = TextFormatter.format_search_results(
            results=[],
            query="test",
            source="google",
        )

        assert "Count: 0" in output


class TestTextFormatterFetch:
    """Tests for TextFormatter.format_fetch."""

    def test_format_fetch_basic(self):
        """Test basic fetch formatting."""
        output = TextFormatter.format_fetch(
            content="Hello world\nLine 2",
            url="https://example.com",
            char_count=17,
        )

        assert "URL FETCH" in output
        assert "URL: https://example.com" in output
        assert "Characters: 17" in output

    def test_format_fetch_with_truncation(self):
        """Test formatting with truncation info."""
        output = TextFormatter.format_fetch(
            content="A" * 1000,
            url="https://example.com",
            char_count=500,
            was_truncated=True,
            original_length=1000,
        )

        assert "Truncated: yes" in output
        assert "original 1,000 chars" in output

    def test_format_fetch_with_error(self):
        """Test formatting fetch with error."""
        error = OutputError(code="FETCH_ERROR", message="Failed to fetch")
        output = TextFormatter.format_fetch(
            content="",
            url="https://example.com",
            char_count=0,
            error=error,
        )

        assert "ERROR: FETCH_ERROR" in output


class TestTextFormatterNews:
    """Tests for TextFormatter.format_news."""

    def test_format_news_basic(self):
        """Test basic news formatting."""
        from serp.google_news import NewsResult

        news_list = [
            NewsResult(
                title="News Title",
                url="https://example.com/news",
                published=datetime(2026, 5, 11, 10, 30, 0),
                source="BBC",
                description="News description",
                query="test",
            )
        ]

        output = TextFormatter.format_news(
            news_list=news_list,
            search_term="test",
            language="en",
            country="US",
        )

        assert "GOOGLE NEWS" in output
        assert "Search Term: test" in output
        assert "Language: en" in output
        assert "Country: US" in output
        assert "News Title" in output
        assert "BBC" in output

    def test_format_news_with_error(self):
        """Test formatting news with error."""
        error = OutputError(code="NEWS_ERROR", message="News fetch failed")
        output = TextFormatter.format_news(
            news_list=[],
            search_term="test",
            language="en",
            country="US",
            error=error,
        )

        assert "ERROR: NEWS_ERROR" in output


class TestJSONFormatterSearchResults:
    """Tests for JSONFormatter.format_search_results."""

    def test_format_search_results_basic(self):
        """Test basic search results JSON formatting."""
        from serp.types import SearchResult

        results = [
            SearchResult(rank=1, title="Title 1", url="https://example.com/1", description="Desc 1"),
        ]

        output = JSONFormatter.format_search_results(
            results=results,
            query="test query",
            source="google",
        )

        data = json.loads(output)
        assert data["status"] == "success"
        assert data["type"] == "search_results"
        assert data["query"] == "test query"
        assert data["source"] == "google"
        assert data["count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Title 1"

    def test_format_search_results_with_error(self):
        """Test formatting with error returns error JSON."""
        error = OutputError(code="TEST_ERROR", message="Test error")
        output = JSONFormatter.format_search_results(
            results=[],
            query="test",
            error=error,
        )

        data = json.loads(output)
        assert data["status"] == "error"
        assert data["error"]["code"] == "TEST_ERROR"


class TestJSONFormatterFetch:
    """Tests for JSONFormatter.format_fetch."""

    def test_format_fetch_basic(self):
        """Test basic fetch JSON formatting."""
        output = JSONFormatter.format_fetch(
            content="Hello world\nLine 2",
            url="https://example.com",
            char_count=17,
        )

        data = json.loads(output)
        assert data["status"] == "success"
        assert data["type"] == "fetch"
        assert data["url"] == "https://example.com"
        assert data["char_count"] == 17
        assert data["was_truncated"] is False

    def test_format_fetch_with_truncation(self):
        """Test formatting with truncation info."""
        output = JSONFormatter.format_fetch(
            content="A" * 1000,
            url="https://example.com",
            char_count=500,
            was_truncated=True,
            original_length=1000,
        )

        data = json.loads(output)
        assert data["was_truncated"] is True
        assert data["original_length"] == 1000


class TestJSONFormatterNews:
    """Tests for JSONFormatter.format_news."""

    def test_format_news_basic(self):
        """Test basic news JSON formatting."""
        from serp.google_news import NewsResult

        news_list = [
            NewsResult(
                title="News Title",
                url="https://example.com/news",
                published=datetime(2026, 5, 11, 10, 30, 0),
                source="BBC",
                description="News description",
                query="test",
            )
        ]

        output = JSONFormatter.format_news(
            news_list=news_list,
            search_term="test",
            language="en",
            country="US",
        )

        data = json.loads(output)
        assert data["status"] == "success"
        assert data["type"] == "news"
        assert data["search_term"] == "test"
        assert data["language"] == "en"
        assert data["country"] == "US"
        assert data["count"] == 1


class TestOutputFormatter:
    """Tests for OutputFormatter central interface."""

    def test_format_search_results_text_mode(self):
        """Test OutputFormatter with text mode."""
        from serp.types import SearchResult

        results = [SearchResult(rank=1, title="T", url="https://example.com")]
        output = OutputFormatter.format_search_results(
            results=results,
            mode=OUTPUT_TEXT,
            query="test",
        )

        assert "SEARCH RESULTS" in output

    def test_format_search_results_json_mode(self):
        """Test OutputFormatter with JSON mode."""
        from serp.types import SearchResult

        results = [SearchResult(rank=1, title="T", url="https://example.com")]
        output = OutputFormatter.format_search_results(
            results=results,
            mode=OUTPUT_JSON,
            query="test",
        )

        data = json.loads(output)
        assert data["status"] == "success"

    def test_format_fetch_text_mode(self):
        """Test format_fetch with text mode."""
        output = OutputFormatter.format_fetch(
            content="test",
            url="https://example.com",
            char_count=4,
            mode=OUTPUT_TEXT,
        )

        assert "URL FETCH" in output

    def test_format_fetch_json_mode(self):
        """Test format_fetch with JSON mode."""
        output = OutputFormatter.format_fetch(
            content="test",
            url="https://example.com",
            char_count=4,
            mode=OUTPUT_JSON,
        )

        data = json.loads(output)
        assert data["status"] == "success"

    def test_format_news_text_mode(self):
        """Test format_news with text mode."""
        from serp.google_news import NewsResult

        news_list = [NewsResult(
            title="T",
            url="https://example.com",
            published=datetime.now(),
        )]
        output = OutputFormatter.format_news(
            news_list=news_list,
            search_term="test",
            language="en",
            country="US",
            mode=OUTPUT_TEXT,
        )

        assert "GOOGLE NEWS" in output

    def test_format_news_json_mode(self):
        """Test format_news with JSON mode."""
        from serp.google_news import NewsResult

        news_list = [NewsResult(
            title="T",
            url="https://example.com",
            published=datetime.now(),
        )]
        output = OutputFormatter.format_news(
            news_list=news_list,
            search_term="test",
            language="en",
            country="US",
            mode=OUTPUT_JSON,
        )

        data = json.loads(output)
        assert data["status"] == "success"


class TestFormatterConstants:
    """Tests for formatter constants."""

    def test_output_text_constant(self):
        """Test OUTPUT_TEXT constant."""
        assert OUTPUT_TEXT == "text"

    def test_output_json_constant(self):
        """Test OUTPUT_JSON constant."""
        assert OUTPUT_JSON == "json"