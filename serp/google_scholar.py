"""Google Scholar scraping module.

This module provides functionality to scrape academic papers from Google Scholar.
It uses browser automation (nodriver) to fetch and parse Scholar results.

Example:
    >>> import asyncio
    >>> from serp.google_scholar import ScholarClient
    >>>
    >>> async def main():
    ...     async with ScholarClient() as client:
    ...         results = await client.search_scholar("machine learning")
    ...         for r in results:
    ...             print(f"{r.title} - Cited by {r.citation_count}")
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

from .config import USER_AGENTS
from .config_pydantic import SerpConfig, get_default_config
from .parsers import (
    _check_captcha,
    _cleanup_browser,
    _create_browser,
    _extract_js_value,
)
from .types import RetryPolicy
from .utils import (
    PageTimeoutError,
    ProxyError,
    _random_user_agent,
)
from nodriver.cdp.fetch import (
    enable as fetch_enable,
    AuthRequired,
    continue_with_auth,
    AuthChallengeResponse,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScholarResult:
    """Represents a single academic paper from Google Scholar.

    Attributes:
        title: Paper title
        url: Direct link to the paper/article
        scholar_url: Google Scholar page URL for this paper
        snippet: Abstract/excerpt from the paper
        authors: List of author names
        publication_year: Year of publication (None if not available)
        venue: Journal, conference, or publication venue
        citation_count: Number of citations
        pdf_url: Direct PDF link if available (None otherwise)
        cluster_id: Google Scholar cluster ID for the paper
    """

    title: str
    url: str
    scholar_url: str = ""
    snippet: str = ""
    authors: list = None
    publication_year: Optional[int] = None
    venue: str = ""
    citation_count: int = 0
    pdf_url: Optional[str] = None
    cluster_id: str = ""

    def __post_init__(self):
        if self.authors is None:
            object.__setattr__(self, 'authors', [])

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "url": self.url,
            "scholar_url": self.scholar_url,
            "snippet": self.snippet,
            "authors": self.authors,
            "publication_year": self.publication_year,
            "venue": self.venue,
            "citation_count": self.citation_count,
            "pdf_url": self.pdf_url,
            "cluster_id": self.cluster_id,
        }


@dataclass
class ScholarSettings:
    """Configuration for Google Scholar scraping.

    Attributes:
        language: Language code for search (e.g., "en" for English)
        year_from: Start year for publication range (optional)
        year_to: End year for publication range (optional)
        sort_by: Sort order - "relevance" or "date"
    """

    language: str = "en"
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    sort_by: str = "relevance"  # "relevance" or "date"


# Google Scholar base URL
SCHOLAR_BASE_URL = "https://scholar.google.com/scholar"


class ScholarClient:
    """Client for scraping Google Scholar.

    This client uses browser automation (nodriver) to fetch and parse
    academic papers from Google Scholar.

    Example:
        >>> import asyncio
        >>> from serp.google_scholar import ScholarClient
        >>>
        >>> async def main():
        ...     async with ScholarClient() as client:
        ...         # Simple search
        ...         results = await client.search_scholar("machine learning")
        ...         for r in results:
        ...             print(f"{r.title} - Cited by {r.citation_count}")
        ...
        ...         # Advanced search with year range
        ...         results = await client.search_scholar(
        ...             "deep learning",
        ...             year_from=2020,
        ...             year_to=2024,
        ...         )
        >>>
        >>> asyncio.run(main())
    """

    # Result selectors based on site_analysis.json
    RESULT_CONTAINER_SELECTOR = "div.gs_r.gs_or.gs_scl"
    RESULT_ITEM_SELECTOR = "div.gs_ri"
    TITLE_SELECTOR = "h3.gs_rt"
    TITLE_LINK_SELECTOR = "h3.gs_rt a"
    SNIPPET_SELECTOR = "div.gs_rs"
    METADATA_SELECTOR = "div.gs_a"
    FOOTER_SELECTOR = "div.gs_fl.gs_flb"
    PDF_CONTAINER_SELECTOR = "div.gs_ggs.gs_fl"
    PDF_LINK_SELECTOR = "div.gs_ggs a"

    def __init__(
        self,
        config: Optional[SerpConfig] = None,
        use_cache: bool = True,
        language: str = "en",
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        sort_by: str = "relevance",
    ):
        """Initialize Google Scholar client.

        Args:
            config: SerpConfig instance for proxy/retry settings
            use_cache: Whether to use caching
            language: Language code (e.g., "en", "tr")
            year_from: Start year for publication range (optional)
            year_to: End year for publication range (optional)
            sort_by: Sort order - "relevance" or "date"
        """
        self._config = config or get_default_config()
        self._use_cache = use_cache and self._config.cache.enabled

        self._scholar_settings = ScholarSettings(
            language=language,
            year_from=year_from,
            year_to=year_to,
            sort_by=sort_by,
        )

    def _build_search_url(
        self,
        query: str,
        page_num: int = 0,
        advanced_params: Optional[dict] = None,
    ) -> str:
        """Build Google Scholar search URL.

        Args:
            query: Search query string
            page_num: Page number (0-indexed, default 0)
            advanced_params: Optional advanced search parameters

        Returns:
            Full Scholar search URL
        """
        params = {
            "q": query,
            "hl": self._scholar_settings.language,
            "start": page_num * 10,
        }

        # Add year range if specified
        if self._scholar_settings.year_from:
            params["as_ylo"] = str(self._scholar_settings.year_from)
        if self._scholar_settings.year_to:
            params["as_yhi"] = str(self._scholar_settings.year_to)

        # Add sorting
        if self._scholar_settings.sort_by == "date":
            params["sort"] = "date"

        # Add advanced search parameters if provided
        if advanced_params:
            params.update(advanced_params)

        return f"{SCHOLAR_BASE_URL}?{urlencode(params)}"

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

    async def _fetch_page(self, url: str, proxy: Optional[dict]) -> str:
        """Fetch Scholar page content using nodriver browser.

        Args:
            url: Scholar URL to fetch
            proxy: Proxy configuration (optional)

        Returns:
            Page HTML content

        Raises:
            PageTimeoutError: If page load times out
            ProxyError: If proxy fails
            ParseError: If CAPTCHA detected
        """
        browser = await _create_browser(proxy, self._config.search.headless)
        if browser is None:
            raise ProxyError("Failed to start browser for Scholar search")

        tab = None
        try:
            tab = await browser.get(url)

            # Wait for results to load
            try:
                await tab.select(self.RESULT_CONTAINER_SELECTOR, timeout=15)
            except Exception as e:
                logger.debug(f"Smart wait for Scholar results timed out: {e}")
                await asyncio.sleep(2)

            # Check for CAPTCHA
            current_url = (tab.url or "").lower()
            if "sorry/app" in current_url or "/captcha/" in current_url:
                from .utils import CaptchaError
                raise CaptchaError("CAPTCHA detected on Google Scholar")

            page_content = await tab.get_content()
            if _check_captcha(tab.url, page_content):
                from .utils import CaptchaError
                raise CaptchaError("CAPTCHA detected on Google Scholar")

            return page_content

        finally:
            if tab is not None:
                try:
                    await tab.close()
                except Exception:
                    pass

            try:
                await _cleanup_browser(browser)
            except Exception:
                pass

    async def _parse_results(self, tab, page_num: int) -> list[ScholarResult]:
        """Parse Google Scholar results using JavaScript evaluation.

        Args:
            tab: nodriver Tab with loaded page
            page_num: Current page number (0-indexed)

        Returns:
            List of ScholarResult objects
        """
        js_code = """
        (function() {
            const results = [];
            const containers = document.querySelectorAll('div.gs_r.gs_or.gs_scl');

            containers.forEach((container, idx) => {
                // Get the result item (gs_ri) or PDF container (gs_ggs)
                const resultItem = container.querySelector('div.gs_ri');
                const pdfContainer = container.querySelector('div.gs_ggs');

                if (!resultItem && !pdfContainer) return;

                // Get title and link
                const titleEl = resultItem ? resultItem.querySelector('h3.gs_rt a') : null;
                const title = titleEl ? (titleEl.innerText || titleEl.textContent || '') : '';
                const url = titleEl ? (titleEl.href || '') : '';

                // Get snippet/abstract
                const snippetEl = resultItem ? resultItem.querySelector('div.gs_rs') : null;
                const snippet = snippetEl ? (snippetEl.innerText || snippetEl.textContent || '') : '';

                // Get metadata (authors, year, venue)
                const metaEl = resultItem ? resultItem.querySelector('div.gs_a') : null;
                const metadata = metaEl ? (metaEl.innerText || metaEl.textContent || '') : '';

                // Get citation count from footer
                const footerEl = resultItem ? resultItem.querySelector('div.gs_fl.gs_flb') : null;
                let citationCount = 0;
                let pdfUrl = null;

                if (footerEl) {
                    const citeLink = footerEl.querySelector('a[href*="cites="]');
                    if (citeLink) {
                        const citeText = citeLink.innerText || citeLink.textContent || '';
                        const match = citeText.match(/Cited by (\\d+)/);
                        if (match) {
                            citationCount = parseInt(match[1], 10);
                        }
                    }

                    // Check for PDF link
                    const pdfLink = footerEl.querySelector('a[href*=".pdf"]') ||
                                   (pdfContainer ? pdfContainer.querySelector('a') : null);
                    if (pdfLink) {
                        pdfUrl = pdfLink.href;
                    }
                }

                // Get cluster ID from container attributes
                const clusterId = container.getAttribute('data-cid') || '';

                // Get scholar URL
                const scholarUrl = url ? 'https://scholar.google.com/scholar?q=info:' +
                              clusterId + ':scholar.google.com/&output=cite&scirp=0&hl=en' : '';

                results.push({
                    rank: idx + 1,
                    title: title,
                    url: url,
                    scholar_url: scholarUrl,
                    snippet: snippet,
                    metadata: metadata,
                    citation_count: citationCount,
                    pdf_url: pdfUrl,
                    cluster_id: clusterId
                });
            });

            return results;
        })()
        """

        try:
            js_results = await tab.evaluate(js_code)
            actual_results = _extract_js_value(js_results)

            if not actual_results or not isinstance(actual_results, list):
                return []

            results = []
            base_rank = page_num * 10

            for r in actual_results:
                if not isinstance(r, dict):
                    continue

                title = r.get('title', '')
                url = r.get('url', '')
                if not title or not url:
                    continue

                # Parse metadata to extract authors, year, venue
                metadata = r.get('metadata', '')
                authors, year, venue = self._parse_metadata(metadata)

                results.append(ScholarResult(
                    title=title,
                    url=url,
                    scholar_url=r.get('scholar_url', ''),
                    snippet=r.get('snippet', ''),
                    authors=authors,
                    publication_year=year,
                    venue=venue,
                    citation_count=r.get('citation_count', 0),
                    pdf_url=r.get('pdf_url'),
                    cluster_id=r.get('cluster_id', ''),
                ))

            return results

        except Exception as e:
            logger.error(f"Failed to parse Scholar results: {e}")
            return []

    def _parse_metadata(self, metadata: str) -> tuple:
        """Parse metadata string to extract authors, year, and venue.

        Args:
            metadata: Raw metadata string like "Author1, Author2, ... - Journal, Year"

        Returns:
            Tuple of (authors list, year int or None, venue string)
        """
        authors = []
        year = None
        venue = ""

        if not metadata:
            return authors, year, venue

        # Split by " - " which typically separates authors from venue+year
        parts = metadata.split(" - ")

        if len(parts) >= 1:
            # First part is usually authors
            author_part = parts[0].strip()
            if author_part:
                # Authors are typically comma or semicolon separated
                # Handle patterns like "Author1, Author2, Author3"
                author_list = re.split(r'[,;]', author_part)
                authors = [a.strip() for a in author_list if a.strip()]

        if len(parts) >= 2:
            # Second part typically contains venue and year
            venue_part = parts[-1].strip()

            # Try to extract year (4-digit number)
            year_match = re.search(r'\b(19|20)\d{2}\b', venue_part)
            if year_match:
                try:
                    year = int(year_match.group(0))
                except ValueError:
                    pass

                # Extract venue by removing year
                venue = re.sub(r'\b(19|20)\d{2}\b', '', venue_part).strip()
                # Clean up any leading/trailing punctuation
                venue = venue.strip(' ,-')

        return authors, year, venue

    async def _retry_failed(
        self,
        attempt: int,
        error: Exception,
        retry: RetryPolicy,
    ) -> bool:
        """Handle failed retry attempt with exponential backoff."""
        logger.warning(f"Scholar attempt {attempt} failed: {error}")
        if attempt < retry.max_retries:
            delay = retry.calculate_delay(attempt)
            await asyncio.sleep(delay)
            return True
        return False

    async def search_scholar(
        self,
        query: str,
        max_results: int = 50,
        advanced_params: Optional[dict] = None,
    ) -> list[ScholarResult]:
        """Search Google Scholar for academic papers.

        Args:
            query: Search query string
            max_results: Maximum number of results to return (default 50)
            advanced_params: Optional advanced search parameters:
                - as_epq: Exact phrase
                - as_oq: At least one of words
                - as_eq: Without words
                - as_sauthors: Author search
                - as_publication: Publication name

        Returns:
            List of ScholarResult objects

        Example:
            >>> results = await client.search_scholar("machine learning")
            >>> results = await client.search_scholar(
            ...     "deep learning",
            ...     year_from=2020,
            ...     year_to=2024
            ... )
            >>> results = await client.search_scholar(
            ...     "neural networks",
            ...     advanced_params={"as_sauthors": "Hinton"}
            ... )
        """
        retry_policy = self._config.retry
        all_results: list[ScholarResult] = []
        page_num = 0

        while len(all_results) < max_results:
            # Build URL for current page
            url = self._build_search_url(query, page_num, advanced_params)

            last_error = None

            for attempt in range(1, retry_policy.max_retries + 1):
                proxy = self._get_random_proxy()

                try:
                    # Fetch page content
                    browser = await _create_browser(proxy, self._config.search.headless)
                    if browser is None:
                        raise ProxyError("Failed to start browser for Scholar search")

                    tab = None
                    try:
                        tab = await browser.get(url)

                        # Wait for results
                        try:
                            await tab.select(self.RESULT_CONTAINER_SELECTOR, timeout=15)
                        except Exception as e:
                            logger.debug(f"Smart wait for Scholar results timed out: {e}")
                            await asyncio.sleep(2)

                        # Check for CAPTCHA
                        current_url = (tab.url or "").lower()
                        if "sorry/app" in current_url or "/captcha/" in current_url:
                            from .utils import CaptchaError
                            raise CaptchaError("CAPTCHA detected on Google Scholar")

                        page_content = await tab.get_content()
                        if _check_captcha(tab.url, page_content):
                            from .utils import CaptchaError
                            raise CaptchaError("CAPTCHA detected on Google Scholar")

                        # Parse results
                        results = await self._parse_results(tab, page_num)

                        if not results:
                            # No more results available
                            logger.debug(f"No more Scholar results for page {page_num}")
                            return all_results[:max_results]

                        all_results.extend(results)
                        logger.info(
                            f"Scholar search: page {page_num} returned {len(results)} results "
                            f"for query='{query}'"
                        )

                        break

                    finally:
                        if tab is not None:
                            try:
                                await tab.close()
                            except Exception:
                                pass

                        try:
                            await _cleanup_browser(browser)
                        except Exception:
                            pass

                except Exception as e:
                    last_error = e
                    if await self._retry_failed(attempt, e, retry_policy):
                        continue
                    break

            if last_error:
                logger.warning(
                    f"Failed to fetch Scholar results for query '{query}' page {page_num}: {last_error}"
                )
                break

            # Move to next page
            page_num += 1

            # Safety limit to prevent infinite loops
            if page_num > 100:
                logger.warning(f"Reached maximum page limit (100) for Scholar query '{query}'")
                break

        return all_results[:max_results]

    async def __aenter__(self) -> "ScholarClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        pass


# Convenience functions

_default_client: Optional[ScholarClient] = None


def get_default_client() -> ScholarClient:
    """Get or create the default client instance."""
    global _default_client
    if _default_client is None:
        _default_client = ScholarClient()
    return _default_client


def reset_default_client() -> None:
    """Reset the default client instance."""
    global _default_client
    _default_client = None


async def quick_scholar(
    query: str,
    max_results: int = 50,
    language: str = "en",
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> list[ScholarResult]:
    """Convenience function for searching Scholar using default client.

    Args:
        query: Search query string
        max_results: Maximum number of results
        language: Language code
        year_from: Start year (optional)
        year_to: End year (optional)

    Returns:
        List of ScholarResult objects
    """
    async with ScholarClient(
        language=language,
        year_from=year_from,
        year_to=year_to,
    ) as client:
        return await client.search_scholar(query, max_results)
