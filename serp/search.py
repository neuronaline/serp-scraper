"""Main search function for SERP module."""

from typing import Optional

from .config import load_config
from .cache import get_cache
from .parsers import _search_impl
from .utils import (
    MAX_RETRIES,
    CaptchaError,
    PageTimeoutError,
    ParseError,
    _retry_failed,
    logger,
)


async def search(
    query: str,
    page_num: int = 1,
    proxy_file: str = "proxies.json",
    headless: bool = False,
    use_cache: bool = True,
    cache_ttl: int = 86400,
    source: Optional[str] = None,
) -> list[dict]:
    """Search Google and/or Bing and return organic results.

    Args:
        query: Search query string
        page_num: Page number (1-based)
        proxy_file: Path to proxies.json
        headless: Whether to run browser in headless mode
        use_cache: Whether to use cache (default True)
        cache_ttl: Cache time-to-live in seconds (default 86400 = 24 hours)
        source: Search source - "google", "bing", or None for auto (google first, bing fallback)

    Returns:
        List of dicts with keys: rank, title, url, description

    Raises:
        CaptchaError: Captcha after all retries
        PageTimeoutError: Page load timeout
        ParseError: Failed to parse results
    """
    if use_cache:
        cache = get_cache()
        search_sources = (source,) if source else ("google", "bing")
        for src in search_sources:
            key = cache.make_key(query=query, page_num=page_num, source=src)
            cached = cache.get(key)
            if cached is not None:
                logger.debug(f"Cache hit for query='{query}', page={page_num} (source={src})")
                return cached

    config = load_config(proxy_file)

    if not config.has_proxies:
        logger.warning("No proxies configured - proceeding without proxy")

    # Determine search order based on source parameter
    sources_to_try = []
    if source == "bing":
        sources_to_try = [("bing", "Bing")]
    elif source == "google":
        sources_to_try = [("google", "Google")]
    else:
        # Auto mode: google first, then bing fallback
        sources_to_try = [("google", "Google"), ("bing", "Bing fallback")]

    last_error: Optional[Exception] = None
    for src, src_name in sources_to_try:
        for attempt in range(1, MAX_RETRIES + 1):
            proxy = config.get_random_proxy()
            try:
                engine = None if src == "google" else src
                results = await _search_impl(query, page_num, proxy, headless, engine)
                if use_cache:
                    cache = get_cache()
                    cache.set(cache.make_key(query=query, page_num=page_num, source=src),
                             results, cache_ttl)
                logger.info(f"{src_name} search successful for query='{query}', page={page_num}")
                return results
            except (CaptchaError, PageTimeoutError, ParseError) as e:
                last_error = e
                if await _retry_failed(attempt, e, src_name):
                    continue
                break
            except Exception as e:
                last_error = e
                break

        # If we get here with a source-specific preference, stop trying other sources
        if source is not None:
            break

    if last_error:
        raise last_error
    raise ParseError(f"All search attempts failed for query '{query}'")