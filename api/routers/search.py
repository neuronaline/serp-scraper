"""Search endpoint router."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.config import get_settings
from api.deps import RateLimitInfo, rate_limited_request, search_rate_limit
from api.middleware.logging_middleware import get_logger
from api.models.requests import SearchRequest
from api.models.responses import APIResponse, ErrorDetail, ResponseMeta
from serp import SerpClient, SerpConfig
from serp.utils import CaptchaError, PageTimeoutError, ParseError, ProxyError

router = APIRouter(prefix="/api/v1/search", tags=["Search"])
logger = get_logger("api.routers.search")


@router.post("", response_model=APIResponse[list[dict]])
async def search_endpoint(
    request: Request,
    params: SearchRequest,
    _rate_info: Annotated[RateLimitInfo, Depends(search_rate_limit)],
) -> APIResponse[list[dict]]:
    """Search for query and return results.

    Performs a SERP search using Google or Bing.
    Results are cached by default.

    Args:
        request: FastAPI request object
        params: Search parameters
        _rate_info: Rate limit info (from dependency, after API key verified)

    Returns:
        APIResponse containing search results
    """
    request_id = str(uuid.uuid4())[:8]

    # Apply request pool limiting
    async with rate_limited_request():
        logger.info(
            f"Search request: query='{params.query}' source='{params.source or 'auto'}' "
            f"| request_id={request_id}"
        )

        try:
            settings = get_settings()
            config = SerpConfig(timeout=settings.request_timeout)
            async with SerpClient(config=config) as client:
                results = await client.search(
                    query=params.query,
                    page_num=params.page,
                    source=params.source,
                    method=params.method,
                )

            # Convert results to dict format
            results_data = [
                {
                    "rank": r.rank,
                    "title": r.title,
                    "url": r.url,
                    "description": r.description,
                    "source": r.source,
                }
                for r in results
            ]

            logger.info(
                f"Search successful: query='{params.query}' results={len(results_data)} "
                f"| request_id={request_id}"
            )

            return APIResponse(
                success=True,
                data=results_data,
                error=None,
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

        except PageTimeoutError as e:
            logger.error(f"Timeout error: {e} | request_id={request_id}")
            return APIResponse(
                success=False,
                data=None,
                error=ErrorDetail(
                    code="TIMEOUT_ERROR",
                    message=f"Page timeout: {str(e)}",
                    details={"original_error": str(e)},
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
                    details={"original_error": str(e)},
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
                    details={"original_error": str(e)},
                ),
                meta=ResponseMeta(
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc),
                    rate_limit_remaining=_rate_info.remaining,
                    rate_limit_reset=_rate_info.reset_seconds,
                ),
            )
