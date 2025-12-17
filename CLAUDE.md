# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Web API Gateway for Gemini 2.5 with Clerk Auth & Token-bucket rate limiting.
FastAPI service providing secure, rate-limited AI chat interface powered by Google Gemini 2.5.

**Product**: Odiseo (https://www.nexusintelligent.ai/)

## Common Commands

```bash
# Development server (with hot reload)
make run
# or: PYTHONPATH=.:$PYTHONPATH uvicorn app.main:app --host 0.0.0.0 --port 9090 --reload

# Run all tests
make test
# or: pytest tests/ -v

# Run single test file
pytest tests/test_token_bucket.py -v

# Run single test function
pytest tests/test_token_bucket.py::test_function_name -v

# Code quality (all checks)
make quality
# or: ruff check . && black --check . && isort --check . && mypy app

# Format code
make format
# or: black . && isort . && ruff check . --fix

# Type checking
make type-check
# or: mypy app

# Docker
make docker-up      # Build and start containers
make docker-down    # Stop containers
make docker-logs    # Follow container logs
make docker-restart # Restart after code changes
make fix-perms      # Fix file permissions for Docker volumes
```

## Architecture

```
app/
├── main.py               # FastAPI entry point, lifespan events
├── config/settings.py    # Pydantic v2 settings (all env vars)
├── api/demo.py           # /v1/demo endpoints (POST, GET status/history)
├── services/
│   ├── demo_agent.py     # Core business logic orchestration
│   ├── gemini_client.py  # Vertex AI client (ThreadPoolExecutor for non-blocking)
│   ├── clerk_service.py  # Clerk JWT validation via public JWKS
│   └── prompt_manager.py # Jinja2 prompt templates
├── security/
│   ├── clerk_middleware.py  # Auth middleware (validates JWT, JIT user provisioning)
│   ├── fingerprint.py       # Client fingerprinting for abuse detection
│   └── ip_limiter.py        # IP-based rate limiting
├── rate_limiter/
│   └── token_bucket.py   # Token bucket algorithm (5000 tokens/day per user)
└── utils/
    ├── logging.py        # structlog setup with sensitive data sanitization
    └── sanitizers.py     # XSS/injection prevention helpers
```

### Request Flow
```
Request → ClerkAuthMiddleware (JWT validation via JWKS)
       → IP Rate Limiter → Token Bucket check
       → DemoAgent → GeminiClient (non-blocking via executor)
       → Response with token usage
```

### Key Design Patterns

1. **Clerk Auth**: Uses public JWKS for JWT validation - no secret keys needed in backend
2. **Concurrency**: `GeminiClient` uses `asyncio.run_in_executor()` with ThreadPoolExecutor
3. **Rate Limiting**: Token bucket stored in PostgreSQL, resets daily per user timezone
4. **Fail-closed**: Rate limiters block on database errors (security over availability)

## Code Standards

### Pydantic v2 (Required)
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class MyModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip()

    model_config = ConfigDict(json_schema_extra={"example": {"name": "example"}})
```

### Security Patterns
```python
from app.utils.sanitizers import sanitize_user_input, sanitize_html, sanitize_error_message

# All user input
clean_input = sanitize_user_input(raw_input)

# HTML output (XSS prevention)
safe_html = sanitize_html(content)

# Error messages (info disclosure prevention)
safe_error = sanitize_error_message(error_details)
```

### Logging
```python
from app.utils.logging import get_logger

logger = get_logger(__name__)
logger.info("Event description", user_id=123, action="login")
```

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/v1/demo` | POST | Clerk JWT | Process AI query |
| `/v1/demo/status` | GET | Clerk JWT | Get quota status |
| `/v1/demo/history` | GET | Clerk JWT | Get chat history |
| `/health` | GET | None | Health check |

## Environment Variables

Required variables:
- `DATABASE_URL` - PostgreSQL connection string
- `GCP_PROJECT_ID` - Google Cloud project ID
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to service account JSON (local dev only)
- `CLERK_FRONTEND_API` - Clerk instance domain (e.g., `mighty-leopard-52.clerk.accounts.dev`)
- `SCHEMA_NAME` - PostgreSQL schema name (`test` for Cloud SQL, `public` for local Docker)

Key optional variables:
- `ENABLE_CLERK_AUTH=true` - Toggle auth (false for local dev)
- `DEMO_MAX_TOKENS=5000` - Daily token limit per user
- `UVICORN_WORKERS=4` - Number of worker processes
- `MAX_CONCURRENT_REQUESTS=10` - Concurrent Gemini calls per worker

See `.env.example` for full documentation of all variables.

## Deployment

### Production (Google Cloud)

| Component | Value |
|-----------|-------|
| **API Gateway** | `https://demo-agent-gateway-vq1gs9i.uc.gateway.dev` |
| **Cloud Run** | `demo-agent` in `us-central1` |
| **Cloud SQL** | `demo-db` (PostgreSQL 15) |
| **Schema** | `test` |
| **Clerk Frontend API** | `mighty-leopard-52.clerk.accounts.dev` |

### Database Schema

The schema is defined in `deploy/schema-cloud-sql.sql` with dynamic schema name support:

```bash
# Deploy with default schema (test)
psql -U demo_user -d demodb -f deploy/schema-cloud-sql.sql

# Deploy with custom schema
psql -v schema_name='production' -U demo_user -d demodb -f deploy/schema-cloud-sql.sql
```

**IMPORTANT**: Functions use `current_schema()` with dynamic SQL to resolve table names at runtime. This ensures they work correctly regardless of the schema name.

### Clerk JWT Configuration

The frontend must use a custom JWT template (`odiseo-api`) that includes the `email` claim:

```typescript
// Frontend: useChat.ts, useTokenQuota.ts
const token = await getToken({ template: 'odiseo-api' });
```

This is required for JIT (Just-In-Time) user provisioning in the database.

## Concurrency Configuration

```
Total Concurrent Gemini Calls = UVICORN_WORKERS × MAX_CONCURRENT_REQUESTS
Total DB Connections = UVICORN_WORKERS × DB_POOL_MAX_SIZE

Example: 4 workers × 10 = 40 concurrent API calls, 80 max DB connections
```

Ensure PostgreSQL `max_connections` >= (UVICORN_WORKERS × DB_POOL_MAX_SIZE) + 20