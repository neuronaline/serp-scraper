"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.middleware.logging_middleware import get_logger, setup_logging
from api.middleware.rate_limit import reset_rate_limiter
from api.routers import fetch, health, news, search

logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    Initializes resources on startup and cleans up on shutdown.
    """
    # Startup
    settings = get_settings()
    setup_logging(
        log_dir=settings.log_dir,
        log_level=settings.log_level,
    )
    logger.info(
        f"Starting SERP API server on {settings.host}:{settings.port} "
        f"(max_concurrent={settings.max_concurrent_requests})"
    )

    yield

    # Shutdown
    logger.info("Shutting down SERP API server")
    reset_rate_limiter()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    settings = get_settings()

    app = FastAPI(
        title="SERP Scraper API",
        description="SERP scraping API with Google/Bing search, URL fetch, and news",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS middleware - only add if origins are configured
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Include routers
    app.include_router(health.router)
    app.include_router(search.router)
    app.include_router(fetch.router)
    app.include_router(news.router)

    return app


app = create_app()


def main() -> None:
    """Run the API server."""
    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()
