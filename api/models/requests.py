"""Request models for the API."""

from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class SearchRequest(BaseModel):
    """Search endpoint request."""

    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    page: int = Field(default=1, ge=1, le=100, description="Page number (1-based)")
    source: Optional[str] = Field(
        default=None,
        description="Search source: 'google', 'bing', or None (auto)",
    )
    method: Optional[str] = Field(
        default=None,
        description="Search method: 'browser', 'http', or None (auto)",
    )


class FetchRequest(BaseModel):
    """Fetch endpoint request."""

    url: HttpUrl = Field(..., description="URL to fetch")
    prefer_browser: bool = Field(
        default=True, description="Use browser (nodriver) instead of HTTP"
    )


class NewsRequest(BaseModel):
    """News endpoint request."""

    query: str = Field(..., min_length=1, max_length=500, description="News search query")
    max_results: int = Field(
        default=50, ge=1, le=100, description="Maximum number of results"
    )
    language: str = Field(default="tr", description="Language code (tr/en)")
    country: Optional[str] = Field(
        default=None, description="Country code (TR/US). Auto-derived from language."
    )
