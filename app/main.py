"""Demo Agent Main Entry Point.

FastAPI application for demo agent with token-bucket rate limiting.
REQ-1 Compliant: Single endpoint, Clerk auth, Gemini 2.5, token tracking.

Author: Odiseo Team
Version: 2.0.0 (REQ-1 Compliant)
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import demo_router, health_router
from app.config.settings import settings
from app.db.connection import close_db, init_db
from app.middleware.request_size_limit import RequestSizeLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.security.clerk_middleware import ClerkAuthMiddleware
from app.services.demo_agent import DemoAgent
from app.services.user_service import get_user_service
from app.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Handle startup and shutdown events."""
    # Setup logging first
    setup_logging()

    logger.info(f"Demo Agent starting on {settings.host}:{settings.port}")
    logger.info(
        f"Config: {settings.demo_max_tokens} tokens/day, "
        f"{settings.demo_cooldown_hours}h cooldown"
    )

    try:
        await init_db()
        logger.info("Database connection pool initialized")

        app.state.demo_agent = DemoAgent()
        app.state.user_service = get_user_service()
        logger.info("Demo Agent initialized")

    except Exception as e:
        logger.exception(f"Failed to initialize: {e}")
        raise RuntimeError(f"Startup failed: {e}") from e

    yield

    logger.info("Demo Agent shutting down...")
    await close_db()
    logger.info("Database connection closed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Demo Agent API",
        description="REQ-1: Single endpoint with Clerk auth, Gemini 2.5, token tracking",
        version="2.0.0",
        lifespan=lifespan,
    )

    # Clerk Authentication Middleware
    app.add_middleware(ClerkAuthMiddleware)

    # Request Size Limit
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_size=50 * 1024,
        endpoint_limits={"/v1/demo": 10 * 1024},
    )

    # CORS Configuration
    cors_origins = [
        o.strip()
        for o in settings.cors_allow_origins.split(",")
        if o.strip() and o.strip().startswith(("http://", "https://"))
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # Security Headers
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True, enable_csp=True)

    # Correlation ID middleware
    @app.middleware("http")
    async def add_correlation_id(request: Request, call_next: Callable[[Request], Any]) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
        response: Response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    # Root endpoint
    @app.get("/", tags=["Info"])
    async def root() -> dict[str, Any]:
        return {
            "service": "Demo Agent API",
            "version": "2.0.0",
            "endpoints": {
                "health": "/health",
                "demo": "/v1/demo (POST)",
                "status": "/v1/demo/status (GET)",
            },
        }

    # Register routers
    app.include_router(health_router)
    app.include_router(demo_router)

    logger.info("Routers registered: /health, /v1/demo")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_debug,
        log_level=settings.log_level.lower(),
    )
