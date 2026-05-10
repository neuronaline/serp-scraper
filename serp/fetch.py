"""Fetch functions for SERP module."""

import asyncio
from typing import Optional

from .config import load_config
from .cache import get_cache
from .parsers import _fetch_browser_impl
from .utils import (
    MAX_RETRIES,
    CaptchaError,
    PageTimeoutError,
    ParseError,
    ProxyError,
    _retry_failed,
    _fetch_http,
    logger,
)


async def fetch(
    url: str,
    proxy_file: str = "proxies.json",
    headless: bool = False,
    prefer_browser: bool = True,
    use_cache: bool = True,
    cache_ttl: int = 86400,
) -> str:
    """
    Fetch a URL and return content as Markdown.
    Tries HTTP first if prefer_browser=False, otherwise uses browser directly.

    Args:
        url: Target URL
        proxy_file: Path to proxies.json
        headless: Whether to run browser in headless mode
        prefer_browser: If True, use browser directly. If False, try HTTP first then fall back to browser.
        use_cache: Whether to use cache (default True)
        cache_ttl: Cache time-to-live in seconds (default 86400 = 24 hours)

    Returns:
        Page content as Markdown string

    Raises:
        ProxyError: All proxies failed
        PageTimeoutError: Page load timeout
    """
    # Try cache first if enabled
    if use_cache:
        cache = get_cache()
        cache_key = cache.make_key(url=url)
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for url='{url}'")
            return cached

    # If not preferring browser, try simple HTTP fetch first
    if not prefer_browser:
        try:
            result = await _fetch_http(url, proxy_file)
            if use_cache:
                cache.set(cache_key, result, cache_ttl)
            return result
        except Exception as e:
            logger.debug(f"HTTP fetch failed, falling back to browser: {e}")

    # Use browser-based fetch
    result = await _fetch_browser(url, proxy_file, headless)

    # Cache the result
    if use_cache:
        cache.set(cache_key, result, cache_ttl)

    return result


async def _fetch_browser(
    url: str,
    proxy_file: str,
    headless: bool,
) -> str:
    """Browser-based fetch using nodriver."""
    config = load_config(proxy_file)

    if not config.has_proxies:
        logger.warning("No proxies configured - proceeding without proxy")

    # Errors that should be retried with proxy rotation
    RETRYABLE_ERRORS = (CaptchaError, PageTimeoutError, ProxyError, ParseError, TimeoutError, OSError)

    for attempt in range(1, MAX_RETRIES + 1):
        proxy = config.get_random_proxy()
        if proxy is None:
            logger.warning(f"Fetch attempt {attempt}: No proxy available, proceeding without proxy")
        else:
            logger.debug(f"Fetch attempt {attempt}: proxy={proxy['server']}")

        try:
            result = await _fetch_browser_impl(url, proxy, headless)
            return result
        except Exception as e:
            # Check if error is retryable
            if isinstance(e, RETRYABLE_ERRORS):
                if await _retry_failed(attempt, e, "Fetch"):
                    continue
                # All retries exhausted - raise appropriate error
                if isinstance(e, PageTimeoutError):
                    raise
                elif isinstance(e, CaptchaError):
                    raise
                else:
                    raise ProxyError(f"All {MAX_RETRIES} attempts failed: {e}") from e
            else:
                # Non-retryable error (KeyboardInterrupt, MemoryError, etc.) - re-raise immediately
                raise