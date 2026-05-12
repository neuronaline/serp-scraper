"""Health check endpoint router."""

from datetime import datetime, timezone

from fastapi import APIRouter

from api.models.responses import APIResponse, ResponseMeta

router = APIRouter(prefix="", tags=["Health"])


@router.get("/health", response_model=APIResponse[dict])
async def health_check() -> APIResponse[dict]:
    """Basic health check endpoint.

    Returns:
        APIResponse with health status
    """
    return APIResponse(
        success=True,
        data={"status": "healthy"},
        error=None,
        meta=ResponseMeta(
            request_id="health",
            timestamp=datetime.now(timezone.utc),
        ),
    )
