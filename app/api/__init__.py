"""API routes package for Demo Agent."""

from app.api.demo import router as demo_router
from app.api.health import router as health_router

__all__ = ["demo_router", "health_router"]
