"""Type definitions for SERP module."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Represents a single search result.

    Attributes:
        rank: Position in search results (1-based)
        title: Result title
        url: Target URL
        description: Result snippet/description
        source: Search engine source ("google" or "bing")
    """

    rank: int
    title: str
    url: str
    description: str = ""
    source: str = "google"

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        return {
            "rank": self.rank,
            "title": self.title,
            "url": self.url,
            "description": self.description,
            "source": self.source,
        }


@dataclass
class RetryPolicy:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts
        delay_min: Minimum delay between retries (seconds)
        delay_max: Maximum delay between retries (seconds)
        exponential_backoff: Whether to use exponential backoff
    """

    max_retries: int = 3
    delay_min: float = 0.5
    delay_max: float = 2.0
    exponential_backoff: bool = False

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number.

        Args:
            attempt: Current attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        import random

        if self.exponential_backoff:
            base = random.uniform(self.delay_min, self.delay_max)
            return min(base * (2 ** (attempt - 1)), self.delay_max)
        return random.uniform(self.delay_min, self.delay_max)


@dataclass
class ProxySettings:
    """Proxy configuration settings.

    Attributes:
        custom_proxies: List of custom proxy URLs from environment
        dataimpulse_gateway: DataImpulse gateway URL (gw.dataimpulse.com)
        dataimpulse_user: DataImpulse username
        dataimpulse_pass: DataImpulse password
        strategy: Proxy selection strategy ("random" or "dataimpulse_first")
        dataimpulse_protocol: Proxy protocol ("http" or "socks5")
        dataimpulse_country: Country code for targeting (e.g., "us", "de", "gb")
        dataimpulse_sessid: Session ID for sticky proxies (binds IP to session for ~30 min)
        dataimpulse_sessttl: Session TTL in minutes for sticky proxies (1-120)
    """

    custom_proxies: list[str] = field(default_factory=list)
    dataimpulse_gateway: Optional[str] = None
    dataimpulse_user: Optional[str] = None
    dataimpulse_pass: Optional[str] = None
    strategy: str = "dataimpulse_first"  # "random" or "dataimpulse_first"
    dataimpulse_protocol: str = "http"  # "http" or "socks5"
    dataimpulse_country: Optional[str] = None  # Country code like "us", "de"
    dataimpulse_sessid: Optional[str] = None  # Session ID for sticky proxy
    dataimpulse_sessttl: Optional[int] = None  # Session TTL in minutes (1-120)


@dataclass
class CacheSettings:
    """Cache configuration settings.

    Attributes:
        enabled: Whether caching is enabled
        cache_dir: Directory for disk cache
        ttl: Default time-to-live for cache entries (seconds)
    """

    enabled: bool = True
    cache_dir: str = ".cache/serp"
    ttl: int = 86400


@dataclass
class SearchSettings:
    """Search behavior settings.

    Attributes:
        source: Preferred search source ("google", "bing", "auto", or None for auto)
        timeout: Request timeout in seconds
        headless: Whether to run browser in headless mode
        user_agent: Custom user agent string (None for default rotating agents)
    """

    source: str = "auto"  # "google", "bing", "auto", or None
    timeout: int = 30
    headless: bool = False
    user_agent: Optional[str] = None


@dataclass
class LoggingSettings:
    """Logging configuration settings.

    Attributes:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        enabled: Whether logging is enabled
    """

    level: str = "WARNING"
    enabled: bool = True