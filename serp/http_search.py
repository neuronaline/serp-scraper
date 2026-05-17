"""HTTP-based search implementations for SERP module."""

import asyncio
from typing import Any, Optional

from bs4 import BeautifulSoup

from .cache import get_cache
from .utils import (
    CaptchaError,
    PageTimeoutError,
    ParseError,
    ProxyError,
    _random_user_agent,
    _extract_bing_real_url,
    logger,
)


async def _search_google_simple(
    query: str,
    page_num: int,
    proxy_url: Optional[str],
    use_cache: bool,
    cache_ttl: int,
) -> list[dict]:
    """Internal Google search implementation using httpx."""
    import httpx

    start = (page_num - 1) * 10
    google_url = f"https://www.google.com/search?q={query}&start={start}&hl=en&gl=us&lr=lang_en"

    request_headers = {
        "User-Agent": _random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    async with httpx.AsyncClient(
        proxy=proxy_url,
        timeout=30.0,
        follow_redirects=True,
        headers=request_headers,
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

        if not results:
            raise ParseError(f"No results found for query '{query}' on Google page {page_num}")

        # Cache the result before returning (with source=google)
        if use_cache:
            cache = get_cache()
            google_cache_key = cache.make_key(query=query, page_num=page_num, source="google")
            cache.set(google_cache_key, results, cache_ttl)

        return results


async def _search_simple_impl_bing(
    query: str,
    page_num: int,
    proxy_url: Optional[str],
) -> list[dict[str, Any]]:
    """Simple HTTP-based Bing search using httpx with proxy."""
    import httpx

    # Bing uses 1-based offset: first result number
    offset = (page_num - 1) * 10 + 1
    url = f"https://www.bing.com/search?q={query}&first={offset}&mkt=en-US&setlang=en&cc=US"

    headers = {
        "User-Agent": _random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    async with httpx.AsyncClient(
        proxy=proxy_url if proxy_url else None,
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

        if not results:
            raise ParseError(f"No results found for query '{query}' on Bing page {page_num}")

        return results