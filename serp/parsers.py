"""SERP parsing logic for Google and Bing using Camoufox (Firefox/Gecko).

This module replaces the previous nodriver-based implementation with
Camoufox, which provides C++-level BrowserForge fingerprint spoofing
and a Playwright-compatible API.

Key changes from nodriver:
- ``uc.start()`` → ``AsyncCamoufox(os="windows", ...)`` context manager
- ``uc.Tab.evaluate()`` → Playwright ``page.evaluate()`` (returns plain values)
- ``uc.Tab.get_content()`` → ``page.content()``
- ``uc.Tab.select()`` → ``page.wait_for_selector()``
- ``uc.Tab.close()`` → ``page.close()``
"""

import asyncio
import warnings
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlparse

import markdownify
from camoufox.async_api import AsyncCamoufox

from .browser_stealth import (
    DEFAULT_FINGERPRINT,
    WIN10_FONTS,
    FingerprintProfile,
    apply_stealth,
    build_firefox_prefs,
)
from .cleaning import clean_html, clean_markdown
from .config import BING_URL_TEMPLATE
from .utils import (
    CaptchaError,
    PageTimeoutError,
    ParseError,
    _extract_bing_real_url,
    logger,
    require_virtual_display,
)

# ── Suppress Camoufox's "Disabling OS-specific fonts" warning ──────────
warnings.filterwarnings(
    "ignore",
    message="Disabling OS-specific fonts while spoofing your OS",
)

# ── Fontconfig isolation ────────────────────────────────────────────────
# Camoufox's bundled fonts.conf contains implicit <include> tags that
# load the host OS's /etc/fonts configuration, leaking Linux fonts
# (Cantarell) into Gecko's rendering pipeline.
#
# We apply the same surgical monkeypatch + sterile XML approach from
# isolated_browser to prevent font leaks.
#
# NOTE: The monkeypatch and fonts.conf file write are deferred to
# _init_fontconfig(), which is called from _create_browser().
# This avoids module-level side effects.  The fonts_windows.conf file
# is written fresh each time the browser starts, so the hardcoded
# absolute path is resolved dynamically.

import camoufox.utils as _camoufox_utils  # noqa: E402

_FONTCONFIG_INITIALIZED = False


def _init_fontconfig() -> None:
    """Monkey-patch camoufox get_env_vars and write sterile fonts.conf.

    Safe to call multiple times — the monkey-patch and file write are only
    applied on the first invocation.
    """
    global _FONTCONFIG_INITIALIZED
    if _FONTCONFIG_INITIALIZED:
        return

    # ── Monkey-patch camoufox.utils.get_env_vars ─────────────────────
    _orig_get_env_vars = _camoufox_utils.get_env_vars

    def _patched_get_env_vars(config_map: dict, user_agent_os: str) -> dict:
        env = _orig_get_env_vars(config_map, user_agent_os)

        _target_dir = Path(__file__).resolve().parent.parent / "data" / "fontconfig"
        _target_conf = _target_dir / "fonts_windows.conf"

        _target_dir.mkdir(parents=True, exist_ok=True)
        (_target_dir / "cache").mkdir(parents=True, exist_ok=True)

        env["FONTCONFIG_PATH"] = str(_target_dir.resolve())
        env["FONTCONFIG_FILE"] = str(_target_conf.resolve())

        return env

    _camoufox_utils.get_env_vars = _patched_get_env_vars

    # ── Write sterile fonts.conf ──────────────────────────────────────
    try:
        from camoufox.pkgman import camoufox_path

        base = Path(camoufox_path()).resolve()
        font_dir = base / "fonts" / "windows"

        if not font_dir.is_dir():
            logger.warning(
                "Bundled font dir not found at %s — cannot isolate fontconfig",
                font_dir,
            )
            _FONTCONFIG_INITIALIZED = True
            return

        target_dir = Path(__file__).resolve().parent.parent / "data" / "fontconfig"
        target_dir.mkdir(parents=True, exist_ok=True)

        sterile_xml = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <!-- Force fontconfig to ignore and wipe out all compiled-in host system directories -->
  <reset-dirs />

  <!-- Only load our Windows fonts -->
  <dir>{font_dir.as_posix()}</dir>

  <!-- Cache directory isolated to our path -->
  <cachedir>{(target_dir / "cache").as_posix()}</cachedir>

  <!-- Strict generic fallback mappings directly to Windows fonts -->
  <match target="pattern">
    <test qual="any" name="family"><string>sans-serif</string></test>
    <edit name="family" mode="assign" binding="same"><string>Arial</string></edit>
  </match>
  <match target="pattern">
    <test qual="any" name="family"><string>serif</string></test>
    <edit name="family" mode="assign" binding="same"><string>Times New Roman</string></edit>
  </match>
  <match target="pattern">
    <test qual="any" name="family"><string>monospace</string></test>
    <edit name="family" mode="assign" binding="same"><string>Consolas</string></edit>
  </match>
  <match target="pattern">
    <test qual="any" name="family"><string>system-ui</string></test>
    <edit name="family" mode="assign" binding="same"><string>Segoe UI</string></edit>
  </match>
</fontconfig>"""

        target_conf = target_dir / "fonts_windows.conf"
        target_conf.write_text(sterile_xml, encoding="utf-8")

        logger.info(
            "Fontconfig isolated — using %s (fonts dir: %s)",
            target_conf,
            font_dir,
        )
    except Exception as exc:
        logger.warning("Fontconfig isolation failed: %s — host fonts may leak", exc)

    _FONTCONFIG_INITIALIZED = True


# ─────────────────────────────────────────────────────────────────────────
# Page creation helper
# ─────────────────────────────────────────────────────────────────────────


async def _create_page(browser) -> Any:
    """Create a new page on an existing browser and apply stealth init scripts.

    This replaces the old ``_serp_page`` approach — each navigation gets its own
    page, which eliminates race conditions when using the browser concurrently.

    Args:
        browser: A Playwright ``Browser`` returned by ``_create_browser()``.

    Returns:
        A Playwright ``Page`` with stealth init scripts pre-registered.
    """
    fp = getattr(browser, "_serp_fingerprint", DEFAULT_FINGERPRINT)
    page = await browser.new_page()

    # Suppress pageerror events that could crash the browser.
    # Firefox (Gecko) may emit page errors with undefined `location.url`,
    # which triggers a TypeError inside Playwright's internal error handling
    # and kills the entire browser context.  This handler swallows those
    # errors safely so that normal page operations continue uninterrupted.
    page.on("pageerror", lambda err: logger.debug("Page error (suppressed): %s", err))

    # Note: proxy_ip is intentionally "0.0.0.0" to avoid leaking the real IP.
    # The WebRTC spoof replaces public IPs; an empty string would delete them.
    await apply_stealth(page, fp, proxy_ip="0.0.0.0")
    return page


# ─────────────────────────────────────────────────────────────────────────
# CAPTCHA detection
# ─────────────────────────────────────────────────────────────────────────


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
    has_captcha_iframe = 'id="captcha"' in content_lower or 'class="captcha"' in content_lower
    # Require actual CAPTCHA widget HTML, not just the word appearing anywhere.
    # A blog post or privacy policy may mention "reCAPTCHA" or "hCaptcha" in
    # text — that is NOT a CAPTCHA challenge.  Only flag if the specific
    # widget elements (g-recaptcha / h-captcha divs) or challenge pages are
    # present.
    has_explicit_captcha = (
        ("recaptcha" in content_lower and "g-recaptcha" in content_lower)
        or ("hcaptcha" in content_lower and "h-captcha" in content_lower)
        or "cf-challenge" in content_lower
        or "google.com/recaptcha" in content_lower
        or "hcaptcha.com" in content_lower
        or "challenges.cloudflare.com" in content_lower
    )
    return has_captcha_content or has_explicit_captcha or has_captcha_iframe


# ─────────────────────────────────────────────────────────────────────────
# Browser creation
# ─────────────────────────────────────────────────────────────────────────


async def _create_browser(
    proxy: Optional[dict] = None,
    headless: bool = False,
    fingerprint: Optional[FingerprintProfile] = None,
    block_images: bool = False,
) -> Any:
    """Create and return a Camoufox browser instance with full stealth applied.

    Uses Camoufox (Firefox/Gecko) with BrowserForge C++ level fingerprinting
    and JS safety net injection.

    Args:
        proxy: Proxy dict with ``server``, ``username``, ``password`` keys.
        headless: Run in headless mode (default: ``False``).
        fingerprint: Optional ``FingerprintProfile``; uses ``DEFAULT_FINGERPRINT`` if None.
        block_images: If True, block image loading to speed up non-SERP fetches
            where media is irrelevant (default: ``False`` — images loaded).

    Returns:
        A Playwright ``Browser`` instance, or ``None`` if startup fails.
    """
    # Initialize fontconfig isolation (idempotent — runs once)
    _init_fontconfig()

    # Virtual display check for non-headless mode
    if not headless:
        require_virtual_display()

    fp = fingerprint or DEFAULT_FINGERPRINT

    # Build Camoufox launch options
    window = (fp.screen_width, fp.screen_height)

    # Proxy settings
    proxy_settings = None
    if proxy:
        server = proxy.get("server", "")
        username = proxy.get("username")
        password = proxy.get("password")
        if username and password:
            # Build authenticated proxy URL for Playwright with URL-encoded credentials
            parsed = urlparse(server)
            scheme = parsed.scheme or "http"
            hostname = parsed.hostname or ""
            port_str = f":{parsed.port}" if parsed.port else ""
            encoded_user = quote(username, safe="")
            encoded_pass = quote(password, safe="")
            server = f"{scheme}://{encoded_user}:{encoded_pass}@{hostname}{port_str}"

        proxy_settings = {"server": server}

    # Firefox user preferences for Windows spoofing
    firefox_user_prefs = build_firefox_prefs()

    try:
        camoufox = AsyncCamoufox(
            os="windows",
            window=window,
            proxy=proxy_settings,
            humanize=False,
            disable_coop=True,
            geoip=False,
            block_images=block_images,
            block_webrtc=False,
            fonts=WIN10_FONTS,
            custom_fonts_only=True,
            i_know_what_im_doing=True,
            firefox_user_prefs=firefox_user_prefs,
            headless=headless,
        )

        browser = await camoufox.__aenter__()
        if browser is None:
            logger.error("AsyncCamoufox.__aenter__() returned None")
            return None

        # Store the AsyncCamoufox context manager and fingerprint for cleanup/page creation
        browser._serp_camoufox = camoufox
        browser._serp_fingerprint = fp

        logger.debug(
            "Camoufox browser started — window=%dx%d, proxy=%s, headless=%s",
            fp.screen_width, fp.screen_height,
            bool(proxy), headless,
        )
        return browser

    except Exception as e:
        logger.error("Failed to start Camoufox browser: %s", e)
        return None


# ─────────────────────────────────────────────────────────────────────────
# Smart wait helper
# ─────────────────────────────────────────────────────────────────────────


async def _wait_for_results(page: Any, selectors: list[str], timeout: int = 5) -> bool:
    """Wait for any of the given CSS selectors to appear on the page.

    Args:
        page: Playwright Page.
        selectors: List of CSS selector strings.
        timeout: Timeout in seconds for each selector attempt.

    Returns:
        True if any selector matched, False if all timed out.
    """
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout * 1000)
            return True
        except Exception:
            continue
    return False


# ─────────────────────────────────────────────────────────────────────────
# Page content / HTML helper
# ─────────────────────────────────────────────────────────────────────────


async def _get_page_html(page: Any) -> str:
    """Get the full page HTML content.

    Uses ``page.content()`` which returns the complete DOM as HTML.
    """
    try:
        return await page.content()
    except Exception as e:
        logger.debug("Failed to get page content: %s", e)
        return ""


# ─────────────────────────────────────────────────────────────────────────
# Google results parsing
# ─────────────────────────────────────────────────────────────────────────


async def _parse_google_results(page: Any, page_num: int) -> list[dict[str, Any]]:
    """Parse Google search results using JavaScript evaluation.

    Polls for results with increasing delays to handle slow-rendering pages.

    Args:
        page: Playwright Page with loaded Google search results.
        page_num: Current page number (1-based).

    Returns:
        List of result dicts with rank, title, url, description.
    """
    js_code = """
    (function() {
        const results = [];
        let resultIdx = 0;
        const items = document.querySelectorAll(
            'div.g, div#rso > div, div.MjjYud, div[data-hveid]'
        );
        items.forEach((item) => {
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

            resultIdx++;
            results.push({
                rank: resultIdx,
                title: title,
                url: url,
                description: desc
            });
        });
        return results;
    })()
    """

    # Poll for results with short fixed delays (0.3s, 0.5s, 0.8s)
    max_parse_attempts = 3
    seen_urls: set[str] = set()
    results: list[dict[str, Any]] = []
    base_rank = (page_num - 1) * 10

    for parse_attempt in range(1, max_parse_attempts + 1):
        try:
            actual_results = await page.evaluate(js_code)

            if actual_results and isinstance(actual_results, list):
                seen_urls.clear()
                results.clear()

                for idx, r in enumerate(actual_results):
                    if not isinstance(r, dict):
                        continue
                    url = r.get("url", "")
                    title = r.get("title", "")
                    if not title or not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    results.append({
                        "rank": base_rank + idx + 1,
                        "title": title,
                        "url": url,
                        "description": r.get("description", ""),
                    })

            if results:
                logger.debug("Google parse succeeded on attempt %d (%d results)", parse_attempt, len(results))
                return results

            if parse_attempt < max_parse_attempts:
                delay = 0.3 * parse_attempt
                logger.debug("Google parse attempt %d returned 0 results, retrying in %.1fs...", parse_attempt, delay)
                await asyncio.sleep(delay)

        except Exception as e:
            if parse_attempt < max_parse_attempts:
                logger.debug("Google parse attempt %d failed: %s, retrying...", parse_attempt, e)
                await asyncio.sleep(0.3 * parse_attempt)
            else:
                logger.error("Failed to parse Google results after %d attempts: %s", max_parse_attempts, e)

    return []


# ─────────────────────────────────────────────────────────────────────────
# Bing results parsing
# ─────────────────────────────────────────────────────────────────────────


async def _parse_bing_results(page: Any, page_num: int) -> list[dict[str, Any]]:
    """Parse Bing search results using JavaScript evaluation.

    Args:
        page: Playwright Page with loaded Bing search results.
        page_num: Current page number (1-based).

    Returns:
        List of result dicts with rank, title, url, description.
    """
    js_code = """
    (function() {
        const results = [];
        let resultIdx = 0;
        const items = document.querySelectorAll('li.b_algo');
        items.forEach((item) => {
            const h2 = item.querySelector('h2');
            if (!h2) return;
            const title = h2.innerText || h2.textContent;

            const linkEl = item.querySelector('h2 a, a[href]');
            if (!linkEl) return;
            const url = linkEl.href;
            if (!url || url.startsWith('javascript:')) return;

            const descEl = item.querySelector('p');
            const desc = descEl ? (descEl.innerText || descEl.textContent) : '';

            resultIdx++;
            results.push({
                rank: resultIdx,
                title: title,
                url: url,
                description: desc
            });
        });
        return results;
    })()
    """

    max_parse_attempts = 3
    seen_urls: set[str] = set()
    results: list[dict[str, Any]] = []
    base_rank = (page_num - 1) * 10

    for parse_attempt in range(1, max_parse_attempts + 1):
        try:
            actual_results = await page.evaluate(js_code)

            if actual_results and isinstance(actual_results, list):
                seen_urls.clear()
                results.clear()

                for idx, r in enumerate(actual_results):
                    if not isinstance(r, dict):
                        continue
                    url = r.get("url", "")
                    original_url = url
                    url = _extract_bing_real_url(url)
                    if original_url != url:
                        logger.debug("Resolved Bing redirect: %s... -> %s...", original_url[:50], url[:50])
                    elif "bing.com/ck/a" in original_url:
                        logger.warning("Failed to extract real URL from Bing redirect: %s...", original_url[:50])
                    title = r.get("title", "")
                    if not title or not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    results.append({
                        "rank": base_rank + idx + 1,
                        "title": title,
                        "url": url,
                        "description": r.get("description", ""),
                    })

            if results:
                logger.debug("Bing parse succeeded on attempt %d (%d results)", parse_attempt, len(results))
                return results

            if parse_attempt < max_parse_attempts:
                delay = 0.3 * parse_attempt
                logger.debug("Bing parse attempt %d returned 0 results, retrying in %.1fs...", parse_attempt, delay)
                await asyncio.sleep(delay)

        except Exception as e:
            if parse_attempt < max_parse_attempts:
                logger.debug("Bing parse attempt %d failed: %s, retrying...", parse_attempt, e)
                await asyncio.sleep(0.3 * parse_attempt)
            else:
                logger.error("Failed to parse Bing results after %d attempts: %s", max_parse_attempts, e)

    return []


# ─────────────────────────────────────────────────────────────────────────
# Search implementation
# ─────────────────────────────────────────────────────────────────────────


async def _search_impl(
    query: str,
    page_num: int,
    proxy: Optional[dict] = None,
    headless: bool = False,
    source: str = "google",
) -> list[dict[str, Any]]:
    """Async search implementation using Camoufox browser.

    Args:
        query: Search query string.
        page_num: Page number (1-based).
        proxy: Optional proxy dict.
        headless: Run browser in headless mode.
        source: Search engine — "google" or "bing".

    Returns:
        List of result dicts.

    Raises:
        ParseError: If browser fails to start.
        CaptchaError: If CAPTCHA is detected.
        PageTimeoutError: If page load fails.
    """
    if source == "bing":
        offset = (page_num - 1) * 10 + 1
        url = BING_URL_TEMPLATE.format(query=query, offset=offset)
        captcha_msg = "CAPTCHA detected on Bing"
    else:
        start = (page_num - 1) * 10
        url = f"https://www.google.com/search?q={query}&start={start}&hl=en&gl=us&lr=lang_en"
        captcha_msg = "CAPTCHA detected on Google"

    logger.debug("Navigating to %s: %s", source, url)

    browser = await _create_browser(proxy, headless)
    if browser is None:
        raise ParseError("Failed to start browser — Camoufox may not be properly installed")

    try:
        page = await _create_page(browser)

        # Navigate to the search URL
        try:
            await page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            logger.debug("Navigation to %s failed: %s", url, e)
            raise PageTimeoutError(f"Failed to navigate to {source}") from e

        # Smart wait: wait for search results (or CAPTCHA page) to appear
        try:
            if source == "bing":
                await _wait_for_results(page, ["li.b_algo", "#b_results", "ol#b_results"], timeout=5)
                await asyncio.sleep(0.5)
            else:
                await _wait_for_results(page, ["div.g", "div#rso > div", "div.MjjYud", "div[data-hveid]"], timeout=5)
        except Exception as e:
            logger.debug("Smart wait for %s results timed out: %s", source, e)
            await asyncio.sleep(1)

        # Check for CAPTCHA / error pages
        current_url = (page.url or "").lower()
        if "sorry/app" in current_url or "/captcha/" in current_url:
            raise CaptchaError(captcha_msg)

        if not page.url or page.url == "about:blank":
            raise PageTimeoutError("Failed to navigate — page did not load")

        # Check page content for CAPTCHA or blocking patterns
        try:
            page_html = await _get_page_html(page)
            if _check_captcha(page.url, page_html):
                raise CaptchaError(captcha_msg)
        except CaptchaError:
            raise
        except Exception:
            pass

        # Parse results
        if source == "bing":
            results = await _parse_bing_results(page, page_num)
        else:
            results = await _parse_google_results(page, page_num)

        logger.debug("Parsed %d results from %s", len(results), source)

        if not results:
            raise ParseError(f"No results found for query '{query}' on {source} page {page_num}")

        return results

    except (CaptchaError, PageTimeoutError, ParseError):
        raise
    except asyncio.CancelledError:
        # Graceful shutdown: close the page before tearing down the browser
        # so that in-flight navigations don't leak TargetClosedError futures.
        if 'page' in locals():
            try:
                await page.close()
            except Exception:
                pass
        raise
    except Exception as e:
        logger.warning("Search failed: %s: %s", type(e).__name__, e)
        raise ParseError(str(e)) from e
    finally:
        # Clean up browser
        try:
            await _cleanup_browser(browser)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────
# Browser cleanup
# ─────────────────────────────────────────────────────────────────────────


async def _cleanup_browser(browser) -> None:
    """Stop Camoufox browser and clean up resources.

    Closes all open pages first so that in-flight navigations are cancelled
    cleanly, then tears down the browser context.  This prevents
    ``TargetClosedError`` futures from leaking when the browser is shut down
    while a page is still navigating (e.g. on Ctrl+C).
    """
    if browser is None:
        return

    # Close every open page to cancel any in-progress navigations.
    # This avoids "Future exception was never retrieved" warnings when the
    # browser context is destroyed while a ``page.goto()`` is pending.
    try:
        for page in browser.pages:
            try:
                await page.close()
            except Exception:
                pass
    except Exception:
        pass

    # Exit the AsyncCamoufox context manager (this handles browser.close())
    camoufox = getattr(browser, "_serp_camoufox", None)
    if camoufox is not None:
        try:
            await camoufox.__aexit__(None, None, None)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────
# Browser-based page fetch
# ─────────────────────────────────────────────────────────────────────────


async def _fetch_browser_impl(
    url: str,
    proxy: Optional[dict] = None,
    headless: bool = False,
) -> str:
    """Async browser fetch implementation using Camoufox.

    Navigates to the URL, waits for the page to load, and returns the
    content as cleaned Markdown.

    Args:
        url: Target URL to fetch.
        proxy: Optional proxy dict.
        headless: Run browser in headless mode.

    Returns:
        Page content as Markdown string.

    Raises:
        ParseError: If browser fails to start.
        PageTimeoutError: If page load fails.
        CaptchaError: If CAPTCHA is detected.
    """
    browser = await _create_browser(proxy, headless, block_images=True)
    if browser is None:
        raise ParseError("Failed to start browser — Camoufox may not be properly installed")

    try:
        page = await _create_page(browser)

        # Navigate to the target URL
        try:
            await page.goto(url, wait_until="domcontentloaded")
        except Exception as e:
            logger.debug("Navigation to %s failed: %s", url, e)
            raise PageTimeoutError(f"Failed to navigate to {url}") from e

        # Additional wait for JavaScript to execute
        await asyncio.sleep(2)

        # Verify page loaded
        if not page.url or page.url == "about:blank":
            raise PageTimeoutError("Page did not load — no URL returned")

        page_content = await _get_page_html(page)
        if _check_captcha(page.url, page_content):
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

    except asyncio.CancelledError:
        # Graceful shutdown: close the page before tearing down the browser
        # so that in-flight navigations don't leak TargetClosedError futures.
        if 'page' in locals():
            try:
                await page.close()
            except Exception:
                pass
        raise
    finally:
        try:
            await _cleanup_browser(browser)
        except Exception:
            pass
