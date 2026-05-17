"""Pydantic-based configuration for SERP module.

This module provides validated configuration using Pydantic, with support
for environment variables and .env files.
"""

import logging
import os
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings

from .types import CacheSettings, LoggingSettings, ProxySettings, RetryPolicy, SearchSettings

# DataImpulse default ports (from documentation)
DATAIMPULSE_HTTP_PORT = 823
DATAIMPULSE_SOCKS5_PORT = 824
DATAIMPULSE_STICKY_PORT_RANGE = (10000, 20000)


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


class SerpConfig(BaseSettings, SerpBaseConfig):
    """Main configuration class for SERP client.

    Supports loading from environment variables and direct parameter passing.
    Environment variables use the prefix SERP_ (e.g., SERP_LOG_LEVEL, SERP_TIMEOUT).

    Example .env file:
        SERP_DATAIMPULSE_GATEWAY=gateway.example.com
        SERP_DATAIMPULSE_USER=myuser
        SERP_LOG_LEVEL=DEBUG
        SERP_CACHE_ENABLED=true
        SERP_MAX_RETRIES=3

    Example usage:
        >>> from serp import SerpConfig
        >>> config = SerpConfig()
        >>> config = SerpConfig(log_level="DEBUG")
    """

    model_config = BaseSettings.model_config | {
        "env_prefix": "SERP_",
        "extra": "ignore",
    }

    # Top-level settings
    log_level: str = Field(default="WARNING")

    # DataImpulse settings
    dataimpulse_gateway: Optional[str] = None
    dataimpulse_user: Optional[str] = None
    dataimpulse_pass: Optional[str] = None
    dataimpulse_protocol: str = "http"
    dataimpulse_country: Optional[str] = None
    dataimpulse_sessid: Optional[str] = None
    dataimpulse_sessttl: Optional[int] = None

    # Custom proxies (comma-separated)
    custom_proxies: str = ""

    # Proxy strategy
    proxy_strategy: str = "dataimpulse_first"

    # Cache settings
    cache_enabled: bool = True
    cache_dir: str = ".cache/serp"
    cache_ttl: int = 86400

    # Retry settings
    max_retries: int = 3
    retry_delay_min: float = 0.5
    retry_delay_max: float = 2.0
    exponential_backoff: bool = False

    # Search settings
    timeout: int = 30
    default_source: str = "auto"
    headless: bool = False
    user_agent: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _handle_empty_strings(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Handle empty string env var values by removing them so defaults are used."""
        if not isinstance(values, dict):
            return values
        # Fields that should use default when env var is empty string
        # (removing the key lets Pydantic use the field default)
        empty_uses_default = {
            "cache_ttl", "max_retries", "timeout", "retry_delay_min",
            "retry_delay_max", "dataimpulse_sessttl",
        }
        for key in empty_uses_default:
            if key in values and values[key] == "":
                del values[key]
        return values

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
        if v is None:
            return 3
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
        if v is None:
            return 30
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
        if v is None:
            return 86400
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

    @model_validator(mode="after")
    def _build_nested_settings(self) -> "SerpConfig":
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
        source_value = source_map.get(self.default_source.lower(), None)

        self.search = SearchSettings(
            source=source_value,
            timeout=self.timeout,
            headless=self.headless,
            user_agent=self.user_agent,
        )

        return self

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