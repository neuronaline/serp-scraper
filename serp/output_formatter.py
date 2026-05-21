"""Output formatting module for text and JSON modes.

This module provides consistent output formatting for CLI applications,
supporting both human-readable text output and machine-parseable JSON.
"""

import json
from dataclasses import dataclass
from typing import Optional

# Output modes
OUTPUT_TEXT = "text"
OUTPUT_JSON = "json"


@dataclass
class OutputError:
    """Structured error representation."""
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class TextFormatter:
    """Formatter for human-readable text output.

    Output format:
    - No emojis, ASCII-only characters
    - Consistent indentation (2 spaces)
    - '=' for section headers, '-' for separators
    """

    @staticmethod
    def format_search_results(
        results: list,
        query: str,
        source: Optional[str] = None,
        error: Optional[OutputError] = None,
    ) -> str:
        """Format search results as text."""
        if error:
            return TextFormatter._format_error("SEARCH RESULTS", error)

        source_name = TextFormatter._get_source_name(source)
        count = len(results)

        lines = [
            "=" * 50,
            "SEARCH RESULTS",
            "=" * 50,
            f"Query: {query}",
            f"Source: {source_name}",
            f"Count: {count}",
            "-" * 50,
        ]

        for r in results:
            lines.append(f"{r.rank}. {r.title}")
            lines.append(f"  URL: {r.url}")
            if r.description:
                lines.append(f"  Description: {r.description}")
            lines.append("")

        lines.append("-" * 50)
        return "\n".join(lines)

    @staticmethod
    def format_fetch(
        content: str,
        url: str,
        char_count: int,
        error: Optional[OutputError] = None,
        was_truncated: bool = False,
        original_length: Optional[int] = None,
    ) -> str:
        """Format fetched content as text."""
        if error:
            return TextFormatter._format_error("URL FETCH", error)

        lines = [
            "=" * 50,
            "URL FETCH",
            "=" * 50,
            f"URL: {url}",
            f"Characters: {char_count}",
        ]

        if was_truncated and original_length is not None:
            lines.append(f"Truncated: yes (original {original_length:,} chars)")

        lines += [
            "-" * 50,
            "Preview (first 30 lines):",
            "-" * 50,
        ]

        # Filter and limit content
        content_lines = [l for l in content.split("\n") if l.strip()]
        preview_lines = content_lines[:30] if content_lines else ["(no content)"]
        lines.extend(preview_lines)

        if len(content_lines) > 30:
            lines.append(f"\n... ({len(content_lines) - 30} more lines)")

        lines.append("-" * 50)
        return "\n".join(lines)

    @staticmethod
    def format_news(
        news_list: list,
        search_term: str,
        language: str,
        country: str,
        error: Optional[OutputError] = None,
    ) -> str:
        """Format news results as text."""
        if error:
            return TextFormatter._format_error("GOOGLE NEWS", error)

        count = len(news_list)

        lines = [
            "=" * 50,
            "GOOGLE NEWS",
            "=" * 50,
            f"Search Term: {search_term}",
            f"Language: {language}",
            f"Country: {country}",
            f"Count: {count}",
            "-" * 50,
        ]

        for i, r in enumerate(news_list, 1):
            lines.append(f"{i}. {r.title}")
            lines.append(f"  Source: {r.source}")
            display_url = r.original_url if r.original_url else r.url
            lines.append(f"  URL: {display_url}")
            date_str = r.published.strftime("%Y-%m-%d %H:%M") if r.published else "N/A"
            lines.append(f"  Date: {date_str}")
            if r.description:
                desc_preview = r.description[:80] + "..." if len(r.description) > 80 else r.description
                lines.append(f"  Description: {desc_preview}")
            lines.append("")

        lines.append("-" * 50)
        return "\n".join(lines)

    @staticmethod
    def format_scholar(
        results: list,
        query: str,
        error: Optional[OutputError] = None,
    ) -> str:
        """Format scholar results as text."""
        if error:
            return TextFormatter._format_error("GOOGLE SCHOLAR", error)

        count = len(results)

        lines = [
            "=" * 50,
            "GOOGLE SCHOLAR",
            "=" * 50,
            f"Query: {query}",
            f"Count: {count}",
            "-" * 50,
        ]

        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.title}")
            lines.append(f"  URL: {r.url}")
            if r.authors:
                authors_str = ", ".join(r.authors[:3])
                if len(r.authors) > 3:
                    authors_str += " et al."
                lines.append(f"  Authors: {authors_str}")
            if r.publication_year:
                lines.append(f"  Year: {r.publication_year}")
            if r.venue:
                lines.append(f"  Venue: {r.venue}")
            if r.citation_count:
                lines.append(f"  Citations: {r.citation_count}")
            if r.snippet:
                snippet_preview = r.snippet[:100] + "..." if len(r.snippet) > 100 else r.snippet
                lines.append(f"  Abstract: {snippet_preview}")
            lines.append("")

        lines.append("-" * 50)
        return "\n".join(lines)

    @staticmethod
    def _format_error(section: str, error: OutputError) -> str:
        """Format error message as text."""
        return "\n".join([
            "=" * 50,
            section,
            "=" * 50,
            f"ERROR: {error.code}",
            f"Message: {error.message}",
            "-" * 50,
        ])

    @staticmethod
    def _get_source_name(source: Optional[str]) -> str:
        """Get human-readable source name."""
        if source == "google":
            return "Google"
        elif source == "bing":
            return "Bing"
        return "Auto (Google -> Bing)"


class JSONFormatter:
    """Formatter for machine-parseable JSON output.

    Output structure:
    - status: "success" or "error"
    - type: result type (search_results, fetch, news)
    - Common fields: query/url, count, results
    - Error field when status is error
    """

    @staticmethod
    def format_search_results(
        results: list,
        query: str,
        source: Optional[str] = None,
        error: Optional[OutputError] = None,
    ) -> str:
        """Format search results as JSON."""
        if error:
            return JSONFormatter._format_error("search_results", error, query=query)

        return json.dumps({
            "status": "success",
            "type": "search_results",
            "query": query,
            "source": source or "auto",
            "count": len(results),
            "results": [r.to_dict() for r in results],
            "errors": [],
        }, indent=2, ensure_ascii=False)

    @staticmethod
    def format_fetch(
        content: str,
        url: str,
        char_count: int,
        error: Optional[OutputError] = None,
        was_truncated: bool = False,
        original_length: Optional[int] = None,
    ) -> str:
        """Format fetched content as JSON."""
        if error:
            return JSONFormatter._format_error("fetch", error, url=url)

        data = {
            "status": "success",
            "type": "fetch",
            "url": url,
            "char_count": char_count,
            "was_truncated": was_truncated,
            "original_length": original_length if was_truncated else None,
            "content_preview": "\n".join(content.split("\n")[:30]),
            "content_lines": len(content.split("\n")),
            "errors": [],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def format_news(
        news_list: list,
        search_term: str,
        language: str,
        country: str,
        error: Optional[OutputError] = None,
    ) -> str:
        """Format news results as JSON."""
        if error:
            return JSONFormatter._format_error("news", error, search_term=search_term)

        return json.dumps({
            "status": "success",
            "type": "news",
            "search_term": search_term,
            "language": language,
            "country": country,
            "count": len(news_list),
            "results": [r.to_dict() for r in news_list],
            "errors": [],
        }, indent=2, ensure_ascii=False)

    @staticmethod
    def format_scholar(
        results: list,
        query: str,
        error: Optional[OutputError] = None,
    ) -> str:
        """Format scholar results as JSON."""
        if error:
            return JSONFormatter._format_error("scholar", error, query=query)

        return json.dumps({
            "status": "success",
            "type": "scholar",
            "query": query,
            "count": len(results),
            "results": [r.to_dict() for r in results],
            "errors": [],
        }, indent=2, ensure_ascii=False)

    @staticmethod
    def _format_error(result_type: str, error: OutputError, **metadata) -> str:
        """Format error as JSON."""
        data = {
            "status": "error",
            "type": result_type,
            "error": error.to_dict(),
            "errors": [error.to_dict()],
        }
        data.update(metadata)
        return json.dumps(data, indent=2, ensure_ascii=False)


class OutputFormatter:
    """Central interface for output formatting.

    Usage:
        formatter = OutputFormatter()
        output = formatter.format_search_results(results, mode="json", query="test")
    """

    @staticmethod
    def format_search_results(
        results: list,
        mode: str = OUTPUT_TEXT,
        **kwargs
    ) -> str:
        """Format search results."""
        if mode == OUTPUT_JSON:
            return JSONFormatter.format_search_results(results, **kwargs)
        return TextFormatter.format_search_results(results, **kwargs)

    @staticmethod
    def format_fetch(
        content: str,
        url: str,
        mode: str = OUTPUT_TEXT,
        **kwargs
    ) -> str:
        """Format fetched content."""
        if mode == OUTPUT_JSON:
            return JSONFormatter.format_fetch(content, url, **kwargs)
        return TextFormatter.format_fetch(content, url, **kwargs)

    @staticmethod
    def format_news(
        news_list: list,
        mode: str = OUTPUT_TEXT,
        **kwargs
    ) -> str:
        """Format news results."""
        if mode == OUTPUT_JSON:
            return JSONFormatter.format_news(news_list, **kwargs)
        return TextFormatter.format_news(news_list, **kwargs)

    @staticmethod
    def format_scholar(
        results: list,
        query: str,
        mode: str = OUTPUT_TEXT,
        **kwargs
    ) -> str:
        """Format scholar results."""
        if mode == OUTPUT_JSON:
            return JSONFormatter.format_scholar(results, query, **kwargs)
        return TextFormatter.format_scholar(results, query, **kwargs)