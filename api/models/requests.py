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
        default=True, description="Deprecated, ignored (browser is always used)"
    )
    compress: bool = Field(
        default=False,
        description="Compress long content (>10K chars). When enabled, takes head, middle, "
                    "and tail portions, marking the truncated section."
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


class ScholarRequest(BaseModel):
    """Scholar endpoint request."""

    query: str = Field(..., min_length=1, max_length=500, description="Scholar search query")
    max_results: int = Field(
        default=50, ge=1, le=100, description="Maximum number of results"
    )
    language: str = Field(default="en", description="Language code (en/tr/etc)")
    year_from: Optional[int] = Field(
        default=None, ge=1900, le=2030, description="Start year for publication range"
    )
    year_to: Optional[int] = Field(
        default=None, ge=1900, le=2030, description="End year for publication range"
    )
    sort_by: str = Field(
        default="relevance",
        description="Sort order: 'relevance' or 'date'"
    )
    # Advanced search parameters
    exact_phrase: Optional[str] = Field(
        default=None, description="Exact phrase search (as_epq)"
    )
    some_words: Optional[str] = Field(
        default=None, description="At least one of the words (as_oq)"
    )
    without_words: Optional[str] = Field(
        default=None, description="Without these words (as_eq)"
    )
    author: Optional[str] = Field(
        default=None, description="Search by author name (as_sauthors)"
    )
    publication: Optional[str] = Field(
        default=None, description="Publication name (as_publication)"
    )
