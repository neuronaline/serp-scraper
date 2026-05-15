"""Utility functions, constants, and exception classes for SERP module."""

import asyncio
import base64
import logging
import os
import random
import urllib.parse
from typing import Optional, Union

import httpx
import markdownify

from .config import (
    BING_URL_TEMPLATE,
    USER_AGENTS,
)

# Configure module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    _default_level = logging.DEBUG if os.getenv("SERP_DEBUG") else logging.WARNING
    logger.setLevel(_default_level)


def set_log_level(level: Union[str, int]) -> None:
    """Set the log level for all serp loggers.

    Args:
        level: Log level as string ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
                or as integer (logging.DEBUG, etc.)

    Example:
        >>> from serp import set_log_level
        >>> set_log_level("DEBUG")  # Enable debug logging
        >>> set_log_level("WARNING")  # Only show warnings and errors

        Or with logging module:
        >>> import logging
        >>> from serp import set_log_level
        >>> set_log_level(logging.DEBUG)
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.WARNING)

    # Set level for all serp-related loggers
    for name in logging.Logger.manager.loggerDict:
        if name.startswith("serp"):
            logging.getLogger(name).setLevel(level)

    # Also set for the root serp logger and module-level logger
    logger.setLevel(level)

# Constants
MAX_RETRIES = int(os.getenv("SERP_MAX_RETRIES", "3"))
RETRY_DELAY_MIN = float(os.getenv("SERP_RETRY_DELAY_MIN", "0.5"))
RETRY_DELAY_MAX = float(os.getenv("SERP_RETRY_DELAY_MAX", "2.0"))
USE_EXPONENTIAL_BACKOFF = os.getenv("SERP_EXPONENTIAL_BACKOFF", "false").lower() == "true"
TIMEOUT_SECONDS = 30
TIMEOUT_MS = TIMEOUT_SECONDS * 1000  # Backward compatibility alias


class ProxyError(Exception):
    """All proxies failed."""
    pass


class CaptchaError(Exception):
    """Captcha could not be solved after retries."""
    pass


class PageTimeoutError(Exception):
    """Page load timeout."""
    pass


class ParseError(Exception):
    """Failed to parse results."""
    pass


def _random_user_agent() -> str:
    """Return a random user agent string."""
    return random.choice(USER_AGENTS)


def _build_chrome_proxy_arg(proxy: dict) -> Optional[str]:
    """Build proxy argument for Chrome's --proxy-server flag.

    Chrome does NOT support embedded credentials in --proxy-server.
    Returns just scheme://host:port (no user:pass). Authentication
    must be handled separately via CDP Fetch.authRequired event.

    Args:
        proxy: Proxy dict with 'server' key.

    Returns:
        Proxy URL string without credentials, e.g. 'http://gw.dataimpulse.com:823'
    """
    server = proxy.get("server")
    if not server:
        return None
    from urllib.parse import urlparse
    parsed = urlparse(server)
    scheme = parsed.scheme or "http"
    hostname = parsed.hostname or ""
    port_part = f":{parsed.port}" if parsed.port else ""
    return f"{scheme}://{hostname}{port_part}"


def _calculate_backoff_delay(attempt: int) -> float:
    """Calculate delay with exponential backoff and jitter.

    Args:
        attempt: Current attempt number (1-indexed)

    Returns:
        Delay in seconds
    """
    if USE_EXPONENTIAL_BACKOFF:
        # Exponential backoff: base * 2^(attempt-1) with jitter
        base_delay = random.uniform(RETRY_DELAY_MIN, RETRY_DELAY_MAX)
        exponential_delay = base_delay * (2 ** (attempt - 1))
        # Cap at max delay
        delay = min(exponential_delay, RETRY_DELAY_MAX)
    else:
        delay = random.uniform(RETRY_DELAY_MIN, RETRY_DELAY_MAX)
    return delay


async def _wait_random_delay_async(attempt: int = 1) -> None:
    """Wait random delay between retries with exponential backoff.

    Args:
        attempt: Current attempt number for exponential backoff calculation
    """
    delay = _calculate_backoff_delay(attempt)
    await asyncio.sleep(delay)


def _extract_bing_real_url(redirect_url: str) -> str:
    """Extract the real URL from a Bing redirect URL.

    Bing redirect URLs contain the actual URL encoded in the 'u' parameter.
    Example: https://www.bing.com/ck/a?...&u=a1aHR0cHM6Ly9sZWFybi5taWNyb3NvZnQuY29t...
    The 'u' parameter contains a base64-encoded URL with a 2-character prefix that
    needs to be stripped before decoding.
    """
    if not redirect_url or "bing.com/ck/a" not in redirect_url:
        return redirect_url

    try:
        parsed = urllib.parse.urlparse(redirect_url)
        query_params = urllib.parse.parse_qs(parsed.query)

        # The 'u' parameter contains the base64-encoded URL
        if "u" in query_params:
            encoded_url = query_params["u"][0]
            # Strip the 2-character prefix (usually 'a1') before the actual base64 data
            # The actual base64 string starts at index 2
            if len(encoded_url) > 2:
                encoded_url = encoded_url[2:]

            # Add padding if needed
            padding_needed = (4 - len(encoded_url) % 4) % 4
            encoded_url += "=" * padding_needed

            # Decode base64
            decoded = base64.b64decode(encoded_url).decode("utf-8")
            return decoded
    except Exception as e:
        logger.debug(f"Failed to decode Bing redirect URL: {e}")

    return redirect_url
