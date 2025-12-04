"""Health Check Routes.

Health check endpoint for Docker healthcheck and monitoring.

Author: Odiseo Team
Created: 2025-11-10
Version: 1.0.0
"""

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for Docker healthcheck.

    Returns:
        dict: Service status information.
    """
    return {
        "status": "ok",
        "service": "demo_agent",
        "version": __version__,
    }
