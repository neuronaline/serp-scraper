"""Tests for output formatter module."""

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
    def test_creation_and_to_dict(self):
        error = OutputError(code="ERR", message="Failed")
        assert error.code == "ERR"
        assert error.to_dict() == {"code": "ERR", "message": "Failed"}


class TestTextFormatter:
    """Tests for TextFormatter output modes."""

    def test_search_results_basic(self):
        from serp.types import SearchResult
        results = [
            SearchResult(rank=1, title="T1", url="https://e.com/1", description="D1"),
            SearchResult(rank=2, title="T2", url="https://e.com/2", description="D2"),
        ]
        output = TextFormatter.format_search_results(results=results, query="test", source="google")
        assert "SEARCH RESULTS" in output
        assert "Query: test" in output
        assert "Count: 2" in output
        assert "T1" in output and "T2" in output

    def test_search_results_with_error(self):
        error = OutputError(code="ERR", message="Oops")
        output = TextFormatter.format_search_results(results=[], query="test", error=error)
        assert "ERROR: ERR" in output
        assert "Oops" in output

    def test_search_results_empty(self):
        output = TextFormatter.format_search_results(results=[], query="test", source="google")
        assert "Count: 0" in output

    def test_fetch_basic(self):
        output = TextFormatter.format_fetch(content="Hello", url="https://e.com", char_count=5)
        assert "URL: https://e.com" in output
        assert "Characters: 5" in output

    def test_fetch_with_truncation(self):
        output = TextFormatter.format_fetch(
            content="A" * 1000, url="https://e.com", char_count=500,
            was_truncated=True, original_length=1000,
        )
        assert "Truncated: yes" in output
        assert "original 1,000 chars" in output

    def test_news_basic(self):
        from serp.google_news import NewsResult
        news = [NewsResult(title="N1", url="https://e.com", published=datetime(2026, 5, 11, 10, 30), source="BBC")]
        output = TextFormatter.format_news(news_list=news, search_term="test", language="en", country="US")
        assert "GOOGLE NEWS" in output
        assert "N1" in output
        assert "BBC" in output


class TestJSONFormatter:
    """Tests for JSONFormatter output modes."""

    def test_search_results_basic(self):
        from serp.types import SearchResult
        results = [SearchResult(rank=1, title="T1", url="https://e.com")]
        output = JSONFormatter.format_search_results(results=results, query="test", source="google")
        data = json.loads(output)
        assert data["status"] == "success"
        assert data["type"] == "search_results"
        assert data["count"] == 1
        assert data["results"][0]["title"] == "T1"

    def test_search_results_with_error(self):
        error = OutputError(code="ERR", message="Fail")
        output = JSONFormatter.format_search_results(results=[], query="test", error=error)
        data = json.loads(output)
        assert data["status"] == "error"
        assert data["error"]["code"] == "ERR"

    def test_fetch_basic(self):
        output = JSONFormatter.format_fetch(content="Hello", url="https://e.com", char_count=5)
        data = json.loads(output)
        assert data["status"] == "success"
        assert data["type"] == "fetch"
        assert data["was_truncated"] is False

    def test_fetch_with_truncation(self):
        output = JSONFormatter.format_fetch(
            content="A" * 1000, url="https://e.com", char_count=500,
            was_truncated=True, original_length=1000,
        )
        data = json.loads(output)
        assert data["was_truncated"] is True
        assert data["original_length"] == 1000

    def test_news_basic(self):
        from serp.google_news import NewsResult
        news = [NewsResult(title="N1", url="https://e.com", published=datetime(2026, 5, 11, 10, 30))]
        output = JSONFormatter.format_news(news_list=news, search_term="test", language="en", country="US")
        data = json.loads(output)
        assert data["status"] == "success"
        assert data["type"] == "news"
        assert data["count"] == 1


class TestOutputFormatter:
    """Test OutputFormatter dispatches to correct formatter by mode."""

    @pytest.mark.parametrize("mode,check", [
        (OUTPUT_TEXT, lambda o: "SEARCH RESULTS" in o),
        (OUTPUT_JSON, lambda o: json.loads(o)["status"] == "success"),
    ])
    def test_format_search_results(self, mode, check):
        from serp.types import SearchResult
        results = [SearchResult(rank=1, title="T", url="https://e.com")]
        output = OutputFormatter.format_search_results(results=results, mode=mode, query="test")
        assert check(output)

    @pytest.mark.parametrize("mode,check", [
        (OUTPUT_TEXT, lambda o: "URL FETCH" in o),
        (OUTPUT_JSON, lambda o: json.loads(o)["status"] == "success"),
    ])
    def test_format_fetch(self, mode, check):
        output = OutputFormatter.format_fetch(content="test", url="https://e.com", char_count=4, mode=mode)
        assert check(output)

    @pytest.mark.parametrize("mode,check", [
        (OUTPUT_TEXT, lambda o: "GOOGLE NEWS" in o),
        (OUTPUT_JSON, lambda o: json.loads(o)["status"] == "success"),
    ])
    def test_format_news(self, mode, check):
        from serp.google_news import NewsResult
        news = [NewsResult(title="T", url="https://e.com", published=datetime.now())]
        output = OutputFormatter.format_news(
            news_list=news, search_term="test", language="en", country="US", mode=mode,
        )
        assert check(output)
