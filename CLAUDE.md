# Demo Agent Service

## Project Overview

Web API Gateway for Gemini 2.5 with Clerk Auth & Token Usage.
REQ-1 compliant FastAPI service with token-bucket rate limiting.

## Architecture

```
demo-service/
├── app/
│   ├── main.py               # FastAPI application entry point
│   ├── config/
│   │   └── settings.py       # Pydantic v2 settings (env vars)
│   ├── db/
│   │   └── connection.py     # AsyncPG connection pool
│   ├── models/
│   │   ├── requests.py       # Request DTOs (Pydantic v2)
│   │   └── responses.py      # Response DTOs (Pydantic v2)
│   ├── api/
│   │   └── demo.py           # Demo endpoints (/v1/demo)
│   ├── services/
│   │   ├── demo_agent.py     # Core business logic
│   │   ├── gemini_client.py  # Vertex AI Gemini 2.5 client
│   │   ├── clerk_service.py  # Clerk JWT validation
│   │   ├── client_ip_service.py
│   │   └── prompt_manager.py # Jinja2 prompt templates
│   ├── security/
│   │   ├── clerk_middleware.py
│   │   ├── fingerprint.py
│   │   └── ip_limiter.py
│   ├── middleware/
│   │   ├── request_size_limit.py
│   │   └── security_headers.py
│   ├── rate_limiter/
│   │   └── token_bucket.py   # Token bucket algorithm
│   └── utils/
│       ├── logging.py        # Structured logging (structlog)
│       ├── validators.py     # Input validation (UUID)
│       └── sanitizers.py     # XSS/injection prevention
├── prompts/                  # Jinja2 prompt templates
├── credentials/              # GCP service account (gitignored)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env
```

## Logging (structlog)

Uses **structlog** for structured JSON logging with:
- Console output with colors (development)
- JSON file logging with rotation (production)
- Sensitive data sanitization (CWE-532 mitigation)
- Startup banner with config summary

```python
from app.utils.logging import get_logger

# Get named logger
logger = get_logger(__name__)
logger.info("Starting process", user_id=123, action="login")
logger.debug("Debug message", data={"key": "value"})
```

### Configuration
```bash
LOG_LEVEL=INFO           # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_TO_FILE=true         # Enable file logging
LOG_DIR=logs             # Log directory
LOG_CONSOLE_ENABLED=true # Enable console output
LOG_JSON_FORMAT=true     # JSON format for files
LOG_FILE_MAX_MB=10       # Max file size before rotation
LOG_FILE_BACKUP_COUNT=5  # Rotated files to keep
```

## Code Standards

### Python Version
- Python 3.10+ with full type hints

### Dependencies
- FastAPI 0.115+
- Pydantic 2.11+ (use `ConfigDict`, `field_validator`)
- pydantic-settings 2.11+
- google-genai 1.0+ (Google Gen AI SDK for Gemini)
- asyncpg 0.30+ (async PostgreSQL)
- PyJWT 2.9+ (Clerk JWT validation via public JWKS)
- structlog 24.4+

### Pydantic v2 Patterns

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class MyModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip()

    model_config = ConfigDict(
        json_schema_extra={"example": {"name": "example"}}
    )
```

### Linting & Formatting
```bash
ruff check .           # Linting
ruff check . --fix     # Auto-fix
black .                # Format
isort .                # Sort imports
mypy .                 # Type checking
```

### Security Practices
- All user input through `sanitize_user_input()`
- HTML output through `sanitize_html()` (XSS prevention)
- Error messages through `sanitize_error_message()` (info disclosure)
- Session IDs validated as UUID v4
- Client IP extracted securely from proxy headers
- Log sanitization (JWT, API keys, emails, IPs redacted)

## Clerk Authentication

JWT validation uses **public JWKS** - no secret keys required in backend.

### Configuration
```bash
# Required: Clerk instance domain for JWKS endpoint
CLERK_FRONTEND_API=your-instance.clerk.accounts.dev

# Optional: For audience validation (more secure)
CLERK_PUBLISHABLE_KEY=pk_test_...

# Enable/disable auth (false for local dev without Clerk)
ENABLE_CLERK_AUTH=true
```

### Flow
```
Frontend (Clerk SDK) → JWT → Backend → JWKS validation → PostgreSQL user sync
```

- Frontend handles auth with Clerk SDK
- Backend validates JWT using Clerk's public JWKS endpoint
- JIT (Just-In-Time) provisioning creates users in local DB on first access
- No `CLERK_SECRET_KEY` needed for token validation

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/demo` | POST | Clerk JWT | Process demo query |
| `/v1/demo/status` | GET | Clerk JWT | Get quota status |
| `/v1/demo/history` | GET | Clerk JWT | Get chat history |
| `/health` | GET | None | Health check |

## Development Commands

```bash
# Run service
uvicorn app.main:app --reload --port 9090

# Run tests
pytest tests/ -v

# Type check
mypy . --ignore-missing-imports

# Full lint
ruff check . && black --check . && isort --check .
```

## Docker

```bash
# Build and run with docker-compose
docker-compose up -d --build

# Or standalone
docker build -t demo-agent .
docker run -p 9090:9090 --env-file .env demo-agent
```
- La pagina de Odiseo es https://www.nexusintelligent.ai/
- Odiseo es el nombre del producto