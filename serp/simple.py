"""Simple HTTP-based search for SERP module."""

import asyncio
import re
from typing import Any, Optional

from bs4 import BeautifulSoup

from .config import load_config
from .cache import get_cache
from .utils import (
    CaptchaError,
    PageTimeoutError,
    ParseError,
    ProxyError,
    MAX_RETRIES,
    _random_user_agent,
    _build_proxy_url,
    _extract_bing_real_url,
    _wait_random_delay_async,
    logger,
)


async def _search_simple_impl_bing(
    query: str,
    page_num: int,
    proxy_url: str,
) -> list[dict[str, Any]]:
    """Simple HTTP-based Bing search using httpx with proxy."""
    import httpx

    # Bing uses 1-based offset: first result number
    offset = (page_num - 1) * 10 + 1
    url = f"https://www.bing.com/search?q={query}&first={offset}"

    headers = {
        "User-Agent": _random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    async with httpx.AsyncClient(
        proxy=proxy_url,
        timeout=30.0,
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = await client.get(url)
        logger.debug(f"_search_simple_impl_bing: status={response.status_code}")

        if response.status_code != 200:
            raise ProxyError(f"Bing HTTP {response.status_code}")

        html = response.text

        # Check for CAPTCHA
        if "sorry" in response.url.path.lower() or "captcha" in html.lower():
            raise CaptchaError("CAPTCHA detected on Bing")

        # Parse results with BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        results = []
        base_rank = (page_num - 1) * 10

        # Find Bing organic results - li.b_algo contains each result
        for rank, li in enumerate(soup.select("li.b_algo"), start=base_rank + 1):
            # Get title from h2 > a
            title_el = li.select_one("h2 a") or li.select_one("h2")
            if not title_el:
                continue
            title = title_el.get_text()

            # Get link
            link_el = li.select_one("h2 a")
            if not link_el:
                continue
            link = link_el.get("href", "")

            # Skip if not a valid URL
            if not link or link.startswith("javascript:"):
                continue

            # Extract real URL from Bing redirect URLs
            link = _extract_bing_real_url(link)

            # Get description from p
            desc_el = li.select_one("p")
            desc = desc_el.get_text() if desc_el else ""

            if title and link:
                results.append({
                    "rank": rank,
                    "title": title,
                    "url": link,
                    "description": desc,
                })

        return results


async def search_simple(
    query: str,
    page_num: int = 1,
    proxy_file: str = "proxies.json",
    use_cache: bool = True,
    cache_ttl: int = 86400,
    source: Optional[str] = None,
) -> list[dict]:
    """
    Simple HTTP-based search using httpx with proxy.
    Tries Google first, falls back to Bing on failure (or uses specified source).

    Args:
        query: Search query string
        page_num: Page number (1-based)
        proxy_file: Path to proxies.json
        use_cache: Whether to use cache (default True)
        cache_ttl: Cache time-to-live in seconds (default 86400 = 24 hours)
        source: Search source preference - "google", "bing", or None (auto: google then bing)

    Returns:
        List of dicts with keys: rank, title, url, description
    """
    import httpx

    # Try cache first if enabled (check both Google and Bing cached results)
    if use_cache:
        cache = get_cache()
        # Check Google cache first
        google_cache_key = cache.make_key(query=query, page_num=page_num, source="google")
        cached = cache.get(google_cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for query='{query}', page={page_num} (source=google)")
            return cached
        # Check Bing cache
        bing_cache_key = cache.make_key(query=query, page_num=page_num, source="bing")
        cached = cache.get(bing_cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for query='{query}', page={page_num} (source=bing)")
            return cached

    config = load_config(proxy_file)

    start = (page_num - 1) * 10
    google_url = f"https://www.google.com/search?q={query}&start={start}"

    headers = {
        "User-Agent": _random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    # Retryable error types
    RETRYABLE_ERRORS = (CaptchaError, PageTimeoutError, ParseError, ProxyError, TimeoutError)

    google_error = None
    bing_error = None

    # Determine search order based on source parameter
    if source == "bing":
        search_order = ["bing"]
    elif source == "google":
        search_order = ["google"]
    else:
        # Auto mode: try google first, then bing as fallback
        search_order = ["google", "bing"]

    for current_source in search_order:
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            # Get fresh proxy for each attempt
            proxy = config.get_random_proxy()
            if proxy is None:
                logger.warning(f"No proxy configured - proceeding without proxy")
                proxy_url = None
            else:
                proxy_url = _build_proxy_url(proxy)

            logger.debug(f"search_simple: {current_source} attempt {attempt}/{MAX_RETRIES}, proxy={proxy['server'] if proxy else 'None'}")

            try:
                if current_source == "google":
                    results = await _search_google_simple(query, page_num, proxy_url, headers, use_cache, cache_ttl)
                else:
                    results = await _search_simple_impl_bing(query, page_num, proxy_url)

                logger.info(f"search_simple: {current_source} successful for query='{query}', page={page_num}")
                return results

            except Exception as e:
                last_error = e
                logger.warning(f"search_simple: {current_source} attempt {attempt} failed: {type(e).__name__}: {e}")

                # Check if error is retryable
                if not isinstance(e, RETRYABLE_ERRORS):
                    # Non-retryable error, stop trying this source
                    break

                if attempt < MAX_RETRIES:
                    await _wait_random_delay_async(attempt)

        # All retries exhausted for this source
        if current_source == "google":
            google_error = last_error
        else:
            bing_error = last_error

        # If source is explicitly specified, don't try fallback
        if source in ("google", "bing"):
            break

    # Both sources failed - chain errors properly
    if google_error and bing_error:
        # Raise a combined error with both causes
        raise ParseError(
            f"All search attempts failed for query '{query}': "
            f"Google: {google_error} -> Bing: {bing_error}"
        ) from google_error
    elif google_error:
        raise google_error
    elif bing_error:
        raise bing_error
    else:
        raise ParseError(f"All search attempts failed for query '{query}'")


async def _search_google_simple(
    query: str,
    page_num: int,
    proxy_url: Optional[str],
    headers: dict,
    use_cache: bool,
    cache_ttl: int,
) -> list[dict]:
    """Internal Google search implementation for search_simple."""
    import httpx
    from .cache import get_cache

    start = (page_num - 1) * 10
    google_url = f"https://www.google.com/search?q={query}&start={start}"

    async with httpx.AsyncClient(
        proxy=proxy_url,
        timeout=30.0,
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = await client.get(google_url)
        logger.debug(f"search_simple Google: status={response.status_code}")

        if response.status_code != 200:
            raise ProxyError(f"Google HTTP {response.status_code}")

        html = response.text

        # Check for CAPTCHA
        if "sorry" in response.url.path.lower() or "captcha" in html.lower():
            raise CaptchaError("CAPTCHA detected on Google")

        # Parse results with BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        results = []
        base_rank = (page_num - 1) * 10

        # Find organic results
        for rank, div in enumerate(soup.select("div.g"), start=base_rank + 1):
            title_el = div.select_one("h3")
            if not title_el:
                continue
            title = title_el.get_text()

            link_el = div.select_one("a")
            if not link_el:
                continue
            link = link_el.get("href", "")

            # Skip if not a valid URL or is a Google internal link
            if not link:
                continue
            # Skip Google redirect URLs and internal links
            if link.startswith("/search?") or link.startswith("/url?") or link.startswith("/"):
                continue

            # Get description
            desc = ""
            for sel in ["div.VwiC3b", "span.aCOpRe"]:
                desc_el = div.select_one(sel)
                if desc_el:
                    desc = desc_el.get_text()
                    break

            if title and link:
                results.append({
                    "rank": rank,
                    "title": title,
                    "url": link,
                    "description": desc,
                })

        # Cache the result before returning (with source=google)
        if use_cache:
            cache = get_cache()
            google_cache_key = cache.make_key(query=query, page_num=page_num, source="google")
            cache.set(google_cache_key, results, cache_ttl)

        return results