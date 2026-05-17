"""Scholar endpoint router."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request

from api.deps import RateLimitInfo, rate_limited_request, news_rate_limit
from api.middleware.logging_middleware import get_logger
from api.models.requests import ScholarRequest
from api.models.responses import APIResponse, ErrorDetail, ResponseMeta
from serp.google_scholar import ScholarClient
from serp.utils import CaptchaError, PageTimeoutError, ParseError, ProxyError

router = APIRouter(prefix="/api/v1/scholar", tags=["Scholar"])
logger = get_logger("api.routers.scholar")


@router.post("", response_model=APIResponse[list[dict]])
async def scholar_endpoint(
    request: Request,
    params: ScholarRequest,
    _rate_info: Annotated[RateLimitInfo, Depends(news_rate_limit)],
) -> APIResponse[list[dict]]:
    """Search Google Scholar for academic papers.

    Args:
        request: FastAPI request object
        params: Scholar search parameters
        _rate_info: Rate limit info (from dependency, after API key verified)

    Returns:
        APIResponse containing Scholar results
    """
    request_id = str(uuid.uuid4())[:8]

    # Apply request pool limiting
    async with rate_limited_request():
        logger.info(
            f"Scholar request: query='{params.query}' language='{params.language}' "
            f"year_from={params.year_from} year_to={params.year_to} "
            f"max_results={params.max_results} | request_id={request_id}"
        )

        try:
            # Build advanced search params
            advanced_params = {}
            if params.exact_phrase:
                advanced_params["as_epq"] = params.exact_phrase
            if params.some_words:
                advanced_params["as_oq"] = params.some_words
            if params.without_words:
                advanced_params["as_eq"] = params.without_words
            if params.author:
                advanced_params["as_sauthors"] = params.author
            if params.publication:
                advanced_params["as_publication"] = params.publication

            async with ScholarClient(
                language=params.language,
                year_from=params.year_from,
                year_to=params.year_to,
                sort_by=params.sort_by,
            ) as client:
                scholar_results = await client.search_scholar(
                    params.query,
                    max_results=params.max_results,
                    advanced_params=advanced_params if advanced_params else None,
                )

            # Convert results to dict format
            scholar_data = [
                {
                    "title": r.title,
                    "url": r.url,
                    "scholar_url": r.scholar_url,
                    "snippet": r.snippet,
                    "authors": r.authors,
                    "publication_year": r.publication_year,
                    "venue": r.venue,
                    "citation_count": r.citation_count,
                    "pdf_url": r.pdf_url,
                    "cluster_id": r.cluster_id,
                }
                for r in scholar_results
            ]

            logger.info(
                f"Scholar successful: query='{params.query}' results={len(scholar_data)} "
                f"| request_id={request_id}"
            )

            return APIResponse(
                success=True,
                data=scholar_data,
                error=None,
                meta=ResponseMeta(
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc),
                    rate_limit_remaining=_rate_info.remaining,
                    rate_limit_reset=_rate_info.reset_seconds,
                ),
            )

        except CaptchaError as e:
            logger.error(f"Captcha error: {e} | request_id={request_id}")
            return APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="CAPTCHA_ERROR",
                    message=f"CAPTCHA detected: {str(e)}",
                    details={"original_error": str(e)},
                ),
                meta=ResponseMeta(
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc),
                    rate_limit_remaining=_rate_info.remaining,
                    rate_limit_reset=_rate_info.reset_seconds,
                ),
            )

        except ProxyError as e:
            logger.error(f"Proxy error: {e} | request_id={request_id}")
            return APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="PROXY_ERROR",
                    message=f"Proxy error: {str(e)}",
                    details={"original_error": str(e)},
                ),
                meta=ResponseMeta(
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc),
                    rate_limit_remaining=_rate_info.remaining,
                    rate_limit_reset=_rate_info.reset_seconds,
                ),
            )

        except PageTimeoutError as e:
            logger.error(f"Timeout error: {e} | request_id={request_id}")
            return APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="TIMEOUT_ERROR",
                    message=f"Page timeout: {str(e)}",
                    details={"query": params.query, "original_error": str(e)},
                ),
                meta=ResponseMeta(
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc),
                    rate_limit_remaining=_rate_info.remaining,
                    rate_limit_reset=_rate_info.reset_seconds,
                ),
            )

        except ParseError as e:
            logger.error(f"Parse error: {e} | request_id={request_id}")
            return APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="PARSE_ERROR",
                    message=f"Failed to parse results: {str(e)}",
                    details={"query": params.query, "original_error": str(e)},
                ),
                meta=ResponseMeta(
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc),
                    rate_limit_remaining=_rate_info.remaining,
                    rate_limit_reset=_rate_info.reset_seconds,
                ),
            )

        except Exception as e:
            logger.error(f"Unexpected error: {e} | request_id={request_id}")
            return APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="UNKNOWN_ERROR",
                    message=f"Unexpected error: {str(e)}",
                    details={"query": params.query, "original_error": str(e)},
                ),
                meta=ResponseMeta(
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc),
                    rate_limit_remaining=_rate_info.remaining,
                    rate_limit_reset=_rate_info.reset_seconds,
                ),
            )
