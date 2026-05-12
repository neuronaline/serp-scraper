"""News endpoint router."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.deps import RateLimitInfo, rate_limited_request, news_rate_limit
from api.middleware.logging_middleware import get_logger
from api.models.requests import NewsRequest
from api.models.responses import APIResponse, ErrorDetail, ResponseMeta
from serp import GoogleNewsClient
from serp.utils import PageTimeoutError, ParseError

router = APIRouter(prefix="/api/v1/news", tags=["News"])
logger = get_logger("api.routers.news")


@router.post("", response_model=APIResponse[list[dict]])
async def news_endpoint(
    request: Request,
    params: NewsRequest,
    _rate_info: Annotated[RateLimitInfo, Depends(news_rate_limit)],
) -> APIResponse[list[dict]]:
    """Fetch Google News results for a query.

    Args:
        request: FastAPI request object
        params: News search parameters
        _rate_info: Rate limit info (from dependency, after API key verified)

    Returns:
        APIResponse containing news results
    """
    request_id = str(uuid.uuid4())[:8]

    # Apply request pool limiting
    async with rate_limited_request():
        logger.info(
            f"News request: query='{params.query}' language='{params.language}' "
            f"max_results={params.max_results} | request_id={request_id}"
        )

        # Determine country from language if not specified
        country = params.country or ("TR" if params.language == "tr" else "US")

        try:
            async with GoogleNewsClient(
                language=params.language,
                country=country,
            ) as client:
                news_results = await client.get_news(
                    params.query,
                    max_results=params.max_results,
                )

            # Convert results to dict format
            news_data = [
                {
                    "title": n.title,
                    "url": n.url,
                    "description": n.description,
                    "published": n.published,
                    "source": n.source,
                }
                for n in news_results
            ]

            logger.info(
                f"News successful: query='{params.query}' results={len(news_data)} "
                f"| request_id={request_id}"
            )

            return APIResponse(
                success=True,
                data=news_data,
                error=None,
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
