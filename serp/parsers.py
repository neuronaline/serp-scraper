"""SERP parsing logic for Google and Bing using nodriver."""

import asyncio
from typing import Any, Optional

import markdownify
import nodriver as uc

from .cleaning import clean_html, clean_markdown
from .config import BING_URL_TEMPLATE
from .utils import (
    CaptchaError,
    PageTimeoutError,
    ParseError,
    VirtualScreenRequiredError,
    _build_chrome_proxy_arg,
    _extract_bing_real_url,
    logger,
    require_virtual_display,
)
from nodriver.cdp.runtime import RemoteObject
from nodriver.cdp.fetch import (
    enable as fetch_enable,
    AuthRequired,
    continue_with_auth,
    AuthChallengeResponse,
    RequestPaused,
)


def _check_captcha(url: str, page_source: str = "") -> bool:
    """Check if page has captcha based on URL and page content."""
    url_lower = url.lower()
    if "sorry/app" in url_lower or "/captcha/" in url_lower:
        return True

    captcha_patterns = [
        "sorry/app/before",
        "support.google.com/recaptcha",
        "support.microsoft.com/captcha",
    ]
    content_lower = page_source.lower()
    has_captcha_content = any(pattern in content_lower for pattern in captcha_patterns)
    # Only flag as captcha if it's an actual captcha service with evidence of a challenge
    has_captcha_iframe = 'id="captcha"' in content_lower or 'class="captcha"' in content_lower
    has_explicit_captcha = (
        # Strict check: explicit captcha service with challenge evidence
        ("recaptcha" in content_lower and ("g-recaptcha" in content_lower or "google.com/recaptcha" in content_lower))
        or ("hcaptcha" in content_lower and ("h-captcha" in content_lower or "hcaptcha.com" in content_lower))
        or "cf-challenge" in content_lower
        # Fallback: any mention of captcha services (catches simple text mentions)
        or "recaptcha" in content_lower
        or "hcaptcha" in content_lower
    )
    return has_captcha_content or has_explicit_captcha or has_captcha_iframe


def _find_system_chrome_path() -> Optional[str]:
    """Find system Chrome/Chromium executable path.

    Checks common installation paths and returns the first valid one found.
    Snap chromium is avoided due to proxy configuration limitations.
    """
    import os
    import subprocess

    # Order matters: prefer Google Chrome over system Chromium
    # Also check CHROME_PATH env var if set
    chrome_path = os.environ.get("CHROME_PATH")
    if chrome_path and os.path.isfile(chrome_path) and os.access(chrome_path, os.X_OK):
        return chrome_path

    # Common Chrome/Chromium installation paths
    candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/opt/google/chrome/chrome",
        # Snap paths (not recommended but check last)
        "/snap/bin/chromium",
    ]

    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            if "/snap/" in path:
                logger.warning(
                    f"Snap Chromium detected at {path}. "
                    "Snap browsers may not honor proxy settings properly. "
                    "Set CHROME_PATH to a system Chrome/Chromium path to suppress this warning."
                )
            return path

    return None


async def _create_browser(
    proxy: Optional[dict] = None,
    headless: bool = False,
) -> Optional[uc.Browser]:
    """Create and return a nodriver browser instance.

    Uses nodriver.start() as recommended in the documentation.
    Sandbox is disabled for Linux/root environments.

    Proxy credentials are NOT embedded in --proxy-server because Chrome
    does not support user:pass@host format. Authentication is handled
    separately via CDP Fetch.authRequired event in _setup_proxy_auth().

    When headless=False (the default), a virtual display (DISPLAY env var)
    is required. Running non-headless without a display will raise
    VirtualScreenRequiredError.
    """
    # Non-headless mode requires a virtual display
    if not headless:
        require_virtual_display()

    browser_args = [
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--disable-infobars",
        # WebRTC leak prevention (from documentation)
        "--disable-webrtc",
        "--disable-features=WebRtcHideLocalIpsWithMdns",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    ]

    if proxy:
        # Chrome does NOT support embedded credentials. Pass host:port only.
        proxy_arg = _build_chrome_proxy_arg(proxy)
        if proxy_arg:
            browser_args.append(f"--proxy-server={proxy_arg}")
            logger.debug(f"Proxy configured (auth via CDP): {proxy_arg}")

    try:
        import os

        # nodriver.start() handles --no-sandbox automatically based on this flag.
        # sandbox=False is essential for Linux/root environments.
        sandbox = os.geteuid() != 0  # True = sandbox enabled (non-root), False = disabled (root)

        # Find system Chrome to avoid snap chromium issues
        browser_executable = _find_system_chrome_path()

        browser = await uc.start(
            headless=headless,
            browser_args=browser_args,
            sandbox=sandbox,
            browser_executable_path=browser_executable,
        )
        return browser
    except Exception as e:
        logger.error(f"Failed to start browser: {e}")
        return None


async def _setup_proxy_auth(
    tab: uc.Tab,
    proxy: dict,
) -> None:
    """Set up CDP-based proxy authentication on a tab.

    Chrome's --proxy-server flag does not support embedded credentials.
    Instead, we enable the Fetch domain to intercept 407 Proxy Auth
    Required challenges and respond with the stored credentials.

    Must be called BEFORE navigating to a URL that requires proxy auth.

    Args:
        tab: nodriver Tab to set up auth on (typically about:blank)
        proxy: Proxy dict with 'username' and 'password' keys
    """
    username = proxy.get("username")
    password = proxy.get("password")
    if not username or not password:
        return  # Nothing to set up

    async def _on_auth_required(event: AuthRequired) -> None:
        """Respond to proxy auth challenge with credentials."""
        logger.debug(f"AuthRequired event: {event}")
        await tab.send(continue_with_auth(
            request_id=event.request_id,
            auth_challenge_response=AuthChallengeResponse(
                response="ProvideCredentials",
                username=username,
                password=password,
            ),
        ))

    # Enable Fetch domain with auth request handling
    # handle_auth_requests=True makes Chrome pause on auth challenges and fire AuthRequired
    await tab.send(fetch_enable(handle_auth_requests=True))
    tab.add_handler(AuthRequired, _on_auth_required)

    logger.debug(
        f"CDP proxy auth handler registered for "
        f"{username[:8]}... on tab {tab.target.target_id[:8]}"
    )


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
    """Parse Google search results using JavaScript evaluation.

    Polls for results with increasing delays to handle slow-rendering pages.
    This significantly reduces intermittent "no results" errors when the DOM
    hasn't finished populating before the first parse attempt.
    """
    js_code = """
    (function() {
        const results = [];
        // Combined selector: try all known result container patterns (union).
        // div[data-hveid] is a broad fallback that catches many Google containers
        // including non-organic sections; those are filtered out below.
        const items = document.querySelectorAll(
            'div.g, div#rso > div, div.MjjYud, div[data-hveid]'
        );
        items.forEach((item, idx) => {
            // Skip items inside known non-organic sections (e.g., "People also ask",
            // knowledge panels, image packs, related searches).
            if (item.closest('#botstuff, [data-attrid], .kno-kp, .related-question-pair')) return;

            const h3 = item.querySelector('h3');
            if (!h3) return;
            const title = h3.innerText || h3.textContent;

            const linkEl = item.querySelector('a[href][data-ved], a.zReHs, a[jsname="UWckNb"], a[ping]');
            if (!linkEl) return;
            const url = linkEl.href;
            if (!url || url.startsWith('javascript:') || url.startsWith('/')) return;

            const descEl = item.querySelector('div.VwiC3b, span.aCOpRe, div[data-sncf], span.st');
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

    # Poll for results with increasing delays (0.5s, 1s, 2s, 3s)
    max_parse_attempts = 4
    seen_urls = set()
    results = []
    base_rank = (page_num - 1) * 10

    for parse_attempt in range(1, max_parse_attempts + 1):
        try:
            js_results = await tab.evaluate(js_code)
            actual_results = _extract_js_value(js_results)

            if actual_results and isinstance(actual_results, list):
                seen_urls.clear()
                results.clear()

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

            if results:
                logger.debug(f"Google parse succeeded on attempt {parse_attempt} ({len(results)} results)")
                return results

            if parse_attempt < max_parse_attempts:
                delay = 0.5 * (2 ** (parse_attempt - 1))  # 0.5, 1.0, 2.0
                logger.debug(f"Google parse attempt {parse_attempt} returned 0 results, "
                             f"retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

        except Exception as e:
            if parse_attempt < max_parse_attempts:
                logger.debug(f"Google parse attempt {parse_attempt} failed: {e}, retrying...")
                await asyncio.sleep(0.5 * (2 ** (parse_attempt - 1)))
            else:
                logger.error(f"Failed to parse Google results after {max_parse_attempts} attempts: {e}")

    return []


async def _parse_bing_results(tab: uc.Tab, page_num: int) -> list[dict[str, Any]]:
    """Parse Bing search results using JavaScript evaluation.

    Polls for results with increasing delays to handle slow-rendering pages.
    """
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

    # Poll for results with increasing delays (0.5s, 1s, 2s, 3s)
    max_parse_attempts = 4
    seen_urls = set()
    results = []
    base_rank = (page_num - 1) * 10

    for parse_attempt in range(1, max_parse_attempts + 1):
        try:
            js_results = await tab.evaluate(js_code)
            actual_results = _extract_js_value(js_results)

            if actual_results and isinstance(actual_results, list):
                seen_urls.clear()
                results.clear()

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
                        logger.warning(
                            f"Failed to extract real URL from Bing redirect: {original_url[:50]}..."
                        )
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

            if results:
                logger.debug(f"Bing parse succeeded on attempt {parse_attempt} ({len(results)} results)")
                return results

            if parse_attempt < max_parse_attempts:
                delay = 0.5 * (2 ** (parse_attempt - 1))  # 0.5, 1.0, 2.0
                logger.debug(f"Bing parse attempt {parse_attempt} returned 0 results, "
                             f"retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

        except Exception as e:
            if parse_attempt < max_parse_attempts:
                logger.debug(f"Bing parse attempt {parse_attempt} failed: {e}, retrying...")
                await asyncio.sleep(0.5 * (2 ** (parse_attempt - 1)))
            else:
                logger.error(f"Failed to parse Bing results after {max_parse_attempts} attempts: {e}")

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
        url = f"https://www.google.com/search?q={query}&start={start}&hl=en&gl=us&lr=lang_en"
        captcha_msg = "CAPTCHA detected on Google"

    logger.debug(f"Navigating to {source}: {url}")

    browser = await _create_browser(proxy, headless)
    if browser is None:
        raise ParseError("Failed to start browser - nodriver may not be properly installed")

    tab = None
    try:
        # Navigate directly to the search URL
        # Proxy (if configured) is passed via --proxy-server to Chrome
        tab = await browser.get(url)

        # Smart wait: wait for search results (or CAPTCHA page) to actually appear
        # Instead of a fixed sleep, we wait for known DOM elements to materialize.
        # This handles slow proxies/connections gracefully without a hardcoded limit.
        # Multiple selector sets are tried as fallback to handle DOM structure changes.
        try:
            if source == "bing":
                # Bing wraps results in li.b_algo elements
                for bing_sel in ["li.b_algo", "#b_results", "ol#b_results"]:
                    try:
                        await tab.select(bing_sel, timeout=8)
                        break
                    except Exception:
                        continue
                # Extra short wait for Bing to finish rendering all results
                await asyncio.sleep(1)
            else:
                # Google wraps results in div.g / div#rso elements
                # Try multiple selector variations to handle DOM changes
                for google_sel in ["div.g", "div#rso > div", "div.MjjYud", "div[data-hveid]"]:
                    try:
                        await tab.select(google_sel, timeout=8)
                        break
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Smart wait for {source} results timed out: {e}")
            # Fallback: small extra wait before checking for errors/CAPTCHA
            await asyncio.sleep(2)

        # Check for CAPTCHA / error pages (check both URL and page content)
        current_url = (tab.url or "").lower()
        if "sorry/app" in current_url or "/captcha/" in current_url:
            raise CaptchaError(captcha_msg)

        if not tab.url or tab.url == "about:blank":
            raise PageTimeoutError("Failed to navigate - page did not load")

        # Check page content for CAPTCHA or blocking patterns
        try:
            page_html = await tab.get_content()
            if _check_captcha(tab.url, page_html):
                raise CaptchaError(captcha_msg)
        except CaptchaError:
            raise
        except Exception:
            pass  # if content retrieval fails, proceed anyway

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

        # Cancel background tasks and stop browser cleanly
        try:
            await _cleanup_browser(browser)
        except Exception:
            pass


async def _cleanup_browser(browser) -> None:
    """Cancel nodriver background tasks and stop browser cleanly.

    Nodriver runs internal background tasks (e.g., update_targets) that can
    produce "Task exception was never retrieved" warnings if not properly
    cancelled before browser.stop(). This is a known issue with nodriver's
    CDP connection management.

    Task attribute names (_idle, _update_task) are private API - iterate
    over known names to future-proof against nodriver version changes.
    """
    if browser is None:
        return

    # Known nodriver internal task attribute names
    task_attr_names = ('_idle', '_update_task')

    for attr_name in task_attr_names:
        task = getattr(browser, attr_name, None)
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    await asyncio.sleep(0.25)
    browser.stop()


async def _fetch_browser_impl(
    url: str,
    proxy: Optional[dict] = None,
    headless: bool = False,
) -> str:
    """Async browser fetch implementation using nodriver.

    Ensures the page is fully loaded before retrieving content. This includes:
    1. Navigation to the target URL
    2. Waiting for the page load event to fire
    3. Additional wait time for JavaScript to execute and render content
    4. Verification that the page loaded successfully
    """
    browser = await _create_browser(proxy, headless)
    if browser is None:
        raise ParseError("Failed to start browser - nodriver may not be properly installed")

    tab = None
    try:
        # Navigate directly - proxy is configured via --proxy-server
        tab = await browser.get(url)

        # Wait for page to fully load before accessing content.
        # "load" event fires when all resources (scripts, stylesheets, images)
        # have been fully downloaded and processed.
        await tab.wait("load")

        # Additional wait for JavaScript execution and dynamic content rendering.
        # Some pages render content via JavaScript after the load event.
        # This handles SPAs and dynamically-loaded content.
        await asyncio.sleep(1)

        # Verify page loaded successfully
        if not tab.url or tab.url == "about:blank":
            raise PageTimeoutError("Page did not load - no URL returned")

        page_content = await tab.get_content()
        if _check_captcha(tab.url, page_content):
            raise CaptchaError("Captcha detected")

        # Clean HTML before conversion
        cleaned_html = clean_html(page_content)

        markdown = markdownify.markdownify(
            cleaned_html,
            heading_style="ATX",
        )

        # Post-clean markdown
        markdown = clean_markdown(markdown)

        return markdown

    finally:
        # Clean up tab first, then browser
        if tab is not None:
            try:
                await tab.close()
            except Exception:
                pass
            tab = None

        # Cancel background tasks and stop browser cleanly
        try:
            await _cleanup_browser(browser)
        except Exception:
            pass
