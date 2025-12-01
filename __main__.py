"""Demo Agent module entry point.

Allows running demo_agent as a module: python -m demo-service

Security:
    Configures Uvicorn with proxy header support for secure IP extraction.
    Only enable proxy_headers if running behind a trusted proxy/load balancer.

Author: Odiseo Team
Created: 2025-10-31
Version: 2.0.0
"""

import uvicorn

from app.config.settings import settings
from app.main import app
from app.utils.logging import get_logger

logger = get_logger(__name__)

if __name__ == "__main__":
    # Parse forwarded_allow_ips from config
    forwarded_allow_ips = None
    if settings.enable_proxy_headers and settings.trusted_proxies:
        # Use specific trusted proxy IPs for security
        forwarded_allow_ips = settings.trusted_proxies
        logger.info(f"Proxy headers enabled with trusted proxies: {forwarded_allow_ips}")
    elif settings.enable_proxy_headers:
        # WARNING: Using '*' trusts ALL proxies - only for development!
        forwarded_allow_ips = "*"
        logger.warning(
            "Proxy headers enabled with forwarded_allow_ips='*'. "
            "This is INSECURE for production! Set TRUSTED_PROXIES in .env"
        )
    else:
        logger.info("Proxy headers disabled - using direct connection IPs only")

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.is_debug,
        log_level=settings.log_level.lower(),
        # Security: Enable proxy header support
        proxy_headers=settings.enable_proxy_headers,
        forwarded_allow_ips=forwarded_allow_ips,
    )
