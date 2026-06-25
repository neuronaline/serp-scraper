"""Main client class for SERP module.

This module provides a high-level SerpClient class that encapsulates
all functionality with a simple, consistent API.

FETCH STRATEGY (Browser Only):
==============================
All page fetching uses Camoufox browser directly — no BS4 fallback.
This ensures JavaScript-rendered pages are always captured correctly.

Previously there was a BS4-first-then-browser-fallback strategy, but
BS4 often returned incomplete/partial content, so browser is now the
default and only method for reliability.
"""

import logging
import random
from typing import Optional
from urllib.parse import urlparse

from .cache import get_cache as _get_cache, reset_cache
from .config_pydantic import SerpConfig, get_default_config, reset_default_config
from .parsers import _fetch_browser_impl, _search_impl
from .types import CacheSettings, ProxySettings, RetryPolicy, SearchResult, SearchSettings
from .utils import (
    CaptchaError,
    PageTimeoutError,
    ParseError,
    ProxyError,
    set_log_level,
)

logger = logging.getLogger(__name__)


class SerpClient:
    """High-level SERP client with simple API.

    This is the recommended interface for using the serp library.
    It provides a clean, consistent API with sensible defaults.

    Example:
        >>> import asyncio
        >>> from serp import SerpClient
        >>>
        >>> async def main():
        ...     async with SerpClient() as client:
        ...         results = await client.search("python tutorial")
        ...         for r in results:
        ...             print(f"{r.rank}. {r.title}")
        >>>
        >>> asyncio.run(main())

    Or with custom configuration:

        >>> config = SerpConfig(
        ...     proxy_file="my_proxies.json",
        ...     log_level="DEBUG",
        ...     max_retries=5,
        ... )
        >>> client = SerpClient(config)
    """

    def __init__(
        self,
        config: Optional[SerpConfig] = None,
        headless: bool = False,
        use_cache: bool = True,
        cache_ttl: int = 86400,
        source: Optional[str] = None,
        max_retries: Optional[int] = None,
        timeout: int = 30,
        log_level: str = "WARNING",
    ):
        """Initialize the SERP client.

        Args:
            config: SerpConfig instance. If provided, other parameters are ignored.
            headless: Whether to run browser in headless mode (default: False)
            use_cache: Whether to use caching (default: True)
            cache_ttl: Cache time-to-live in seconds (default: 86400 = 24h)
            source: Search source - "google", "bing", or None for auto (default: None)
            max_retries: Maximum number of retries (default: 3)
            timeout: Request timeout in seconds (default: 30)
            log_level: Logging level (default: "WARNING")

        Example:
            >>> client = SerpClient(headless=True)
            >>> client = SerpClient(config=my_config)
        """
        # Handle config - either provided or created from parameters
        if config is not None:
            self._config = config
        else:
            # Build config from parameters
            self._config = SerpConfig(
                headless=headless,
                cache_ttl=cache_ttl,
                cache_enabled=use_cache,
                source=source,
                max_retries=max_retries or 3,
                timeout=timeout,
                log_level=log_level,
            )

        # Apply log level
        set_log_level(self._config.logging.level)

        # Cache reference
        self._cache = None if not self._config.cache.enabled else _get_cache()

    def _get_random_proxy(self) -> Optional[dict]:
        """Get a random proxy based on configuration.

        Returns:
            Proxy dict with 'server', 'username', 'password' keys,
            or None if no proxy is configured.

        DataImpulse format:
        - Rotating: port 823 (HTTP/HTTPS) or 824 (SOCKS5)
        - Sticky: ports 10000-20000
        - Username format: login__cr.country;sessid.123;sessttl.60
        """
        proxy_settings = self._config.proxy
        candidates = []

        # If DataImpulse is configured and preferred, use it
        if proxy_settings.strategy == "dataimpulse_first" and proxy_settings.dataimpulse_gateway:
            proxy = self._build_dataimpulse_proxy()
            if proxy:
                logger.debug(f"Selected DataImpulse proxy: {proxy['server']}")
                return proxy

        # Add dataimpulse to candidates if configured
        if proxy_settings.dataimpulse_gateway:
            proxy = self._build_dataimpulse_proxy()
            if proxy:
                candidates.append(proxy)

        # Add custom proxies
        for proxy_url in proxy_settings.custom_proxies:
            if not proxy_url:
                continue

            # Parse user:pass from url if present
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
            logger.debug("No proxies configured")
            return None

        proxy = random.choice(candidates)
        logger.debug(f"Selected proxy: {proxy['server']}")
        return proxy

    async def search(
        self,
        query: str,
        page_num: int = 1,
        method: Optional[str] = None,
        source: Optional[str] = None,
        use_cache: Optional[bool] = None,
    ) -> list[SearchResult]:
        """Search for query and return results.

        Note: Google and Bing SERP searches ALWAYS use browser (Camoufox) because
        these search engines require JavaScript to render results.

        Args:
            query: Search query string
            page_num: Page number (1-based, default: 1)
            method: Deprecated, ignored (SERP searches always use browser).
                For HTTP-based page fetching, use client.fetch() instead.
            source: Search engine - "google", "bing", or None (auto, default)
            use_cache: Whether to use cache. None uses client default.

        Returns:
            List of SearchResult objects

        Raises:
            CaptchaError: Captcha detected after all retries
            PageTimeoutError: Page load timeout
            ParseError: Failed to parse results
            ProxyError: All proxies failed

        Example:
            >>> results = await client.search("python tutorial")
            >>> results = await client.search("python", page_num=2, source="bing")
        """
        # Determine effective settings
        effective_source = source or self._config.search.source
        effective_cache = use_cache if use_cache is not None else self._config.cache.enabled

        # SERP searches (Google/Bing) ALWAYS use browser - JS required for rendering
        # method parameter is ignored for SERP searches
        return await self._search_browser(query, page_num, effective_source, effective_cache)

    async def _search_browser(
        self,
        query: str,
        page_num: int,
        source: Optional[str],
        use_cache: bool,
    ) -> list[SearchResult]:
        """Browser-based search using Camoufox."""
        # Check cache first
        if use_cache and self._cache:
            search_sources = (source,) if source else ("google", "bing")
            for src in search_sources:
                key = self._cache.make_key(query=query, page_num=page_num, source=src)
                cached = self._cache.get(key)
                if cached is not None:
                    logger.debug(f"Cache hit for query='{query}', page={page_num} (source={src})")
                    # Create SearchResult objects, using explicit source to override any cached source
                    results = []
                    for r in cached:
                        results.append(SearchResult(
                            rank=r["rank"],
                            title=r["title"],
                            url=r["url"],
                            description=r.get("description", ""),
                            source=src,
                        ))
                    return results

        retry = self._config.retry

        sources_to_try = []
        if source == "bing":
            sources_to_try = [("bing", "Bing")]
        elif source == "google":
            sources_to_try = [("google", "Google")]
        else:
            sources_to_try = [("google", "Google"), ("bing", "Bing fallback")]

        last_error = None
        for src, src_name in sources_to_try:
            for attempt in range(1, retry.max_retries + 1):
                proxy = self._get_random_proxy()
                try:
                    results = await _search_impl(
                        query, page_num, proxy, self._config.search.headless, src
                    )

                    # Cache results
                    if use_cache and self._cache:
                        cache_key = self._cache.make_key(query=query, page_num=page_num, source=src)
                        self._cache.set(cache_key, results, self._config.cache.ttl)

                    logger.info(f"{src_name} search successful for query='{query}', page={page_num}")
                    return [SearchResult(**r, source=src) for r in results]

                except CaptchaError as e:
                    # CAPTCHA won't go away by retrying on the same source.
                    # Break immediately so the next search source is tried.
                    last_error = e
                    break
                except (PageTimeoutError, ParseError) as e:
                    last_error = e
                    if await self._retry_failed(attempt, e, src_name, retry):
                        continue
                    break
                except Exception as e:
                    last_error = e
                    if await self._retry_failed(attempt, e, src_name, retry):
                        continue
                    break

            # Only break out of outer loop when a specific source was explicitly requested.
            # When source is None or "auto", continue to the next source (Bing fallback).
            if source is not None and source != "auto":
                break

        if last_error:
            raise last_error
        raise ParseError(f"All search attempts failed for query '{query}'")

    async def _search_http(
        self,
        query: str,
        page_num: int,
        source: Optional[str],
        use_cache: bool,
    ) -> list[SearchResult]:
        """HTTP-based search using httpx — DEPRECATED.

        This method relied on BS4 (BeautifulSoup) parsing and is no longer
        maintained. Kept for backward compatibility only — always returns empty.
        """
        logger.warning("_search_http is deprecated. SERP searches always use browser.")
        return []

    def _build_dataimpulse_proxy(self) -> Optional[dict]:
        """Build DataImpulse proxy dict with proper port and username parameters.

        DataImpulse username format supports parameters:
        - __cr.country: Country targeting (e.g., __cr.de for Germany)
        - sessid.123: Session ID for rotating proxy with sticky session (~30 min)
        - sessttl.60: Session TTL in minutes (1-120) for sticky proxy

        Port selection:
        - HTTP/HTTPS rotating: 823
        - SOCKS5 rotating: 824
        - Sticky (sessttl): 10000-20000 (sessttl required)

        Note: sessid and sessttl are mutually exclusive - sessid is for rotating
        proxies with session affinity, sessttl is for dedicated sticky proxies.
        """
        ps = self._config.proxy

        if not ps.dataimpulse_gateway or not ps.dataimpulse_user:
            return None

        # Determine if this is a sticky proxy (sessttl) or rotating (sessid or neither)
        is_sticky = ps.dataimpulse_sessttl is not None

        # Determine port based on proxy type
        if is_sticky:
            # Sticky proxy - use port in 10000-20000 range
            port = 10000  # Default sticky port
        elif ps.dataimpulse_protocol == "socks5":
            port = 824  # SOCKS5 rotating
        else:
            port = 823  # HTTP/HTTPS rotating

        # Build username with DataImpulse parameter format
        # Format: login__cr.country (country attached directly with __)
        # Additional params like sessid, sessttl are appended with ;
        username = ps.dataimpulse_user

        if ps.dataimpulse_country:
            # Country parameter attached directly to username with __
            username += f"__cr.{ps.dataimpulse_country}"

        # sessid and sessttl are mutually exclusive
        if ps.dataimpulse_sessid and not is_sticky:
            # sessid only makes sense for rotating proxies (not sticky)
            username += f";sessid.{ps.dataimpulse_sessid}"

        if ps.dataimpulse_sessttl:
            username += f";sessttl.{ps.dataimpulse_sessttl}"

        # Determine scheme
        scheme = "socks5" if ps.dataimpulse_protocol == "socks5" else "http"

        # Parse gateway to get hostname
        from urllib.parse import urlparse
        parsed = urlparse(ps.dataimpulse_gateway)
        hostname = parsed.hostname or "gw.dataimpulse.com"

        server = f"{scheme}://{hostname}:{port}"

        return {
            "server": server,
            "username": username,
            "password": ps.dataimpulse_pass or "",
        }

    def _build_proxy_url(self, proxy: Optional[dict]) -> Optional[str]:
        """Build proxy URL for httpx.

        Only includes auth when BOTH username and password are present.
        DataImpulse requires both for user:pass auth; IP whitelist needs neither.
        """
        if not proxy:
            return None
        server = proxy.get("server")
        if not server:
            return None

        username = proxy.get("username")
        password = proxy.get("password")

        # Only include auth if BOTH username and password are present
        if username and password:
            from urllib.parse import urlparse
            parsed = urlparse(server)
            scheme = parsed.scheme or "http"
            hostname = parsed.hostname or ""
            port_part = f":{parsed.port}" if parsed.port else ""
            auth_part = f"{username}:{password}@"
            return f"{scheme}://{auth_part}{hostname}{port_part}"

        # No auth - just return server as-is, but ensure it has a scheme
        if not server.startswith(("http://", "socks5://", "socks4://")):
            return f"http://{server}"
        return server

    async def _retry_failed(
        self,
        attempt: int,
        error: Exception,
        func_name: str,
        retry: RetryPolicy,
    ) -> bool:
        """Handle failed retry attempt."""
        logger.warning(f"{func_name} attempt {attempt} failed: {error}")
        if attempt < retry.max_retries:
            import asyncio
            delay = retry.calculate_delay(attempt)
            await asyncio.sleep(delay)
            return True
        return False

    async def fetch(
        self,
        url: str,
        use_cache: Optional[bool] = None,
        prefer_browser: bool = True,
        compress: bool = False,
    ) -> str:
        """Fetch a URL and return content as Markdown.

        Uses Camoufox browser directly for reliable content extraction.
        Previously there was a BS4-HTTP fallback, but browser is now used
        for all fetches to ensure JavaScript-rendered content is captured.

        The `prefer_browser` parameter is kept for backward compatibility
        but is ignored — browser is always used.

        Args:
            url: Target URL
            use_cache: Whether to use cache. None uses client default.
            prefer_browser: Deprecated, ignored (browser is always used).
            compress: If True and content exceeds 10K chars, compress by
                      taking head, middle, and tail portions of the content.
                      The return value remains a plain string (use the
                      standalone :func:`compress_content` function from
                      ``serp`` if you need metadata about the truncation).

        Returns:
            Page content as Markdown string (optionally compressed)

        Raises:
            ProxyError: All proxies failed
            PageTimeoutError: Page load timeout
        """
        effective_cache = use_cache if use_cache is not None else self._config.cache.enabled

        if effective_cache and self._cache:
            cache_key = self._cache.make_key(url=url)
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for url='{url}'")
                # Apply compression to cached content if requested (cache always
                # stores the full uncompressed content so that subsequent fetches
                # with compress=False get the complete page)
                if compress:
                    from serp.compression import compress_content
                    cached, _ = compress_content(cached)
                return cached

        retry = self._config.retry

        # All retryable errors
        RETRYABLE_ERRORS = (
            CaptchaError, PageTimeoutError, ProxyError, ParseError,
            TimeoutError, OSError
        )

        for attempt in range(1, retry.max_retries + 1):
            proxy = self._get_random_proxy()
            logger.debug(f"Fetch attempt {attempt}: proxy={proxy.get('server') if proxy else 'None'}")

            try:
                # Always use browser (Camoufox) for reliability
                result = await _fetch_browser_impl(url, proxy, self._config.search.headless)

                # Cache the ORIGINAL (uncompressed) content so that subsequent
                # fetches with compress=False get the full content
                if effective_cache and self._cache:
                    cache_key = self._cache.make_key(url=url)
                    self._cache.set(cache_key, result, self._config.cache.ttl)

                # Apply compression if requested (after caching — return value
                # only, the cache always holds the full original)
                if compress:
                    from serp.compression import compress_content
                    result, _ = compress_content(result)

                return result

            except RETRYABLE_ERRORS as e:
                if attempt < retry.max_retries:
                    if await self._retry_failed(attempt, e, "Fetch", retry):
                        continue
                raise

        raise ProxyError(f"All {retry.max_retries} fetch attempts failed")

    async def __aenter__(self) -> "SerpClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager.

        Note: Browser instances are managed per-request and cleaned up
        automatically by the implementation methods (_search_impl, etc.).
        The cache is a global singleton managed at module level.
        """
        pass

    def __enter__(self) -> "SerpClient":
        """Enter sync context manager (for backward compatibility)."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit sync context manager.

        Note: For async operations, use 'async with SerpClient()' instead.
        This sync version is provided for backward compatibility only.
        """
        pass


# Module-level convenience functions that use default client

_default_client: Optional[SerpClient] = None


def get_default_client() -> SerpClient:
    """Get or create the default client instance."""
    global _default_client
    if _default_client is None:
        _default_client = SerpClient()
    return _default_client


def reset_default_client() -> None:
    """Reset the default client instance."""
    global _default_client
    _default_client = None


async def quick_search(
    query: str,
    page_num: int = 1,
    source: Optional[str] = None,
    method: Optional[str] = None,
) -> list[SearchResult]:
    """Convenience function for search using default client.

    Note: SERP searches (Google/Bing) always use browser (Camoufox) because
    search engines require JavaScript to render results. The 'method' parameter
    is accepted for backward compatibility but is ignored.

    Args:
        query: Search query string
        page_num: Page number (1-based, default: 1)
        source: Search source - "google", "bing", or None (auto)
        method: Deprecated, ignored (SERP searches always use browser)

    Returns:
        List of SearchResult objects

    Note:
        For repeated use, create a SerpClient instance instead to avoid
        re-initializing configuration on each call.
    """
    client = get_default_client()
    return await client.search(query, page_num, method=method, source=source)


async def quick_fetch(url: str, prefer_browser: bool = True, compress: bool = False) -> str:
    """Convenience function for fetch using default client.

    Always uses Camoufox browser for reliability.
    The `prefer_browser` parameter is kept for backward compatibility.

    Args:
        url: Target URL
        prefer_browser: Deprecated, ignored (browser is always used).
        compress: Whether to compress long content (>10K chars)

    Returns:
        Page content as Markdown string (optionally compressed)

    Note:
        For repeated use, create a SerpClient instance instead.
    """
    client = get_default_client()
    return await client.fetch(url, prefer_browser=prefer_browser, compress=compress)


async def quick_search_http(
    query: str,
    page_num: int = 1,
    source: Optional[str] = None,
    use_cache: bool = True,
) -> list[SearchResult]:
    """DEPRECATED. SERP searches always use browser now."""
    client = get_default_client()
    return await client._search_http(query, page_num, source, use_cache)