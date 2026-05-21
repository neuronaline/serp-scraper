"""Fetch endpoint router."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from api.config import get_settings
from api.deps import RateLimitInfo, rate_limited_request, fetch_rate_limit
from api.middleware.logging_middleware import get_logger
from api.models.requests import FetchRequest
from api.models.responses import APIResponse, ErrorDetail, ResponseMeta
from serp import SerpClient, SerpConfig, compress_content
from serp.utils import CaptchaError, PageTimeoutError, ParseError, ProxyError

router = APIRouter(prefix="/api/v1/fetch", tags=["Fetch"])
logger = get_logger("api.routers.fetch")


@router.post("", response_model=APIResponse[dict])
async def fetch_endpoint(
    request: Request,
    params: FetchRequest,
    _rate_info: Annotated[RateLimitInfo, Depends(fetch_rate_limit)],
) -> APIResponse[dict]:
    """Fetch a URL and return content as Markdown.

    Args:
        request: FastAPI request object
        params: Fetch parameters
        _rate_info: Rate limit info (from dependency, after API key verified)

    Returns:
        APIResponse containing fetched content
    """
    request_id = str(uuid.uuid4())[:8]

    # Apply request pool limiting
    async with rate_limited_request():
        logger.info(
            f"Fetch request: url='{params.url}' prefer_browser={params.prefer_browser} "
            f"| request_id={request_id}"
        )

        try:
            settings = get_settings()
            config = SerpConfig(timeout=settings.request_timeout)
            async with SerpClient(config=config) as client:
                content = await client.fetch(
                    url=params.url,
                    prefer_browser=params.prefer_browser,
                )

            logger.info(
                f"Fetch successful: url='{params.url}' chars={len(content)} "
                f"| request_id={request_id}"
            )

            # Apply compression if requested (client-side, includes caching)
            was_truncated = False
            original_length: int | None = None
            if params.compress:
                # Measure original length before compression
                raw_len = len(content)
                content, meta = compress_content(content)
                was_truncated = meta.was_truncated
                original_length = raw_len if was_truncated else None
                if was_truncated:
                    logger.info(
                        f"Content compressed: url='{params.url}' "
                        f"original={original_length} compressed={meta.compressed_length} "
                        f"| request_id={request_id}"
                    )

            return APIResponse(
                success=True,
                data={
                    "url": params.url,
                    "content": content,
                    "char_count": len(content),
                    "was_truncated": was_truncated,
                    "original_length": original_length if was_truncated else None,
                },
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
                    details={"url": params.url, "original_error": str(e)},
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
                    details={"url": params.url, "original_error": str(e)},
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
                    details={"url": params.url, "original_error": str(e)},
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
                    details={"url": params.url, "original_error": str(e)},
                ),
                meta=ResponseMeta(
                    request_id=request_id,
                    timestamp=datetime.now(timezone.utc),
                    rate_limit_remaining=_rate_info.remaining,
                    rate_limit_reset=_rate_info.reset_seconds,
                ),
            )
