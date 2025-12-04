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
- Rate limiters fail-closed on database errors (CWE-400)
- JWT audience validation without insecure fallbacks (CWE-347)
- Jinja2 autoescape enabled for XSS prevention (CWE-79)
- ThreadPoolExecutor properly shutdown on app exit

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

## Concurrency Architecture

The service supports high concurrency through a combination of:
- **Uvicorn Workers**: Multiple processes for parallel request handling
- **ThreadPoolExecutor**: Non-blocking Gemini API calls within each worker
- **AsyncPG Connection Pool**: Async database operations

### Configuration

```bash
# Number of worker processes (default: 4)
UVICORN_WORKERS=4

# Max concurrent Gemini API calls per worker (default: 10)
MAX_CONCURRENT_REQUESTS=10

# Database pool settings per worker
DB_POOL_MIN_SIZE=5      # Minimum connections (default: 5)
DB_POOL_MAX_SIZE=20     # Maximum connections (default: 20)
DB_COMMAND_TIMEOUT=60   # Query timeout in seconds (default: 60)
DB_POOL_MAX_INACTIVE_LIFETIME=300  # Idle connection timeout (default: 300s)
```

### Capacity Calculation

```
Total Concurrent Gemini Calls = UVICORN_WORKERS × MAX_CONCURRENT_REQUESTS

Example: 4 workers × 10 = 40 concurrent Gemini API calls
```

### Architecture Diagram

```
                    ┌─────────────────────────────────────┐
                    │         Load Balancer / Nginx       │
                    └──────────────┬──────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
    ┌────┴────┐              ┌────┴────┐              ┌────┴────┐
    │Worker 1 │              │Worker 2 │              │Worker N │
    │         │              │         │              │         │
    │ ThreadPool(10)         │ ThreadPool(10)         │ ThreadPool(10)
    │ DB Pool (5-20)         │ DB Pool (5-20)         │ DB Pool (5-20)
    └─────────┘              └─────────┘              └─────────┘
```

### Implementation Details

- `gemini_client.py`: Uses `asyncio.run_in_executor()` for non-blocking SDK calls
- `connection.py`: AsyncPG pool with 5-20 connections per worker
- `docker-compose.yml`: Configures workers via `UVICORN_WORKERS` env var

### Recommended Settings

| Deployment | Workers | Concurrent/Worker | Total Capacity |
|------------|---------|-------------------|----------------|
| Development | 1 | 5 | 5 |
| Small | 2 | 10 | 20 |
| Medium | 4 | 10 | 40 |
| Large | 8 | 15 | 120 |

## Security Configuration

```bash
# Abuse detection thresholds
ABUSE_SCORE_BLOCK_THRESHOLD=0.9  # Block requests above this score (0.5-1.0)
DEMO_TOKENS_PER_REQUEST=100      # Estimated tokens for quota pre-check

# IP suspicion detection
IP_SUSPICIOUS_REQ_PER_MIN=5      # Requests/min to flag IP as suspicious
IP_SUSPICIOUS_UNIQUE_USERS=10    # Unique users to flag IP as suspicious
```

## Error Response Model

All API errors use consistent `ErrorResponse` format:

```python
from app.models.responses import ErrorResponse

# Standard error fields
{
    "success": False,
    "error": "error_code",      # Snake_case identifier
    "message": "Human message",  # User-friendly message
    "hint": "Optional hint",     # Resolution suggestion
    "retry_after_seconds": 300   # Optional retry time
}
```

- La pagina de Odiseo es https://www.nexusintelligent.ai/
- Odiseo es el nombre del producto