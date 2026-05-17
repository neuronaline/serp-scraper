"""API configuration using Pydantic Settings."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class RateLimitConfig(BaseSettings):
    """Rate limit configuration per endpoint."""

    search: int = Field(default=30, ge=1, description="Requests per minute for /search")
    fetch: int = Field(default=60, ge=1, description="Requests per minute for /fetch")
    news: int = Field(default=30, ge=1, description="Requests per minute for /news")
    default: int = Field(default=100, ge=1, description="Default requests per minute")


class APISettings(BaseSettings):
    """Main API settings."""

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, ge=1, le=65535, description="Server port")
    debug: bool = Field(default=False, description="Debug mode")

    # Request processing
    max_concurrent_requests: int = Field(
        default=15, ge=1, le=100, description="Max concurrent requests (pool size)"
    )
    request_timeout: int = Field(
        default=60, ge=5, le=300, description="Request timeout in seconds"
    )

    # Rate limiting
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)

    # API Keys (comma-separated hashed keys)
    api_keys_hashed: str = Field(
        default="",
        alias="API_KEYS_HASHED",
        description="Comma-separated list of hashed API keys",
    )
    allow_no_auth: bool = Field(
        default=False,
        description="Allow unauthenticated access when API_KEYS_HASHED is empty (not recommended for production)",
    )

    def get_api_keys(self) -> list[str]:
        """Get list of hashed API keys."""
        if not self.api_keys_hashed:
            return []
        return [k.strip() for k in self.api_keys_hashed.split(",") if k.strip()]

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    log_dir: Path = Field(
        default=Path("logs"),
        description="Directory for log files",
    )
    log_retention_days: int = Field(
        default=7, ge=1, description="Number of days to retain logs"
    )

    # CORS
    cors_origins: str = Field(
        default="",
        description="Comma-separated list of allowed origins for CORS (empty = no CORS)",
    )

    class Config:
        env_prefix = "API_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Global settings instance
_settings: Optional[APISettings] = None


def get_settings() -> APISettings:
    """Get or create the global settings instance."""
    global _settings
    if _settings is None:
        _settings = APISettings()
    return _settings


def reset_settings() -> None:
    """Reset the global settings instance (for testing)."""
    global _settings
    _settings = None
