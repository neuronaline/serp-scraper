"""SERP parsing logic for Google and Bing using nodriver."""

import asyncio
from typing import Any, Optional

import markdownify
import nodriver as uc

from .config import BING_URL_TEMPLATE
from .utils import CaptchaError, PageTimeoutError, ParseError, _extract_bing_real_url, logger
from nodriver.cdp.runtime import RemoteObject


def _check_captcha(url: str, page_source: str = "") -> bool:
    """Check if page has captcha based on URL and page content."""
    url_lower = url.lower()
    if "sorry/app" in url_lower or "/captcha/" in url_lower:
        return True

    captcha_patterns = [
        "sorry/app/before",
        "support.google.com/recaptcha",
        "support.microsoft.com/captcha",
        "detected unusual traffic",
        "enable javascript",
    ]
    content_lower = page_source.lower()
    has_captcha_content = any(pattern in content_lower for pattern in captcha_patterns)
    has_explicit_captcha = "captcha" in content_lower and (
        "/captcha/" in content_lower or "recaptcha" in content_lower or "hcaptcha" in content_lower
    )
    return has_captcha_content or has_explicit_captcha


async def _create_browser(
    proxy: Optional[dict] = None,
    headless: bool = False,
) -> Optional[uc.Browser]:
    """Create and return a nodriver browser instance."""
    browser_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]

    if proxy:
        server = proxy.get("server", "")
        if server:
            browser_args.append(f"--proxy-server={server}")

    try:
        browser = await uc.start(
            headless=headless,
            browser_args=browser_args,
        )
        return browser
    except Exception as e:
        logger.error(f"Failed to start browser: {e}")
        return None


def _extract_js_value(obj) -> Any:
    """Extract actual value from nodriver CDP serialized objects.

    CDP serializes complex objects in a specific format that needs to be
    unpacked to get actual Python values.
    """
    if obj is None:
        return None

    # If it's a RemoteObject, extract from it
    if isinstance(obj, RemoteObject):
        if obj.deep_serialized_value and hasattr(obj.deep_serialized_value, 'value'):
            obj = obj.deep_serialized_value.value
        elif obj.value is not None:
            obj = obj.value
        else:
            return None

    # If it's a list (array result), process each element
    if isinstance(obj, list):
        result = []
        for item in obj:
            if isinstance(item, dict) and item.get('type') == 'object' and 'value' in item:
                # CDP object: [[key, {type, value}], ...]
                dict_result = {}
                for pair in item['value']:
                    if isinstance(pair, list) and len(pair) == 2:
                        key, val = pair
                        dict_result[key] = _extract_js_value(val)
                result.append(dict_result)
            elif isinstance(item, dict):
                # CDP primitive wrapped in dict
                result.append(_extract_js_value(item))
            else:
                result.append(item)
        return result

    # If it's a CDP serialized primitive
    if isinstance(obj, dict):
        if obj.get('type') == 'number':
            return obj.get('value')
        elif obj.get('type') == 'string':
            return obj.get('value')
        elif obj.get('type') == 'boolean':
            return obj.get('value')
        elif obj.get('type') == 'object' and 'value' in obj:
            # Nested CDP object
            return obj.get('value')

    # Already a plain value (string, number, boolean, etc.)
    if isinstance(obj, (str, int, float, bool)):
        return obj

    return obj


async def _parse_google_results(tab: uc.Tab, page_num: int) -> list[dict[str, Any]]:
    """Parse Google search results using JavaScript evaluation."""
    js_code = """
    (function() {
        const results = [];
        const items = document.querySelectorAll('div.MjjYud, div#rso > div, div.g');
        items.forEach((item, idx) => {
            const h3 = item.querySelector('h3');
            if (!h3) return;
            const title = h3.innerText || h3.textContent;

            const linkEl = item.querySelector('a[href][data-ved], a.zReHs, a[jsname="UWckNb"]');
            if (!linkEl) return;
            const url = linkEl.href;
            if (!url || url.startsWith('javascript:') || url.startsWith('/')) return;

            const descEl = item.querySelector('div.VwiC3b, span.aCOpRe, div[data-sncf]');
            const desc = descEl ? (descEl.innerText || descEl.textContent) : '';

            results.push({
                rank: idx + 1,
                title: title,
                url: url,
                description: desc
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

        seen_urls = set()
        results = []
        base_rank = (page_num - 1) * 10

        for idx, r in enumerate(actual_results):
            if not isinstance(r, dict):
                continue
            url = r.get('url', '')
            title = r.get('title', '')
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append({
                'rank': base_rank + idx + 1,
                'title': title,
                'url': url,
                'description': r.get('description', '')
            })

        return results
    except Exception as e:
        logger.error(f"Failed to parse Google results: {e}")
        return []


async def _parse_bing_results(tab: uc.Tab, page_num: int) -> list[dict[str, Any]]:
    """Parse Bing search results using JavaScript evaluation."""
    js_code = """
    (function() {
        const results = [];
        const items = document.querySelectorAll('li.b_algo');
        items.forEach((item, idx) => {
            const h2 = item.querySelector('h2');
            if (!h2) return;
            const title = h2.innerText || h2.textContent;

            const linkEl = item.querySelector('h2 a, a[href]');
            if (!linkEl) return;
            const url = linkEl.href;
            if (!url || url.startsWith('javascript:')) return;

            const descEl = item.querySelector('p');
            const desc = descEl ? (descEl.innerText || descEl.textContent) : '';

            results.push({
                rank: idx + 1,
                title: title,
                url: url,
                description: desc
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

        seen_urls = set()
        results = []
        base_rank = (page_num - 1) * 10

        for idx, r in enumerate(actual_results):
            if not isinstance(r, dict):
                continue
            url = r.get('url', '')
            # Extract real URL from Bing redirect URLs
            original_url = url
            url = _extract_bing_real_url(url)
            if original_url != url:
                logger.debug(f"Resolved Bing redirect: {original_url[:50]}... -> {url[:50]}...")
            elif "bing.com/ck/a" in original_url:
                logger.warning(f"Failed to extract real URL from Bing redirect: {original_url[:50]}...")
            title = r.get('title', '')
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append({
                'rank': base_rank + idx + 1,
                'title': title,
                'url': url,
                'description': r.get('description', '')
            })

        return results
    except Exception as e:
        logger.error(f"Failed to parse Bing results: {e}")
        return []


async def _search_impl(
    query: str,
    page_num: int,
    proxy: Optional[dict] = None,
    headless: bool = False,
    source: str = "google",
) -> list[dict[str, Any]]:
    """Async search implementation using nodriver browser."""
    if source == "bing":
        offset = (page_num - 1) * 10 + 1
        url = BING_URL_TEMPLATE.format(query=query, offset=offset)
        captcha_msg = "CAPTCHA detected on Bing"
    else:
        start = (page_num - 1) * 10
        url = f"https://www.google.com/search?q={query}&start={start}"
        captcha_msg = "CAPTCHA detected on Google"

    logger.debug(f"Navigating to {source}: {url}")

    browser = await _create_browser(proxy, headless)
    if browser is None:
        raise ParseError("Failed to start browser - nodriver may not be properly installed")

    tab = None
    try:
        tab = await browser.get(url)
        # Wait for the page to fully load (Google loads results dynamically)
        await tab.wait(3)

        # Check for CAPTCHA/sorry page
        current_url = (tab.url or "").lower()
        if "sorry/app" in current_url or "/captcha/" in current_url:
            raise CaptchaError(captcha_msg)

        if not tab.url or tab.url == "about:blank":
            raise PageTimeoutError("Failed to navigate - page did not load")

        # Parse results
        if source == "bing":
            results = await _parse_bing_results(tab, page_num)
        else:
            results = await _parse_google_results(tab, page_num)

        logger.debug(f"Parsed {len(results)} results from {source}")

        if not results:
            raise ParseError(f"No results found for query '{query}' on {source} page {page_num}")

        return results

    except (CaptchaError, PageTimeoutError, ParseError):
        raise
    except Exception as e:
        logger.warning(f"Search failed: {type(e).__name__}: {e}")
        raise ParseError(str(e)) from e
    finally:
        # Clean up tab first, then browser
        if tab is not None:
            try:
                await tab.close()
            except Exception:
                pass
            tab = None
        # Small delay to allow tab cleanup before stopping browser
        if browser is not None:
            try:
                await asyncio.sleep(0.1)
                browser.stop()
            except Exception:
                pass


async def _fetch_browser_impl(
    url: str,
    proxy: Optional[dict] = None,
    headless: bool = False,
) -> str:
    """Async browser fetch implementation using nodriver."""
    browser = await _create_browser(proxy, headless)
    if browser is None:
        raise ParseError("Failed to start browser - nodriver may not be properly installed")

    tab = None
    try:
        tab = await browser.get(url)
        await tab.wait(3)

        page_content = await tab.get_content()
        if _check_captcha(tab.url, page_content):
            raise CaptchaError("Captcha detected")

        markdown = markdownify.markdownify(
            page_content,
            heading_style="ATX",
        )
        return markdown

    finally:
        # Clean up tab first, then browser
        if tab is not None:
            try:
                await tab.close()
            except Exception:
                pass
            tab = None
        # Small delay to allow tab cleanup before stopping browser
        if browser is not None:
            try:
                await asyncio.sleep(0.1)
                browser.stop()
            except Exception:
                pass
