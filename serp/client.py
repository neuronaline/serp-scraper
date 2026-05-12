"""Main client class for SERP module.

This module provides a high-level SerpClient class that encapsulates
all functionality with a simple, consistent API.
"""

import logging
import random
from typing import Optional
from urllib.parse import urlparse

from .cache import get_cache as _get_cache, reset_cache
from .config_pydantic import SerpConfig, get_default_config, reset_default_config
from .http_search import _search_google_simple, _search_simple_impl_bing
from .parsers import _fetch_browser_impl, _search_impl
from .types import CacheSettings, ProxySettings, RetryPolicy, SearchResult, SearchSettings
from .utils import (
    MAX_RETRIES,
    RETRY_DELAY_MAX,
    RETRY_DELAY_MIN,
    USE_EXPONENTIAL_BACKOFF,
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

        Args:
            query: Search query string
            page_num: Page number (1-based, default: 1)
            method: Search method - "browser" (nodriver), "http" (httpx), or None (auto, default)
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

        # Determine if proxy should be used
        use_proxy = self._config.proxy.dataimpulse_gateway or self._config.proxy.custom_proxies

        if method == "http" or (method is None and not use_proxy):
            # Use HTTP-based search
            return await self._search_http(query, page_num, effective_source, effective_cache)
        else:
            # Use browser-based search (default, more reliable)
            return await self._search_browser(query, page_num, effective_source, effective_cache)

    async def _search_browser(
        self,
        query: str,
        page_num: int,
        source: Optional[str],
        use_cache: bool,
    ) -> list[SearchResult]:
        """Browser-based search using nodriver."""
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
                    break

            if source is not None:
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
        """HTTP-based search using httpx."""
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
            sources_to_try = [("bing",)]
        elif source == "google":
            sources_to_try = [("google",)]
        else:
            sources_to_try = [("google",), ("bing",)]

        last_error = None
        for src, in sources_to_try:
            for attempt in range(1, retry.max_retries + 1):
                proxy = self._get_random_proxy()
                try:
                    if src == "google":
                        proxy_url = self._build_proxy_url(proxy) if proxy else None
                        results = await _search_google_simple(
                            query, page_num, proxy_url,
                            {}, use_cache, self._config.cache.ttl
                        )
                    else:
                        proxy_url = self._build_proxy_url(proxy) if proxy else None
                        results = await _search_simple_impl_bing(query, page_num, proxy_url or "")

                    # Empty results without an error mean the page was loaded
                    # but no results were found (e.g., consent/bot-detection page).
                    # Treat as parse failure so retry/failover kicks in.
                    if not results:
                        raise ParseError(
                            f"No results found for query '{query}' on {src} page {page_num}"
                        )

                    if use_cache and self._cache:
                        cache_key = self._cache.make_key(query=query, page_num=page_num, source=src)
                        self._cache.set(cache_key, results, self._config.cache.ttl)

                    logger.info(f"search_simple: {src} successful for query='{query}', page={page_num}")
                    return [SearchResult(**r, source=src) for r in results]

                except CaptchaError as e:
                    # CAPTCHA won't clear on retry; try next source
                    last_error = e
                    break
                except Exception as e:
                    last_error = e
                    if await self._retry_failed(attempt, e, src.upper(), retry):
                        continue
                    break

            if source is not None:
                break

        if last_error:
            raise last_error
        raise ParseError(f"All search attempts failed for query '{query}'")

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
        username_parts = [ps.dataimpulse_user]

        if ps.dataimpulse_country:
            username_parts.append(f"__cr.{ps.dataimpulse_country}")

        # sessid and sessttl are mutually exclusive
        if ps.dataimpulse_sessid and not is_sticky:
            # sessid only makes sense for rotating proxies (not sticky)
            username_parts.append(f"sessid.{ps.dataimpulse_sessid}")

        if ps.dataimpulse_sessttl:
            username_parts.append(f"sessttl.{ps.dataimpulse_sessttl}")

        username = ";".join(username_parts)

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
    ) -> str:
        """Fetch a URL and return content as Markdown.

        Args:
            url: Target URL
            use_cache: Whether to use cache. None uses client default.
            prefer_browser: If True, use browser. If False, try HTTP first.

        Returns:
            Page content as Markdown string

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
                return cached

        retry = self._config.retry

        RETRYABLE_ERRORS = (CaptchaError, PageTimeoutError, ProxyError, ParseError, TimeoutError, OSError)

        for attempt in range(1, retry.max_retries + 1):
            proxy = self._get_random_proxy()
            logger.debug(f"Fetch attempt {attempt}: proxy={proxy.get('server') if proxy else 'None'}")

            try:
                if prefer_browser:
                    result = await _fetch_browser_impl(url, proxy, self._config.search.headless)
                else:
                    # HTTP first, browser fallback on failure
                    result = await self.fetch_with_fallback(url, use_cache=False)

                if effective_cache and self._cache:
                    cache_key = self._cache.make_key(url=url)
                    self._cache.set(cache_key, result, self._config.cache.ttl)

                return result

            except RETRYABLE_ERRORS as e:
                if attempt < retry.max_retries:
                    if await self._retry_failed(attempt, e, "Fetch", retry):
                        continue
                raise

        raise ProxyError(f"All {retry.max_retries} fetch attempts failed")

    async def fetch_with_fallback(
        self,
        url: str,
        use_cache: Optional[bool] = None,
    ) -> str:
        """Fetch a URL using HTTP first, falling back to browser on failure.

        This method implements the HTTP-first-then-browser fallback pattern:
        1. Try HTTP fetch (httpx)
        2. On any retryable error, immediately fall back to browser (nodriver)
        3. Cache the successful result

        Args:
            url: Target URL
            use_cache: Whether to use cache. None uses client default.

        Returns:
            Page content as Markdown string

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
                return cached

        retry = self._config.retry

        # Errors that trigger browser fallback
        FALLBACK_ERRORS = (CaptchaError, PageTimeoutError, ProxyError, ParseError, TimeoutError, ConnectionError)

        for attempt in range(1, retry.max_retries + 1):
            proxy = self._get_random_proxy()
            logger.debug(f"Fetch with fallback attempt {attempt}: proxy={proxy.get('server') if proxy else 'None'}")

            try:
                # Phase 1: Try HTTP fetch
                result = await self._fetch_http_impl(url, proxy)

                # Validate response - empty/minimal content suggests blocked page
                if not result or len(result) < 50:
                    logger.debug(f"HTTP returned minimal content ({len(result) if result else 0} chars), falling back to browser")
                    raise ParseError("Empty or minimal content received from HTTP")

            except FALLBACK_ERRORS as e:
                # Phase 2: Immediate fallback to browser
                logger.debug(f"HTTP fetch failed (attempt {attempt}), falling back to browser: {e}")
                try:
                    result = await _fetch_browser_impl(url, proxy, self._config.search.headless)
                except Exception as browser_error:
                    # Browser also failed - retry whole cycle
                    if attempt < retry.max_retries:
                        if await self._retry_failed(attempt, browser_error, "Fetch", retry):
                            continue
                    raise browser_error

                # Browser succeeded - return without caching fallback result
                return result

            # Cache successful HTTP result (only when HTTP succeeds directly)
            if effective_cache and self._cache:
                cache_key = self._cache.make_key(url=url)
                self._cache.set(cache_key, result, self._config.cache.ttl)

            return result

        raise ProxyError(f"All {retry.max_retries} fetch attempts failed")

    async def _fetch_http_impl(self, url: str, proxy: Optional[dict]) -> str:
        """Simple HTTP fetch using httpx."""
        import httpx
        from .utils import _random_user_agent

        proxy_url = self._build_proxy_url(proxy)

        headers = {
            "User-Agent": _random_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=float(self._config.search.timeout),
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            if response.status_code != 200:
                raise ProxyError(f"HTTP {response.status_code}")

            import markdownify
            return markdownify.markdownify(response.text, heading_style="ATX")

    async def __aenter__(self) -> "SerpClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager."""
        pass

    def __enter__(self) -> "SerpClient":
        """Enter sync context manager (for backward compatibility)."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit sync context manager."""
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

    Args:
        query: Search query string
        page_num: Page number (1-based, default: 1)
        source: Search source - "google", "bing", or None (auto)
        method: Search method - "browser", "http", or None (auto)

    Returns:
        List of SearchResult objects

    Note:
        For repeated use, create a SerpClient instance instead to avoid
        re-initializing configuration on each call.
    """
    client = get_default_client()
    return await client.search(query, page_num, method=method, source=source)


async def quick_fetch(url: str, prefer_browser: bool = True) -> str:
    """Convenience function for fetch using default client.

    Args:
        url: Target URL
        prefer_browser: Whether to prefer browser-based fetch

    Returns:
        Page content as Markdown string

    Note:
        For repeated use, create a SerpClient instance instead.
    """
    client = get_default_client()
    return await client.fetch(url, prefer_browser=prefer_browser)


async def quick_search_http(
    query: str,
    page_num: int = 1,
    source: Optional[str] = None,
    use_cache: bool = True,
) -> list[SearchResult]:
    """Convenience function for HTTP-based search.

    This is a shortcut for quick_search(..., method="http").

    Args:
        query: Search query string
        page_num: Page number (1-based)
        source: Search source - "google", "bing", or None (auto)
        use_cache: Whether to use cache

    Returns:
        List of SearchResult objects
    """
    client = get_default_client()
    return await client.search(query, page_num, method="http", source=source, use_cache=use_cache)