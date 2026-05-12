"""Response models for the API."""

from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Error detail structure."""

    code: str = Field(..., description="Error code (e.g., RATE_LIMIT_EXCEEDED)")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict[str, Any]] = Field(
        default=None, description="Additional error details"
    )


class ResponseMeta(BaseModel):
    """Metadata included in all API responses."""

    request_id: str = Field(..., description="Unique request identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Response timestamp"
    )
    rate_limit_remaining: Optional[int] = Field(
        default=None, description="Remaining requests in current window"
    )
    rate_limit_reset: Optional[int] = Field(
        default=None, description="Seconds until rate limit reset"
    )


class APIResponse(BaseModel, Generic[T]):
    """Generic API response wrapper.

    All endpoints return responses in this format.

    Example success response:
        {
            "success": True,
            "data": [...],
            "error": None,
            "meta": {
                "request_id": "abc123",
                "timestamp": "2026-05-12T06:47:19.030Z",
                "rate_limit_remaining": 25,
                "rate_limit_reset": 45
            }
        }

    Example error response:
        {
            "success": False,
            "data": None,
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Rate limit exceeded for /search",
                "details": {"limit": 30, "window": "1 minute"}
            },
            "meta": {...}
        }
    """

    success: bool = Field(..., description="Whether the request succeeded")
    data: Optional[T] = Field(default=None, description="Response data")
    error: Optional[ErrorDetail] = Field(
        default=None, description="Error information if request failed"
    )
    meta: ResponseMeta = Field(..., description="Response metadata")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Check timestamp"
    )
