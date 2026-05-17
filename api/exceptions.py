"""Custom exceptions for the API."""

from typing import Any, Optional


class APIError(Exception):
    """Base exception for API errors."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
        status_code: int = 500,
    ):
        """Initialize API error.

        Args:
            code: Error code (e.g., "RATE_LIMIT_EXCEEDED")
            message: Human-readable error message
            details: Additional error details
            status_code: HTTP status code
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code


class RateLimitExceededError(APIError):
    """Raised when rate limit is exceeded."""

    def __init__(self, limit: int, window: str = "1 minute"):
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message=f"Rate limit exceeded. Try again in {window}.",
            details={"limit": limit, "window": window},
            status_code=429,
        )


class SearchError(APIError):
    """Raised when a search operation fails."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            code="SEARCH_ERROR",
            message=message,
            details=details,
            status_code=500,
        )


class FetchError(APIError):
    """Raised when a fetch operation fails."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            code="FETCH_ERROR",
            message=message,
            details=details,
            status_code=500,
        )


class NewsError(APIError):
    """Raised when a news operation fails."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            code="NEWS_ERROR",
            message=message,
            details=details,
            status_code=500,
        )


class ValidationError(APIError):
    """Raised when request validation fails."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            details=details,
            status_code=400,
        )
