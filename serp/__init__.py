"""SERP search and page fetch with Camoufox.

This module provides functions for searching search engines (Google, Bing)
and fetching web pages, with support for proxies, caching, and CAPTCHA handling.

Example:
    Basic usage with SerpClient (recommended):

    >>> import asyncio
    >>> from serp import SerpClient
    >>>
    >>> async def main():
    ...     async with SerpClient() as client:
    ...         results = await client.search("python tutorial")
    ...         for r in results:
    ...             print(f"{r.rank}. {r.title} - {r.url}")
    ...
    >>> asyncio.run(main())

    Using module-level convenience functions:

    >>> from serp import quick_search, quick_fetch
    >>> results = await quick_search("python tutorial")
    >>> content = await quick_fetch("https://example.com")

    Using .env file for configuration:
    Create a .env file in your project root:
        SERP_DATAIMPULSE_GATEWAY=gateway.example.com
        SERP_DATAIMPULSE_USER=myuser
        SERP_DATAIMPULSE_PASS=mypass
        SERP_LOG_LEVEL=DEBUG
        SERP_CUSTOM_PROXIES=http://user:pass@proxy.com:8080

    Configuration with SerpConfig:

    >>> from serp import SerpClient, SerpConfig
    >>> config = SerpConfig(
    ...     log_level="DEBUG",
    ...     max_retries=5,
    ...     cache_ttl=3600,  # 1 hour
    ... )
    >>> client = SerpClient(config)
"""

# Core classes
from .client import SerpClient, get_default_client, reset_default_client
from .types import (
    SearchResult,
    RetryPolicy,
    ProxySettings,
    CacheSettings,
    SearchSettings,
    LoggingSettings,
)
from .config_pydantic import SerpConfig

# Browser stealth / anti-detection
from .browser_stealth import (
    FingerprintProfile,
    DEFAULT_FINGERPRINT,
)

# Convenience functions (use default client)
from .client import quick_search, quick_fetch, quick_search_http

# Google News RSS module
from .google_news import (
    GoogleNewsClient,
    NewsResult,
    NewsSettings,
    quick_news,
    get_default_client as get_google_news_default_client,
    reset_default_client as reset_google_news_default_client,
)

# Google Scholar module
from .google_scholar import (
    ScholarClient,
    ScholarResult,
    ScholarSettings,
    quick_scholar,
    get_default_client as get_scholar_default_client,
    reset_default_client as reset_scholar_default_client,
)

# Content compression utilities
from .compression import (
    CompressionMeta,
    compress_content,
)

# Utilities
from .utils import (
    ProxyError,
    CaptchaError,
    PageTimeoutError,
    ParseError,
    VirtualScreenRequiredError,
    MAX_RETRIES,
    TIMEOUT_MS,
    USER_AGENTS,
    set_log_level,
)

# Output formatting
from .output_formatter import (
    OutputFormatter,
    TextFormatter,
    JSONFormatter,
    OutputError,
    OUTPUT_TEXT,
    OUTPUT_JSON,
)

__all__ = [
    # Core class (recommended)
    "SerpClient",
    # Configuration
    "SerpConfig",
    "SearchResult",
    "RetryPolicy",
    "ProxySettings",
    "CacheSettings",
    "SearchSettings",
    "LoggingSettings",
    # Browser stealth / anti-detection
    "FingerprintProfile",
    "DEFAULT_FINGERPRINT",
    # Convenience functions (use default client, recommended for simple use)
    "quick_search",
    "quick_fetch",
    "quick_search_http",
    # Utilities
    "set_log_level",
    "get_default_client",
    "reset_default_client",
    # Content compression
    "CompressionMeta",
    "compress_content",
    # Exceptions
    "ProxyError",
    "CaptchaError",
    "PageTimeoutError",
    "ParseError",
    "VirtualScreenRequiredError",
    # Constants
    "MAX_RETRIES",
    "TIMEOUT_MS",
    "USER_AGENTS",
    # Google News RSS
    "GoogleNewsClient",
    "NewsResult",
    "NewsSettings",
    "quick_news",
    "get_google_news_default_client",
    "reset_google_news_default_client",
    # Google Scholar
    "ScholarClient",
    "ScholarResult",
    "ScholarSettings",
    "quick_scholar",
    "get_scholar_default_client",
    "reset_scholar_default_client",
    # Output formatting
    "OutputFormatter",
    "OutputError",
    "OUTPUT_TEXT",
    "OUTPUT_JSON",
]