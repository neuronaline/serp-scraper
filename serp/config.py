"""Proxy configuration and random selection."""

import json
import os
import random
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Bing URL template
BING_URL_TEMPLATE = "https://www.bing.com/search?q={query}&first={offset}"
GOOGLE_URL_TEMPLATE = "https://www.google.com/search?q={query}&start={start}"

# Essential args - always added (minimal set for functionality)
# Note: nodriver handles most stealth settings automatically
ESSENTIAL_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

# User agents for rotation (fresh 2026 versions)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7; rv:140.0) Gecko/20100101 Firefox/140.0",
]

# Environment variable names for DataImpulse credentials
ENV_DATAIMPULSE_GATEWAY = "SERP_DATAIMPULSE_GATEWAY"
ENV_DATAIMPULSE_USER = "SERP_DATAIMPULSE_USER"
ENV_DATAIMPULSE_PASS = "SERP_DATAIMPULSE_PASS"
ENV_PROXY_FILE = "SERP_PROXY_FILE"


class ProxyConfig:
    """Proxy configuration loader and selector."""

    def __init__(self, proxy_file: Optional[str] = None):
        # Allow environment variable override for proxy file path
        if proxy_file is None:
            proxy_file = os.getenv(ENV_PROXY_FILE, "proxies.json")
        self.proxy_file = Path(proxy_file)
        self._dataimpulse: Optional[dict] = None
        self._proxies: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Load proxy configuration from JSON file and environment variables.

        Environment variables take precedence over file-based configuration
        for DataImpulse credentials. All three DataImpulse env vars must be
        set together to be used.
        """
        # Load from file first
        if self.proxy_file.exists():
            try:
                with open(self.proxy_file) as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse proxy file: {e}")
                raise ValueError(f"Invalid JSON in proxy file: {self.proxy_file}") from e

            self._dataimpulse = data.get("dataimpulse")
            self._proxies = data.get("proxies", [])
        else:
            logger.warning(f"Proxy file not found: {self.proxy_file}")
            self._dataimpulse = None
            self._proxies = []

        # Override with environment variables if ALL required DataImpulse vars are set
        env_gateway = os.getenv(ENV_DATAIMPULSE_GATEWAY)
        env_user = os.getenv(ENV_DATAIMPULSE_USER)
        env_pass = os.getenv(ENV_DATAIMPULSE_PASS)

        # Only use env vars if all three are provided together
        if env_gateway and env_user and env_pass:
            logger.debug("Using DataImpulse credentials from environment variables")
            self._dataimpulse = {
                "gateway": env_gateway,
                "username": env_user,
                "password": env_pass,
            }
        elif env_gateway or env_user or env_pass:
            logger.warning("DataImpulse environment variables partially set, ignoring. Set all three (GATEWAY, USER, PASS) or none.")

        logger.debug(f"Loaded {len(self._proxies)} proxies, DI: {bool(self._dataimpulse)}")

    def _normalize_password(self, password: str) -> Optional[str]:
        """Normalize empty string to None."""
        return password if password else None

    def get_random_proxy(self, prefer_dataimpulse: bool = True) -> Optional[dict]:
        """
        Get a random proxy configuration.

        Args:
            prefer_dataimpulse: If True and DataImpulse is configured, always return it.
                                 Otherwise randomly select from all proxies.

        Returns:
            Proxy dict with 'server', 'username', 'password' keys,
            or None if no proxy available.
        """
        candidates = []

        # If DataImpulse is configured and preferred, use it
        if prefer_dataimpulse and self._dataimpulse and self._dataimpulse.get("gateway"):
            proxy = {
                "server": self._dataimpulse["gateway"],
                "username": self._dataimpulse.get("username"),
                "password": self._normalize_password(self._dataimpulse.get("password")),
            }
            logger.debug(f"Selected DataImpulse proxy: {proxy['server']}")
            return proxy

        # Add dataimpulse if configured with valid gateway
        if self._dataimpulse and self._dataimpulse.get("gateway"):
            candidates.append({
                "server": self._dataimpulse["gateway"],
                "username": self._dataimpulse.get("username"),
                "password": self._normalize_password(self._dataimpulse.get("password")),
            })

        # Add standard proxies
        for p in self._proxies:
            url = p.get("url")
            if not url:
                logger.warning(f"Proxy entry missing 'url' key, skipping: {p}")
                continue
            # Parse user:pass from url if present using proper URL parsing
            if "@" in url:
                parsed = urlparse(url)
                # Determine protocol from URL scheme - use parsed scheme, not string prefix
                proto = parsed.scheme if parsed.scheme else "http"
                hostname = parsed.hostname if parsed.hostname else ""
                # Include credentials in server URL for proper proxy auth
                if parsed.username and parsed.password:
                    auth_part = f"{parsed.username}:{parsed.password}@"
                elif parsed.username:
                    auth_part = f"{parsed.username}@"
                else:
                    auth_part = ""
                if parsed.port:
                    server = f"{proto}://{auth_part}{hostname}:{parsed.port}"
                else:
                    server = f"{proto}://{auth_part}{hostname}"
                candidates.append({
                    "server": server,
                    "username": parsed.username,
                    "password": self._normalize_password(parsed.password),
                })
            else:
                # No credentials - use parsed scheme or detect from prefix
                parsed = urlparse(url)
                if parsed.scheme:
                    # URL has proper scheme (http, https, socks5)
                    candidates.append({
                        "server": url,
                        "username": None,
                        "password": None,
                    })
                else:
                    # No scheme - assume http and add prefix
                    candidates.append({
                        "server": f"http://{url}",
                        "username": None,
                        "password": None,
                    })

        if not candidates:
            logger.warning("No proxies available")
            return None

        proxy = random.choice(candidates)
        logger.debug(f"Selected proxy: {proxy['server']}")
        return proxy

    @property
    def has_proxies(self) -> bool:
        """Check if any proxy is configured."""
        return bool(self._dataimpulse or self._proxies)


# Global config instance
_config: Optional[ProxyConfig] = None


def load_config(proxy_file: Optional[str] = None) -> ProxyConfig:
    """Load or reload proxy configuration.

    Args:
        proxy_file: Path to proxies.json. If None, uses SERP_PROXY_FILE env var
                   or defaults to 'proxies.json'.

    Raises:
        ValueError: If proxy_file is an empty string.
    """
    if proxy_file is not None and not proxy_file:
        raise ValueError("proxy_file cannot be empty string")
    global _config
    _config = ProxyConfig(proxy_file)
    return _config


def get_config() -> ProxyConfig:
    """Get current config instance, loading default if needed."""
    global _config
    if _config is None:
        _config = ProxyConfig()
    return _config