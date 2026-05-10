"""Pydantic-based configuration for SERP module.

This module provides validated configuration using Pydantic, with support
for environment variables and .env files.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from .types import CacheSettings, LoggingSettings, ProxySettings, RetryPolicy, SearchSettings

# Environment variable names
ENV_DOTENV_FILE = "SERP_DOTENV_FILE"
ENV_CONFIG_FILE = "SERP_CONFIG_FILE"

# DataImpulse default ports (from documentation)
DATAIMPULSE_HTTP_PORT = 823  # HTTP/HTTPS rotating
DATAIMPULSE_SOCKS5_PORT = 824  # SOCKS5 rotating
DATAIMPULSE_STICKY_PORT_RANGE = (10000, 20000)  # Sticky proxy port range


class SerpBaseConfig(BaseModel):
    """Base configuration with common settings."""

    proxy: ProxySettings = Field(default_factory=ProxySettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    search: SearchSettings = Field(default_factory=SearchSettings)

    model_config = {
        "extra": "ignore",
        "populate_by_name": True,
    }


class SerpConfig(SerpBaseConfig):
    """Main configuration class for SERP client.

    Supports loading from:
    - Environment variables
    - .env file (if python-dotenv is installed)
    - Direct parameter passing

    Environment variables take precedence over .env file.

    Example .env file:
        SERP_DATAIMPULSE_GATEWAY=gateway.example.com
        SERP_DATAIMPULSE_USER=myuser
        SERP_DATAIMPULSE_PASS=mypass
        SERP_LOG_LEVEL=DEBUG
        SERP_CACHE_ENABLED=true
        SERP_CACHE_TTL=86400
        SERP_MAX_RETRIES=3
        SERP_TIMEOUT=30

    Example usage:
        >>> from serp import SerpConfig
        >>> config = SerpConfig()
        >>> config = SerpConfig(log_level="DEBUG")
    """

    # Top-level settings that map to nested objects
    log_level: str = Field(default="WARNING", alias="SERP_LOG_LEVEL")

    # DataImpulse settings
    dataimpulse_gateway: Optional[str] = Field(default=None, alias="SERP_DATAIMPULSE_GATEWAY")
    dataimpulse_user: Optional[str] = Field(default=None, alias="SERP_DATAIMPULSE_USER")
    dataimpulse_pass: Optional[str] = Field(default=None, alias="SERP_DATAIMPULSE_PASS")
    dataimpulse_protocol: str = Field(default="http", alias="SERP_DATAIMPULSE_PROTOCOL")
    dataimpulse_country: Optional[str] = Field(default=None, alias="SERP_DATAIMPULSE_COUNTRY")
    dataimpulse_sessid: Optional[str] = Field(default=None, alias="SERP_DATAIMPULSE_SESSID")
    dataimpulse_sessttl: Optional[int] = Field(default=None, alias="SERP_DATAIMPULSE_SESSTTL")

    # Custom proxies (comma-separated in env var)
    custom_proxies: str = Field(default="", alias="SERP_CUSTOM_PROXIES")

    # Proxy strategy
    proxy_strategy: str = Field(default="dataimpulse_first", alias="SERP_PROXY_STRATEGY")

    # Cache settings
    cache_enabled: bool = Field(default=True, alias="SERP_CACHE_ENABLED")
    cache_dir: str = Field(default=".cache/serp", alias="SERP_CACHE_DIR")
    cache_ttl: int = Field(default=86400, alias="SERP_CACHE_TTL")

    # Retry settings
    max_retries: int = Field(default=3, alias="SERP_MAX_RETRIES")
    retry_delay_min: float = Field(default=0.5, alias="SERP_RETRY_DELAY_MIN")
    retry_delay_max: float = Field(default=2.0, alias="SERP_RETRY_DELAY_MAX")
    exponential_backoff: bool = Field(default=False, alias="SERP_EXPONENTIAL_BACKOFF")

    # Search settings
    timeout: int = Field(default=30, alias="SERP_TIMEOUT")
    default_source: str = Field(default="auto", alias="SERP_DEFAULT_SOURCE")
    headless: bool = Field(default=False, alias="SERP_HEADLESS")
    user_agent: Optional[str] = Field(default=None, alias="SERP_USER_AGENT")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            logging.warning(f"Invalid log level '{v}', using WARNING")
            return "WARNING"
        return v_upper

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        if v < 1:
            logging.warning(f"max_retries must be >= 1, got {v}, using 1")
            return 1
        if v > 10:
            logging.warning(f"max_retries should be <= 10, got {v}, using 10")
            return 10
        return v

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 5:
            logging.warning(f"timeout must be >= 5, got {v}, using 5")
            return 5
        if v > 120:
            logging.warning(f"timeout should be <= 120, got {v}, using 120")
            return 120
        return v

    @field_validator("cache_ttl")
    @classmethod
    def validate_cache_ttl(cls, v: int) -> int:
        if v < 60:
            logging.warning(f"cache_ttl must be >= 60, got {v}, using 60")
            return 60
        return v

    @field_validator("proxy_strategy")
    @classmethod
    def validate_proxy_strategy(cls, v: str) -> str:
        valid_strategies = {"random", "dataimpulse_first"}
        if v.lower() not in valid_strategies:
            logging.warning(f"Invalid proxy_strategy '{v}', using 'dataimpulse_first'")
            return "dataimpulse_first"
        return v.lower()

    @field_validator("default_source")
    @classmethod
    def validate_default_source(cls, v: str) -> str:
        valid_sources = {"auto", "google", "bing"}
        if v.lower() not in valid_sources:
            logging.warning(f"Invalid default_source '{v}', using 'auto'")
            return "auto"
        return v.lower()

    def __init__(self, **data: Any):
        # Try to load from .env file first (if python-dotenv is available)
        self._load_dotenv()

        # Apply environment variable overrides
        self._apply_env_overrides(data)

        # Call Pydantic init
        super().__init__(**data)

        # Build nested settings objects
        self._build_nested_settings()

    def _load_dotenv(self) -> None:
        """Load settings from .env file if available."""
        try:
            from dotenv import find_dotenv, load_dotenv

            dotenv_file = os.getenv(ENV_DOTENV_FILE)
            if dotenv_file:
                load_dotenv(dotenv_file)
            else:
                dotenv_path = find_dotenv(usecwd=True)
                if dotenv_path:
                    load_dotenv(dotenv_path)
        except ImportError:
            # python-dotenv not installed, skip .env loading
            pass

    def _apply_env_overrides(self, data: dict[str, Any]) -> None:
        """Apply environment variable overrides to data."""
        env_mappings = {
            "SERP_LOG_LEVEL": "log_level",
            "SERP_DATAIMPULSE_GATEWAY": "dataimpulse_gateway",
            "SERP_DATAIMPULSE_USER": "dataimpulse_user",
            "SERP_DATAIMPULSE_PASS": "dataimpulse_pass",
            "SERP_DATAIMPULSE_PROTOCOL": "dataimpulse_protocol",
            "SERP_DATAIMPULSE_COUNTRY": "dataimpulse_country",
            "SERP_DATAIMPULSE_SESSID": "dataimpulse_sessid",
            "SERP_DATAIMPULSE_SESSTTL": "dataimpulse_sessttl",
            "SERP_CUSTOM_PROXIES": "custom_proxies",
            "SERP_PROXY_STRATEGY": "proxy_strategy",
            "SERP_CACHE_ENABLED": "cache_enabled",
            "SERP_CACHE_DIR": "cache_dir",
            "SERP_CACHE_TTL": "cache_ttl",
            "SERP_MAX_RETRIES": "max_retries",
            "SERP_RETRY_DELAY_MIN": "retry_delay_min",
            "SERP_RETRY_DELAY_MAX": "retry_delay_max",
            "SERP_EXPONENTIAL_BACKOFF": "exponential_backoff",
            "SERP_TIMEOUT": "timeout",
            "SERP_DEFAULT_SOURCE": "default_source",
            "SERP_HEADLESS": "headless",
            "SERP_USER_AGENT": "user_agent",
        }

        for env_var, field_name in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None and field_name not in data:
                # Type coercion
                if field_name in ("cache_enabled", "exponential_backoff", "headless"):
                    value = value.lower() in ("true", "1", "yes")
                elif field_name in ("max_retries", "cache_ttl", "timeout", "dataimpulse_sessttl"):
                    try:
                        value = int(value)
                    except ValueError:
                        continue
                elif field_name in ("retry_delay_min", "retry_delay_max"):
                    try:
                        value = float(value)
                    except ValueError:
                        continue
                # custom_proxies is comma-separated string, keep as string for now
                data[field_name] = value

    def _build_nested_settings(self) -> None:
        """Build nested settings objects from flat configuration."""
        # Parse custom_proxies from comma-separated string
        custom_proxies_list = []
        if self.custom_proxies:
            custom_proxies_list = [p.strip() for p in self.custom_proxies.split(",") if p.strip()]

        self.proxy = ProxySettings(
            custom_proxies=custom_proxies_list,
            dataimpulse_gateway=self.dataimpulse_gateway,
            dataimpulse_user=self.dataimpulse_user,
            dataimpulse_pass=self.dataimpulse_pass,
            strategy=self.proxy_strategy,
            dataimpulse_protocol=self.dataimpulse_protocol,
            dataimpulse_country=self.dataimpulse_country,
            dataimpulse_sessid=self.dataimpulse_sessid,
            dataimpulse_sessttl=self.dataimpulse_sessttl,
        )

        self.cache = CacheSettings(
            enabled=self.cache_enabled,
            cache_dir=self.cache_dir,
            ttl=self.cache_ttl,
        )

        self.logging = LoggingSettings(
            level=self.log_level,
            enabled=True,
        )

        self.retry = RetryPolicy(
            max_retries=self.max_retries,
            delay_min=self.retry_delay_min,
            delay_max=self.retry_delay_max,
            exponential_backoff=self.exponential_backoff,
        )

        # Map default_source to source (None = auto mode)
        source_map = {"auto": None, "google": "google", "bing": "bing"}
        source_value = source_map.get(self.default_source.lower() if isinstance(self.default_source, str) else "auto", None)

        self.search = SearchSettings(
            source=source_value,
            timeout=self.timeout,
            headless=self.headless,
            user_agent=self.user_agent,
        )

    def get_nested_dict(self) -> dict[str, Any]:
        """Get configuration as nested dictionary (for backward compatibility)."""
        return {
            "custom_proxies": self.custom_proxies,
            "proxy_strategy": self.proxy_strategy,
            "log_level": self.log_level,
            "dataimpulse_gateway": self.dataimpulse_gateway,
            "dataimpulse_user": self.dataimpulse_user,
            "dataimpulse_pass": self.dataimpulse_pass,
            "dataimpulse_protocol": self.dataimpulse_protocol,
            "dataimpulse_country": self.dataimpulse_country,
            "dataimpulse_sessid": self.dataimpulse_sessid,
            "dataimpulse_sessttl": self.dataimpulse_sessttl,
            "cache_enabled": self.cache_enabled,
            "cache_dir": self.cache_dir,
            "cache_ttl": self.cache_ttl,
            "max_retries": self.max_retries,
            "retry_delay_min": self.retry_delay_min,
            "retry_delay_max": self.retry_delay_max,
            "exponential_backoff": self.exponential_backoff,
            "timeout": self.timeout,
            "default_source": self.default_source,
            "headless": self.headless,
            "user_agent": self.user_agent,
        }


# Global default config instance
_default_config: Optional[SerpConfig] = None


def get_default_config() -> SerpConfig:
    """Get or create the default configuration instance.

    Returns:
        Default SerpConfig instance
    """
    global _default_config
    if _default_config is None:
        _default_config = SerpConfig()
    return _default_config


def reset_default_config() -> None:
    """Reset the default configuration instance.

    Useful for testing or when configuration changes.
    """
    global _default_config
    _default_config = None