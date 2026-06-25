"""Google News RSS scraping module.

This module provides functionality to scrape news from Google News using RSS feeds.
It follows the workflow described in GOOGLE_NEWS_NASIL_CALISIR.md:
1. Generate search queries from a company name
2. Build RSS URLs for Google News
3. Fetch and parse RSS XML responses
4. Deduplicate results
5. Return clean news lists

FETCH STRATEGY (Browser Only):
==============================
For article content extraction (get_news_with_content):
All article fetching uses Camoufox browser directly for reliability.
Previously there was a BS4-first-then-browser-fallback strategy, but
browser is now always used to ensure full content capture.

Note: The RSS feed itself uses HTTP (no JS required), but when extracting
full article content from individual news URLs, the browser strategy applies.

Example:
    >>> import asyncio
    >>> from serp.google_news import GoogleNewsClient
    >>>
    >>> async def main():
    ...     async with GoogleNewsClient() as client:
    ...         results = await client.get_news("Tesla")
    ...         for r in results:
    ...             print(f"{r.title} - {r.source}")
    >>>
    >>> asyncio.run(main())
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode, urlparse

import httpx
import markdownify

from .cache import get_cache
from .cleaning import clean_html, clean_markdown
from .config_pydantic import SerpConfig, get_default_config
from .parsers import _create_browser, _cleanup_browser, _create_page, _get_page_html, _check_captcha
from .types import RetryPolicy
from .utils import (
    CaptchaError,
    PageTimeoutError,
    ParseError,
    ProxyError,
    _random_user_agent,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class NewsResult:
    """Represents a single news item from Google News RSS.

    Attributes:
        title: News headline/title
        url: Direct link to the news article (Google News redirect URL)
        original_url: Original article URL (extracted from description if available)
        published: Publication date
        source: News source name (e.g., "BBC", "NTV")
        description: Optional news summary/snippet
        query: The search query that returned this result
    """

    title: str
    url: str
    published: datetime
    source: str = ""
    description: str = ""
    query: str = ""
    original_url: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "url": self.url,
            "original_url": self.original_url,
            "published": self.published.isoformat() if self.published else "",
            "source": self.source,
            "description": self.description,
            "query": self.query,
        }


@dataclass
class NewsSettings:
    """Configuration for Google News RSS scraping.

    Attributes:
        language: Language code for news (e.g., "tr" for Turkish, "en" for English)
        country: Country code for news (e.g., "TR", "US")
        time_range: Time range for news ("h"=hour, "d"=day, "w"=week, "m"=month)
    """

    language: str = "tr"
    country: str = "TR"
    time_range: str = "d"  # h=hour, d=day, w=week, m=month


class GoogleNewsClient:
    """Client for scraping Google News via RSS feeds.

    This client uses Google News RSS feeds to fetch news articles,
    which is more reliable and faster than web scraping.

    Example:
        >>> import asyncio
        >>> from serp.google_news import GoogleNewsClient
        >>>
        >>> async def main():
        ...     async with GoogleNewsClient() as client:
        ...         news = await client.get_news("Tesla")
        ...         for item in news:
        ...             print(f"{item.title} ({item.source})")
        >>>
        >>> asyncio.run(main())
    """

    # Default search query templates for generating queries from company name
    DEFAULT_QUERY_TEMPLATES = [
        "{company}",  # Just the company name
        "{company} haberleri",  # Company news
        "{company} şirket haberleri",  # Company business news
    ]

    # Google News RSS base URL
    RSS_BASE_URL = "https://news.google.com/rss/search"

    def __init__(
        self,
        config: Optional[SerpConfig] = None,
        use_cache: bool = True,
        language: str = "tr",
        country: str = "TR",
        time_range: str = "d",
    ):
        """Initialize Google News client.

        Args:
            config: SerpConfig instance for proxy/retry settings
            use_cache: Whether to use caching
            language: Language code (e.g., "tr", "en")
            country: Country code (e.g., "TR", "US")
            time_range: Time range ("h", "d", "w", "m")
        """
        self._config = config or get_default_config()
        self._use_cache = use_cache and self._config.cache.enabled
        self._cache = get_cache() if self._use_cache else None

        self._news_settings = NewsSettings(
            language=language,
            country=country,
            time_range=time_range,
        )

    def _generate_queries(self, news_search_term: str) -> list[str]:
        """Generate search queries from news search term.

        Args:
            news_search_term: Term to search news for

        Returns:
            List of search queries
        """
        queries = []
        for template in self.DEFAULT_QUERY_TEMPLATES:
            query = template.format(company=news_search_term)
            queries.append(query)
        return queries

    def _build_rss_url(self, query: str) -> str:
        """Build Google News RSS URL from search query.

        Args:
            query: Search query string

        Returns:
            Full RSS URL
        """
        params = {
            "q": query,
            "hl": self._news_settings.language,
            "gl": self._news_settings.country,
            "ceid": f"{self._news_settings.country}:{self._news_settings.language}",
        }
        # Add time range if specified (when parameter for Google News RSS)
        if self._news_settings.time_range:
            params["when"] = self._news_settings.time_range

        return f"{self.RSS_BASE_URL}?{urlencode(params)}"

    def _get_random_proxy(self) -> Optional[dict]:
        """Get a random proxy from configuration."""
        proxy_settings = self._config.proxy
        candidates = []

        # Add dataimpulse proxy if configured
        if proxy_settings.dataimpulse_gateway:
            proxy = self._build_dataimpulse_proxy()
            if proxy:
                candidates.append(proxy)

        # Add custom proxies
        for proxy_url in proxy_settings.custom_proxies:
            if not proxy_url:
                continue

            parsed = urlparse(proxy_url)
            if parsed.username and parsed.password:
                auth_part = f"{parsed.username}:{parsed.password}@"
            elif parsed.username:
                auth_part = f"{parsed.username}@"
            else:
                auth_part = ""

            scheme = parsed.scheme if parsed.scheme else "http"
            hostname = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""

            server = f"{scheme}://{auth_part}{hostname}{port}"

            candidates.append({
                "server": server,
                "username": parsed.username,
                "password": parsed.password,
            })

        if not candidates:
            return None

        import random
        return random.choice(candidates)

    def _build_dataimpulse_proxy(self) -> Optional[dict]:
        """Build DataImpulse proxy dict."""
        ps = self._config.proxy

        if not ps.dataimpulse_gateway or not ps.dataimpulse_user:
            return None

        is_sticky = ps.dataimpulse_sessttl is not None

        if is_sticky:
            port = 10000
        elif ps.dataimpulse_protocol == "socks5":
            port = 824
        else:
            port = 823

        username = ps.dataimpulse_user

        if ps.dataimpulse_country:
            username += f"__cr.{ps.dataimpulse_country}"

        if ps.dataimpulse_sessid and not is_sticky:
            username += f";sessid.{ps.dataimpulse_sessid}"

        if ps.dataimpulse_sessttl:
            username += f";sessttl.{ps.dataimpulse_sessttl}"

        scheme = "socks5" if ps.dataimpulse_protocol == "socks5" else "http"

        parsed = urlparse(ps.dataimpulse_gateway)
        hostname = parsed.hostname or "gw.dataimpulse.com"

        server = f"{scheme}://{hostname}:{port}"

        return {
            "server": server,
            "username": username,
            "password": ps.dataimpulse_pass or "",
        }

    def _build_proxy_url(self, proxy: Optional[dict]) -> Optional[str]:
        """Build proxy URL for httpx."""
        if not proxy:
            return None
        server = proxy.get("server")
        if not server:
            return None

        username = proxy.get("username")
        password = proxy.get("password")

        if username and password:
            parsed = urlparse(server)
            scheme = parsed.scheme or "http"
            hostname = parsed.hostname or ""
            port_part = f":{parsed.port}" if parsed.port else ""
            auth_part = f"{username}:{password}@"
            return f"{scheme}://{auth_part}{hostname}{port_part}"

        if not server.startswith(("http://", "socks5://", "socks4://")):
            return f"http://{server}"
        return server

    async def _fetch_rss(self, url: str, proxy_url: Optional[str]) -> str:
        """Fetch RSS feed content.

        Args:
            url: RSS feed URL
            proxy_url: Proxy URL (optional)

        Returns:
            Raw RSS XML content

        Raises:
            ProxyError: If fetch fails
            PageTimeoutError: If request times out
        """
        headers = {
            "User-Agent": _random_user_agent(),
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": f"{self._news_settings.language}-{self._news_settings.country},{self._news_settings.language};q=0.9",
        }

        timeout = float(self._config.search.timeout)

        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise ProxyError(f"RSS fetch failed with status {response.status_code}")
            return response.text

    async def _resolve_original_url(self, google_news_url: str, proxy_url: Optional[str]) -> str:
        """Resolve original article URL from Google News redirect URL.

        Google News RSS returns links like:
        https://news.google.com/rss/articles/CBMixAFBVV95cUx...

        When accessed with follow_redirects=False, the response Location header
        contains the original article URL.

        Args:
            google_news_url: Google News article URL
            proxy_url: Proxy URL (optional)

        Returns:
            Original article URL if redirect found, otherwise original Google News URL
        """
        headers = {
            "User-Agent": _random_user_agent(),
            "Accept": "text/html,application/xhtml+xml",
        }

        timeout = float(self._config.search.timeout)

        try:
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=timeout,
                follow_redirects=False,
                headers=headers,
            ) as client:
                response = await client.get(google_news_url)
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location", "")
                    if location:
                        # Handle relative redirects
                        if location.startswith("//"):
                            location = "https:" + location
                        elif location.startswith("/"):
                            # Parse the original URL to get base
                            parsed = urlparse(google_news_url)
                            location = f"{parsed.scheme}://{parsed.netloc}{location}"
                        return location
        except (httpx.HTTPError, OSError) as e:
            logger.debug(f"Failed to resolve original URL for {google_news_url}: {e}")

        return google_news_url

    def _parse_rss(self, xml_content: str, query: str) -> list[NewsResult]:
        """Parse RSS XML content into NewsResult objects.

        Args:
            xml_content: Raw RSS XML string
            query: The search query that produced this RSS

        Returns:
            List of NewsResult objects
        """
        from xml.etree import ElementTree as ET

        results = []

        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse RSS XML: {e}")
            return results

        # Find all item elements (RSS 2.0 format)
        channel = root.find("channel")
        if channel is None:
            return results

        for item in channel.findall("item"):
            title = ""
            link = ""
            pub_date = ""
            source = ""
            source_url = ""
            description = ""

            title_el = item.find("title")
            if title_el is not None and title_el.text:
                title = title_el.text.strip()

            link_el = item.find("link")
            if link_el is not None and link_el.text:
                link = link_el.text.strip()

            # Handle enclosure or media elements for link
            if not link:
                enclosure = item.find("enclosure")
                if enclosure is not None:
                    link = enclosure.get("url", "")

            pub_date_el = item.find("pubDate")
            if pub_date_el is not None and pub_date_el.text:
                pub_date = pub_date_el.text.strip()

            source_el = item.find("source")
            if source_el is not None:
                if source_el.text:
                    source = source_el.text.strip()
                # Extract source URL from the url attribute
                source_url = source_el.get("url", "")

            description_el = item.find("description")
            if description_el is not None and description_el.text:
                description = description_el.text.strip()

            if not title or not link:
                continue

            # Parse publication date
            published = self._parse_date(pub_date)

            # Use source_url as original_url if description extraction didn't find anything
            original_url = self._extract_original_url(description)
            if not original_url and source_url:
                original_url = source_url

            results.append(NewsResult(
                title=title,
                url=link,
                published=published,
                source=source,
                description=description,
                query=query,
                original_url=original_url,
            ))

        return results

    def _parse_date(self, date_str: str) -> datetime:
        """Parse RFC 2822 date format from RSS feeds.

        Args:
            date_str: Date string (e.g., "Sun, 11 May 2026 08:00:00 GMT")

        Returns:
            Parsed datetime or epoch if parsing fails
        """
        if not date_str:
            return datetime.min

        # RFC 2822 format: "Sun, 11 May 2026 08:00:00 GMT"
        # Format variants: with timezone offset, with GMT literal, ISO formats
        formats = [
            ("%a, %d %b %Y %H:%M:%S %z", False),
            ("%a, %d %b %Y %H:%M:%S GMT", True),
            ("%Y-%m-%dT%H:%M:%S%z", False),
            ("%Y-%m-%d %H:%M:%S", False),
        ]

        for fmt, needs_gmt_conversion in formats:
            try:
                date_to_parse = date_str
                if needs_gmt_conversion and "GMT" in date_str:
                    date_to_parse = date_str.replace("GMT", "+0000")
                    return datetime.strptime(date_to_parse, "%a, %d %b %Y %H:%M:%S %z")
                return datetime.strptime(date_to_parse, fmt)
            except (ValueError, TypeError):
                continue

        logger.warning(f"Failed to parse date: {date_str}")
        return datetime.min

    def _deduplicate(self, news_list: list[NewsResult]) -> list[NewsResult]:
        """Remove duplicate news items based on URL.

        Args:
            news_list: List of news items

        Returns:
            Deduplicated list
        """
        seen_urls = set()
        unique_news = []

        for news in news_list:
            # Normalize URL for comparison (prefer original_url if available)
            normalized_url = (news.original_url or news.url).lower().strip()
            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                unique_news.append(news)

        return unique_news

    def _extract_original_url(self, description: str) -> str:
        """Extract original article URL from description HTML.

        Google News RSS descriptions contain an <a href="..."> tag with
        the original article URL. This extracts it.

        Args:
            description: HTML description text

        Returns:
            Original article URL or empty string if not found
        """
        if not description:
            return ""

        # Match href attribute in anchor tags
        match = re.search(r'href="([^"]+)"', description)
        if match:
            return match.group(1)

        return ""

    async def _retry_failed(
        self,
        attempt: int,
        error: Exception,
        retry: RetryPolicy,
    ) -> bool:
        """Handle failed retry attempt with exponential backoff."""
        logger.warning(f"Google News attempt {attempt} failed: {error}")
        if attempt < retry.max_retries:
            delay = retry.calculate_delay(attempt)
            await asyncio.sleep(delay)
            return True
        return False

    async def get_news(
        self,
        news_search_term: str,
        max_results: int = 50,
        queries: Optional[list[str]] = None,
    ) -> list[NewsResult]:
        """Get news for a search term using Google News RSS.

        Args:
            news_search_term: Term to search news for
            max_results: Maximum number of news items to return
            queries: Custom list of queries to use (if None, generates from term)

        Returns:
            List of NewsResult objects, deduplicated

        Example:
            >>> results = await client.get_news("Tesla")
            >>> results = await client.get_news("Tesla", max_results=100)
            >>> results = await client.get_news("Tesla", queries=["Tesla haber", "Tesla electric"])
        """
        # Generate queries if not provided
        search_queries = queries or self._generate_queries(news_search_term)

        retry_policy = self._config.retry
        all_news: list[NewsResult] = []
        failed_queries: set[str] = set()

        for query in search_queries:
            # Check cache first
            cache_key = None
            if self._cache:
                cache_key = self._cache.make_key(
                    query=f"news:{query}",
                    source="google_news",
                )
                cached = self._cache.get(cache_key)
                if cached is not None:
                    logger.debug(f"Cache hit for news query='{query}'")
                    # Reconstruct NewsResult objects from cached dicts
                    for item in cached:
                        if isinstance(item, dict):
                            published_str = item.get("published", "")
                            item = NewsResult(
                                title=item.get("title", ""),
                                url=item.get("url", ""),
                                published=datetime.fromisoformat(published_str) if published_str else datetime.min,
                                source=item.get("source", ""),
                                description=item.get("description", ""),
                                query=item.get("query", query),
                                original_url=item.get("original_url", ""),
                            )
                        all_news.append(item)
                    continue

            # Fetch RSS for this query
            rss_url = self._build_rss_url(query)
            last_error = None

            for attempt in range(1, retry_policy.max_retries + 1):
                proxy = self._get_random_proxy()
                proxy_url = self._build_proxy_url(proxy)

                try:
                    xml_content = await self._fetch_rss(rss_url, proxy_url)
                    news_items = self._parse_rss(xml_content, query)

                    # Cache results
                    if self._cache and cache_key:
                        self._cache.set(cache_key, news_items, self._config.cache.ttl)

                    logger.info(f"Google News RSS fetched {len(news_items)} items for query='{query}'")
                    all_news.extend(news_items)
                    break

                except (ProxyError, PageTimeoutError, ParseError) as e:
                    last_error = e
                    if await self._retry_failed(attempt, e, retry_policy):
                        continue
                    break
                except (httpx.HTTPError, OSError) as e:
                    last_error = e
                    logger.error(f"Unexpected error fetching news: {e}")
                    break

            if last_error:
                failed_queries.add(query)
                logger.warning(f"Failed to fetch news for query '{query}': {last_error}")

        # Deduplicate and limit results
        unique_news = self._deduplicate(all_news)

        # Sort by publication date (newest first)
        unique_news.sort(key=lambda x: x.published, reverse=True)

        return unique_news[:max_results]

    async def get_news_with_content(
        self,
        company_name: str,
        max_results: int = 50,
        content_queries: Optional[list[str]] = None,
    ) -> list[NewsResult]:
        """Get news with full article content extraction.

        This method:
        1. Fetches news items via RSS (same as get_news)
        2. For each article URL, extracts full content using Camoufox browser

        Args:
            company_name: Name of the company
            max_results: Maximum number of news items
            content_queries: Not used (reserved for future query expansion)

        Returns:
            List of NewsResult objects with description field populated with article content

        Example:
            >>> results = await client.get_news_with_content("Tesla")
            >>> for r in results:
            ...     print(f"{r.title}: {r.description[:100]}...")
        """
        # Get news items via RSS (fast, reliable)
        news_items = await self.get_news(company_name, max_results)

        if not news_items:
            return []

        # For each news item, fetch full article content
        for item in news_items:
            # Determine which URL to fetch (prefer original_url if available)
            fetch_url = item.original_url or item.url

            try:
                content = await self._fetch_article_content(fetch_url)
                if content:
                    # Truncate content if too long (keep first ~500 chars as description)
                    item.description = content[:500] + ("..." if len(content) > 500 else "")
            except Exception as e:
                logger.debug(f"Failed to fetch article content for {fetch_url}: {e}")
                # Keep original description from RSS if content fetch fails
                pass

        return news_items

    async def _fetch_article_content(self, url: str) -> str:
        """Fetch article content using Camoufox browser.

        Args:
            url: Article URL to fetch

        Returns:
            Article content as Markdown string

        Raises:
            Exception: If browser fetch fails
        """
        from .parsers import _create_browser, _cleanup_browser, _create_page, _get_page_html, _check_captcha

        proxy = self._get_random_proxy()
        browser = await _create_browser(proxy, self._config.search.headless, block_images=True)
        if browser is None:
            raise ProxyError("Failed to start browser for article fetch")

        try:
            page = await _create_page(browser)
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(2)  # Wait for JS to execute

            page_content = await page.content()

            # Check for CAPTCHA
            current_url = (page.url or "").lower()
            if "sorry/app" in current_url or "/captcha/" in current_url:
                raise CaptchaError("CAPTCHA detected")

            # Clean HTML before conversion
            cleaned_html = clean_html(page_content)

            # Convert to Markdown
            markdown = markdownify.markdownify(cleaned_html, heading_style="ATX")

            # Post-clean markdown
            markdown = clean_markdown(markdown)

            return markdown

        finally:
            try:
                await _cleanup_browser(browser)
            except Exception:
                pass

    async def __aenter__(self) -> "GoogleNewsClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        pass


# Convenience functions

_default_client: Optional[GoogleNewsClient] = None


def get_default_client() -> GoogleNewsClient:
    """Get or create the default client instance."""
    global _default_client
    if _default_client is None:
        _default_client = GoogleNewsClient()
    return _default_client


def reset_default_client() -> None:
    """Reset the default client instance."""
    global _default_client
    _default_client = None


async def quick_news(
    news_search_term: str,
    max_results: int = 50,
    language: str = "tr",
    country: str = "TR",
) -> list[NewsResult]:
    """Convenience function for getting news using default client.

    Args:
        news_search_term: Term to search news for
        max_results: Maximum number of results
        language: Language code
        country: Country code

    Returns:
        List of NewsResult objects
    """
    async with GoogleNewsClient(language=language, country=country) as client:
        return await client.get_news(news_search_term, max_results)
