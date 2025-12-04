<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Gemini_2.5-Flash-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/Clerk-Auth-6C47FF?style=for-the-badge&logo=clerk&logoColor=white" alt="Clerk">
  <img src="https://img.shields.io/badge/PostgreSQL-13+-336791?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL">
</p>

<h1 align="center">🚀 Odiseo Demo Agent</h1>

<p align="center">
  <strong>Enterprise-grade AI Gateway powered by Google Gemini 2.5</strong>
  <br>
  Secure, rate-limited, and production-ready API for conversational AI
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-api-reference">API</a> •
  <a href="#-configuration">Config</a>
</p>

---

## 📋 Overview

The **Odiseo Demo Agent** is a FastAPI microservice that provides a secure, token-limited AI chat interface powered by Google Gemini 2.5. It's designed for enterprise deployments with built-in authentication, rate limiting, and abuse detection.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryTextColor': '#000000', 'lineColor': '#333333', 'textColor': '#000000' }}}%%
graph LR
    subgraph Client
        A[🌐 Frontend<br/>Clerk SDK]
    end

    subgraph Odiseo Demo Service
        B[🔐 Auth Middleware<br/>JWT Validation]
        C[⚡ Rate Limiter<br/>Token Bucket]
        D[🤖 Demo Agent<br/>Business Logic]
    end

    subgraph External Services
        E[🔑 Clerk JWKS<br/>Public Keys]
        F[🧠 Gemini 2.5<br/>AI Model]
        G[🗄️ PostgreSQL<br/>User Data]
    end

    A -->|JWT Token| B
    B -->|Validate| E
    B -->|Authenticated| C
    C -->|Allowed| D
    D -->|Query| F
    D -->|Store| G

    style A fill:#E3F2FD,stroke:#1565C0,stroke-width:3px
    style B fill:#FFF3E0,stroke:#E65100,stroke-width:3px
    style C fill:#FCE4EC,stroke:#C2185B,stroke-width:3px
    style D fill:#E8F5E9,stroke:#2E7D32,stroke-width:3px
    style E fill:#F3E5F5,stroke:#7B1FA2,stroke-width:3px
    style F fill:#E1F5FE,stroke:#0277BD,stroke-width:3px
    style G fill:#FFFDE7,stroke:#F57F17,stroke-width:3px
```

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔐 **Clerk Authentication** | JWT validation via public JWKS (no secrets in backend) |
| 🪣 **Token Bucket Rate Limiting** | 5,000 tokens/day per user with automatic reset |
| 🧠 **Gemini 2.5 Integration** | Enterprise AI with zero-hallucination architecture |
| 🛡️ **Security Hardened** | OWASP Top 10 compliant, input sanitization, XSS prevention |
| 📊 **Audit Logging** | Complete trail of all requests and responses |
| 🌍 **Multi-language** | Spanish, English, Arabic support |
| ⚡ **High Concurrency** | Multi-worker architecture with non-blocking API calls |

## 🏗️ Architecture

### System Overview

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryTextColor': '#000000', 'lineColor': '#333333', 'textColor': '#000000' }}}%%
flowchart TB
    subgraph Internet
        CLIENT[👤 User]
    end

    subgraph Docker Network
        subgraph demo-service [Demo Agent Service :9090]
            MAIN[main.py<br/>FastAPI App]
            AUTH[clerk_middleware.py<br/>JWT Validation]
            RATE[token_bucket.py<br/>Rate Limiter]
            AGENT[demo_agent.py<br/>Core Logic]
            GEMINI[gemini_client.py<br/>AI Client]
        end

        subgraph data [Data Layer]
            PG[(PostgreSQL<br/>Users & Audit)]
        end

        subgraph external [External APIs]
            CLERK[Clerk JWKS<br/>clerk.accounts.dev]
            VERTEX[Vertex AI<br/>Gemini 2.5 Flash]
        end
    end

    CLIENT -->|HTTPS + JWT| MAIN
    MAIN --> AUTH
    AUTH -.->|Validate| CLERK
    AUTH --> RATE
    RATE --> AGENT
    AGENT --> GEMINI
    GEMINI -.->|API Call| VERTEX
    AGENT --> PG

    style CLIENT fill:#E3F2FD,stroke:#1565C0,stroke-width:3px
    style MAIN fill:#E8F5E9,stroke:#2E7D32,stroke-width:3px
    style AUTH fill:#FFF3E0,stroke:#E65100,stroke-width:3px
    style RATE fill:#FFEBEE,stroke:#C62828,stroke-width:3px
    style AGENT fill:#F3E5F5,stroke:#7B1FA2,stroke-width:3px
    style GEMINI fill:#E1F5FE,stroke:#0277BD,stroke-width:3px
    style PG fill:#FFFDE7,stroke:#F57F17,stroke-width:3px
    style CLERK fill:#F3E5F5,stroke:#7B1FA2,stroke-width:3px
    style VERTEX fill:#E0F2F1,stroke:#00695C,stroke-width:3px
```

### Authentication Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryTextColor': '#000000', 'actorTextColor': '#000000', 'signalTextColor': '#000000', 'textColor': '#000000' }}}%%
sequenceDiagram
    autonumber
    participant U as 👤 User
    participant F as 🌐 Frontend
    participant C as 🔑 Clerk
    participant B as ⚡ Backend
    participant J as 📜 JWKS
    participant D as 🗄️ Database

    U->>F: Login Request
    F->>C: Authenticate
    C-->>F: JWT Token (60s TTL)
    F->>B: API Request + JWT

    rect rgba(255, 183, 77, 0.3)
        Note over B,J: 🔐 Token Validation
        B->>J: Fetch Public Keys
        J-->>B: RS256 Keys (cached)
        B->>B: Verify Signature
    end

    rect rgba(129, 199, 132, 0.3)
        Note over B,D: 👤 JIT Provisioning
        B->>D: Check User Exists
        alt User Not Found
            B->>D: Create User (JIT)
        end
        D-->>B: User Data
    end

    B-->>F: API Response
    F-->>U: Display Result
```

### Token Bucket Algorithm

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryTextColor': '#000000', 'textColor': '#000000', 'labelTextColor': '#000000' }}}%%
stateDiagram-v2
    [*] --> Available: User Request

    Available --> CheckQuota: Validate JWT ✓

    CheckQuota --> Allowed: tokens_remaining > 0
    CheckQuota --> Blocked: tokens_remaining = 0

    Allowed --> ProcessRequest: Deduct Tokens
    ProcessRequest --> Response: Return AI Response
    Response --> [*]

    Blocked --> Error429: Return Rate Limit Error
    Error429 --> [*]

    state CheckQuota {
        [*] --> QueryDB
        QueryDB --> CalculateRemaining
        CalculateRemaining --> [*]
    }

    note right of Blocked
        Blocked for 24h
        Auto-reset at midnight
    end note

    classDef available fill:#E3F2FD,stroke:#1565C0,stroke-width:3px
    classDef allowed fill:#E8F5E9,stroke:#2E7D32,stroke-width:3px
    classDef blocked fill:#FFEBEE,stroke:#C62828,stroke-width:3px
    classDef process fill:#F3E5F5,stroke:#7B1FA2,stroke-width:3px
    classDef response fill:#E0F2F1,stroke:#00695C,stroke-width:3px
    classDef error fill:#FBE9E7,stroke:#D84315,stroke-width:3px

    class Available available
    class Allowed allowed
    class Blocked blocked
    class ProcessRequest process
    class Response response
    class Error429 error
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 13+
- Google Cloud account with Vertex AI enabled
- Clerk account

### Installation

```bash
# Clone repository
git clone https://github.com/odiseo/demo-service.git
cd demo-service

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Docker Deployment

```bash
# Build and start
docker-compose up -d --build

# Check status
docker ps

# View logs
docker logs -f demo-agent
```

### Verify Installation

```bash
# Health check (no auth required)
curl http://localhost:9090/health

# Expected response:
# {"status":"ok","service":"demo_agent","version":"2.0.0"}
```

## 🔐 Authentication

This service uses **Clerk** for authentication. JWTs are validated using Clerk's **public JWKS endpoint** - no secret keys required in the backend.

### Configuration

```bash
# Required: Your Clerk instance domain
CLERK_FRONTEND_API=your-instance.clerk.accounts.dev

# Optional: For audience validation
CLERK_PUBLISHABLE_KEY=pk_test_...

# Toggle authentication (false for local dev)
ENABLE_CLERK_AUTH=true
```

### Getting a JWT Token

<details>
<summary><b>Option 1: Clerk Dashboard</b> (Recommended for testing)</summary>

1. Go to [dashboard.clerk.com](https://dashboard.clerk.com)
2. Select your application
3. Navigate to **Users** → Select user → **⋯** → **Get session token**
</details>

<details>
<summary><b>Option 2: Clerk Backend API</b></summary>

```bash
curl -X POST "https://api.clerk.com/v1/sessions/{session_id}/tokens" \
  -H "Authorization: Bearer sk_test_YOUR_SECRET_KEY" \
  -H "Content-Type: application/json"
```
</details>

<details>
<summary><b>Option 3: Frontend Console</b></summary>

```javascript
// In browser console after login
const token = await window.Clerk.session.getToken();
console.log(token);
```
</details>

## 📡 API Reference

### Endpoints Overview

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/health` | ❌ | Health check |
| `GET` | `/v1/demo/status` | ✅ | User quota status |
| `GET` | `/v1/demo/history` | ✅ | Chat history |
| `POST` | `/v1/demo` | ✅ | Send message to AI |

---

### `GET /health`

Health check endpoint for monitoring and load balancers.

```bash
curl http://localhost:9090/health
```

<details>
<summary>Response (200)</summary>

```json
{
  "status": "ok",
  "service": "demo_agent",
  "version": "2.0.0"
}
```
</details>

---

### `GET /v1/demo/status`

Get current user's token quota and usage statistics.

```bash
curl -X GET "http://localhost:9090/v1/demo/status" \
  -H "Authorization: Bearer $JWT"
```

<details>
<summary>Response (200)</summary>

```json
{
  "tokens_used": 201,
  "tokens_remaining": 4799,
  "daily_limit": 5000,
  "percentage_used": 4,
  "requests_count": 2,
  "is_blocked": false,
  "blocked_until": null,
  "user_timezone": "America/Costa_Rica",
  "last_reset": "2025-11-30T18:39:59.738622+00:00",
  "next_reset": "2025-12-01T06:00:00+00:00",
  "warning": {
    "is_warning": false,
    "message": null,
    "percentage_used": 4
  }
}
```
</details>

---

### `GET /v1/demo/history`

Retrieve chat history for the authenticated user.

```bash
curl -X GET "http://localhost:9090/v1/demo/history?limit=10" \
  -H "Authorization: Bearer $JWT"
```

<details>
<summary>Response (200)</summary>

```json
{
  "success": true,
  "messages": [
    {
      "id": 1,
      "role": "user",
      "message_text": "Hola",
      "token_count": 0,
      "created_at": "2025-11-30T19:44:18.507122+00:00"
    },
    {
      "id": 2,
      "role": "model",
      "message_text": "¡Hola! Soy tu asistente...",
      "token_count": 23,
      "created_at": "2025-11-30T19:44:18.510000+00:00"
    }
  ],
  "total_messages": 2
}
```
</details>

---

### `POST /v1/demo`

Send a message to the AI assistant.

```bash
curl -X POST "http://localhost:9090/v1/demo" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "¿Qué es Odiseo IA?",
    "language": "es"
  }'
```

#### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `input` | string | ✅ | User message (max 2000 chars) |
| `language` | string | ❌ | `es`, `en`, or `ar` (default: `es`) |
| `session_id` | string | ❌ | UUID for session tracking |
| `metadata` | object | ❌ | Additional context |

<details>
<summary>Success Response (200)</summary>

```json
{
  "success": true,
  "response": "¡Hola! Odiseo IA es una plataforma de agentes de IA...",
  "tokens_used": 45,
  "tokens_remaining": 4955,
  "warning": {
    "is_warning": false,
    "message": null,
    "percentage_used": 1
  },
  "session_id": "9b022e74-89f3-4c5c-bb48-f1b6139b7638",
  "created_at": "2025-11-30T19:44:18.507122+00:00"
}
```
</details>

<details>
<summary>Error Responses</summary>

**401 Unauthorized**
```json
{
  "success": false,
  "error": "Unauthorized",
  "message": "Authentication failed: Token expired",
  "hint": "Include a valid Bearer token in the Authorization header"
}
```

**429 Rate Limited**
```json
{
  "success": false,
  "error": "demo_quota_exceeded",
  "message": "Demo bloqueada. Límite de 5,000 tokens alcanzado.",
  "retry_after_seconds": 64800,
  "blocked_until": "2025-12-01T06:00:00Z"
}
```
</details>

## ⚙️ Configuration

### Environment Variables

<details>
<summary><b>🔥 Google Cloud / Gemini</b></summary>

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT_ID` | ✅ | - | Google Cloud project ID |
| `GCP_LOCATION` | ❌ | `us-central1` | Vertex AI region |
| `GOOGLE_APPLICATION_CREDENTIALS` | ✅ | - | Path to service account JSON |
| `MODEL` | ❌ | `gemini-2.5-flash` | Gemini model ID |
| `TEMPERATURE` | ❌ | `0.2` | Model temperature (0-2) |
</details>

<details>
<summary><b>🔐 Clerk Authentication</b></summary>

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CLERK_FRONTEND_API` | ✅ | - | Clerk instance domain |
| `CLERK_PUBLISHABLE_KEY` | ❌ | - | For audience validation |
| `ENABLE_CLERK_AUTH` | ❌ | `true` | Toggle authentication |
</details>

<details>
<summary><b>📊 Rate Limiting</b></summary>

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEMO_MAX_TOKENS` | ❌ | `5000` | Daily token limit per user |
| `DEMO_COOLDOWN_HOURS` | ❌ | `24` | Block duration after quota exceeded |
| `DEMO_WARNING_THRESHOLD` | ❌ | `85` | Warning percentage threshold |
</details>

<details>
<summary><b>🛡️ Security</b></summary>

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENABLE_FINGERPRINT` | ❌ | `true` | Client fingerprinting |
| `FINGERPRINT_SCORE_THRESHOLD` | ❌ | `0.7` | Abuse detection threshold |
| `IP_RATE_LIMIT_REQUESTS` | ❌ | `100` | Max requests per IP per minute |
| `ABUSE_SCORE_BLOCK_THRESHOLD` | ❌ | `0.9` | Block requests above this score (0.5-1.0) |
| `DEMO_TOKENS_PER_REQUEST` | ❌ | `100` | Estimated tokens for quota pre-check (1-1000) |
| `IP_SUSPICIOUS_REQ_PER_MIN` | ❌ | `5` | Requests/min to flag IP as suspicious |
| `IP_SUSPICIOUS_UNIQUE_USERS` | ❌ | `10` | Unique users to flag IP as suspicious |
</details>

<details>
<summary><b>⚡ Concurrency</b></summary>

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `UVICORN_WORKERS` | ❌ | `4` | Number of worker processes (1-32) |
| `MAX_CONCURRENT_REQUESTS` | ❌ | `10` | Max concurrent Gemini API calls per worker (1-100) |

**Capacity Calculation:**
```
Total Concurrent = UVICORN_WORKERS × MAX_CONCURRENT_REQUESTS
Example: 4 workers × 10 = 40 max concurrent Gemini API calls
```
</details>

<details>
<summary><b>🗄️ Database Pool</b></summary>

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_POOL_MIN_SIZE` | ❌ | `5` | Minimum connections per worker (1-50) |
| `DB_POOL_MAX_SIZE` | ❌ | `20` | Maximum connections per worker (1-100) |
| `DB_COMMAND_TIMEOUT` | ❌ | `60` | Query timeout in seconds (5-300) |
| `DB_POOL_MAX_INACTIVE_LIFETIME` | ❌ | `300` | Idle connection timeout in seconds (60-3600) |

**Connection Calculation:**
```
Total DB Connections = UVICORN_WORKERS × DB_POOL_MAX_SIZE
Example: 4 workers × 20 = 80 max database connections
```

**PostgreSQL Configuration:**

Ensure your PostgreSQL `max_connections` is properly configured:

```sql
-- Check current setting
SHOW max_connections;

-- Recommended formula:
-- max_connections = (UVICORN_WORKERS × DB_POOL_MAX_SIZE) + 20 (overhead)
-- Example: (4 × 20) + 20 = 100 minimum

-- Update PostgreSQL configuration
ALTER SYSTEM SET max_connections = 100;
-- Requires PostgreSQL restart to take effect
```

| Deployment | Workers | Pool Max | Total Connections | Recommended max_connections |
|------------|---------|----------|-------------------|----------------------------|
| Development | 1 | 10 | 10 | 30 |
| Small | 2 | 20 | 40 | 60 |
| Medium | 4 | 20 | 80 | 100 |
| Large | 8 | 20 | 160 | 200 |

> ⚠️ The overhead (20) accounts for superuser connections, replication, monitoring tools, and migrations.
</details>

## 🧪 Token Consumption Scenarios

This section demonstrates the behavior of the token-bucket rate limiting system under different usage levels.

### Configuration Used

```bash
DEMO_MAX_TOKENS=5000          # 5,000 tokens per day
DEMO_COOLDOWN_HOURS=24        # 24h block after quota exceeded
DEMO_WARNING_THRESHOLD=85     # Warning at 85% usage
```

---

### Scenario 1: Normal Usage (< 85%)

User has consumed less than 85% of their daily quota.

<details>
<summary><b>GET /v1/demo/status</b></summary>

**Request:**
```bash
curl -X GET "http://localhost:9090/v1/demo/status" \
  -H "Authorization: Bearer $JWT"
```

**Response (200 OK):**
```json
{
    "tokens_used": 119,
    "tokens_remaining": 4881,
    "daily_limit": 5000,
    "percentage_used": 2,
    "requests_count": 1,
    "is_blocked": false,
    "blocked_until": null,
    "user_timezone": "America/Costa_Rica",
    "last_reset": "2025-12-01T04:32:23.194167+00:00",
    "next_reset": "2025-12-01T20:00:00+00:00",
    "warning": {
        "is_warning": false,
        "message": null,
        "percentage_used": 2
    }
}
```
</details>

<details>
<summary><b>POST /v1/demo</b></summary>

**Request:**
```bash
curl -X POST "http://localhost:9090/v1/demo" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"input": "Hola, ¿qué es Odiseo?", "language": "es"}'
```

**Response (200 OK):**
```json
{
    "success": true,
    "response": "Hola. Odiseo es una plataforma de inteligencia artificial conversacional...",
    "tokens_used": 119,
    "tokens_remaining": 4881,
    "warning": {
        "is_warning": false,
        "message": null,
        "percentage_used": 2
    },
    "session_id": "078186d9-b9b1-4fa0-a8fe-852ba5b8cf32",
    "created_at": "2025-12-01T04:32:25.638974+00:00"
}
```
</details>

---

### Scenario 2: Warning Threshold (≥ 85%)

User has consumed 85% or more of their daily quota. A warning is included in responses.

<details>
<summary><b>GET /v1/demo/status</b></summary>

**Request:**
```bash
curl -X GET "http://localhost:9090/v1/demo/status" \
  -H "Authorization: Bearer $JWT"
```

**Response (200 OK):**
```json
{
    "tokens_used": 4250,
    "tokens_remaining": 750,
    "daily_limit": 5000,
    "percentage_used": 85,
    "requests_count": 50,
    "is_blocked": false,
    "blocked_until": null,
    "user_timezone": "America/Costa_Rica",
    "last_reset": "2025-12-01T04:32:23.194167+00:00",
    "next_reset": "2025-12-01T20:00:00+00:00",
    "warning": {
        "is_warning": true,
        "message": "You've consumed 85% of your daily quota",
        "percentage_used": 85
    }
}
```
</details>

<details>
<summary><b>POST /v1/demo</b></summary>

**Request:**
```bash
curl -X POST "http://localhost:9090/v1/demo" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"input": "Dame un consejo breve", "language": "es"}'
```

**Response (200 OK):**
```json
{
    "success": true,
    "response": "Como asistente de demostración de Odiseo IA...",
    "tokens_used": 61,
    "tokens_remaining": 689,
    "warning": {
        "is_warning": true,
        "message": "You've consumed 86% of your daily quota",
        "percentage_used": 86
    },
    "session_id": "b4d9229a-e007-4f8a-b155-e9f53f1e4dd7",
    "created_at": "2025-12-01T04:33:17.704074+00:00"
}
```
</details>

---

### Scenario 3: Quota Exceeded (100%) - Blocked

User has exhausted their daily quota. All POST requests are rejected until reset.

<details>
<summary><b>GET /v1/demo/status</b></summary>

**Request:**
```bash
curl -X GET "http://localhost:9090/v1/demo/status" \
  -H "Authorization: Bearer $JWT"
```

**Response (200 OK):**
```json
{
    "tokens_used": 5000,
    "tokens_remaining": 0,
    "daily_limit": 5000,
    "percentage_used": 100,
    "requests_count": 100,
    "is_blocked": true,
    "blocked_until": "2025-12-02T04:33:30.035685+00:00",
    "user_timezone": "America/Costa_Rica",
    "last_reset": "2025-12-01T04:32:23.194167+00:00",
    "next_reset": "2025-12-01T20:00:00+00:00",
    "warning": {
        "is_warning": true,
        "message": "You've consumed 100% of your daily quota",
        "percentage_used": 100
    }
}
```
</details>

<details>
<summary><b>POST /v1/demo (Blocked)</b></summary>

**Request:**
```bash
curl -X POST "http://localhost:9090/v1/demo" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"input": "Esto debería fallar", "language": "es"}'
```

**Response (403 Forbidden):**
```json
{
    "success": false,
    "error": "suspicious_behavior_detected",
    "message": "Quota exceeded. Limit: 5,000 tokens. Reset: 2025-12-01T20:00:00+00:00.",
    "retry_after_seconds": 300
}
```
</details>

---

### Scenario 4: Transition to Blocked State 🔄

User is near the limit (4998/5000 tokens, only 2 remaining). A single query exceeds the limit, triggering automatic blocking with a 24-hour cooldown.

<details>
<summary><b>Step 1: GET /v1/demo/status (Before - Not Blocked)</b></summary>

**Request:**
```bash
curl -X GET "http://localhost:9090/v1/demo/status" \
  -H "Authorization: Bearer $JWT"
```

**Response (200 OK):**
```json
{
    "tokens_used": 4998,
    "tokens_remaining": 2,
    "daily_limit": 5000,
    "percentage_used": 99,
    "requests_count": 80,
    "is_blocked": false,
    "blocked_until": null,
    "user_timezone": "America/Costa_Rica",
    "last_reset": "2025-12-01T04:32:23.194167+00:00",
    "next_reset": "2025-12-01T20:00:00+00:00",
    "warning": {
        "is_warning": true,
        "message": "You've consumed 99% of your daily quota",
        "percentage_used": 99
    }
}
```
</details>

<details>
<summary><b>Step 2: POST /v1/demo (Query that Exceeds Limit)</b></summary>

**Request:**
```bash
curl -X POST "http://localhost:9090/v1/demo" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"input": "Hola", "language": "es"}'
```

**Response (200 OK) - Last successful query:**
```json
{
    "success": true,
    "response": "Hola. Soy tu asistente de demostración de Odiseo IA. ¿En qué puedo ayudarte hoy con respecto a nuestro producto?",
    "tokens_used": 27,
    "tokens_remaining": 0,
    "warning": {
        "is_warning": true,
        "message": "You've consumed 100% of your daily quota",
        "percentage_used": 100
    },
    "session_id": "8bf43230-e856-40ff-82c6-e4c19ed5df36",
    "created_at": "2025-12-01T04:39:24.035070+00:00"
}
```

> ⚠️ **Note:** The query consumed 27 tokens (4998 + 27 = 5025), exceeding the 5000 limit. The response is still returned, but the user is now blocked.
</details>

<details>
<summary><b>Step 3: GET /v1/demo/status (After - Now Blocked)</b></summary>

**Request:**
```bash
curl -X GET "http://localhost:9090/v1/demo/status" \
  -H "Authorization: Bearer $JWT"
```

**Response (200 OK):**
```json
{
    "tokens_used": 5025,
    "tokens_remaining": 0,
    "daily_limit": 5000,
    "percentage_used": 100,
    "requests_count": 81,
    "is_blocked": true,
    "blocked_until": "2025-12-02T04:39:24.022266+00:00",
    "user_timezone": "America/Costa_Rica",
    "last_reset": "2025-12-01T04:32:23.194167+00:00",
    "next_reset": "2025-12-01T20:00:00+00:00",
    "warning": {
        "is_warning": true,
        "message": "You've consumed 100% of your daily quota",
        "percentage_used": 100
    }
}
```

> 🔒 **Blocked:** `is_blocked: true` with `blocked_until` showing the exact unblock timestamp (24 hours from now).
</details>

<details>
<summary><b>Step 4: POST /v1/demo (Subsequent Request - Rejected)</b></summary>

**Request:**
```bash
curl -X POST "http://localhost:9090/v1/demo" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"input": "¿Puedo preguntar algo más?", "language": "es"}'
```

**Response (403 Forbidden):**
```json
{
    "success": false,
    "error": "suspicious_behavior_detected",
    "message": "Quota exceeded. Limit: 5,000 tokens. Reset: 2025-12-01T20:00:00+00:00.",
    "retry_after_seconds": 300
}
```

> ❌ All subsequent POST requests are rejected until the `blocked_until` timestamp is reached.
</details>

---

### Scenario 5: Transition to Warning State ⚠️

User is just below the warning threshold (4249/5000 tokens = 84.98%). A single query pushes them over 85%, activating the warning state.

<details>
<summary><b>Step 1: GET /v1/demo/status (Before - No Warning)</b></summary>

**Request:**
```bash
curl -X GET "http://localhost:9090/v1/demo/status" \
  -H "Authorization: Bearer $JWT"
```

**Response (200 OK):**
```json
{
    "tokens_used": 4249,
    "tokens_remaining": 751,
    "daily_limit": 5000,
    "percentage_used": 84,
    "requests_count": 70,
    "is_blocked": false,
    "blocked_until": null,
    "user_timezone": "America/Costa_Rica",
    "last_reset": "2025-12-01T04:32:23.194167+00:00",
    "next_reset": "2025-12-01T20:00:00+00:00",
    "warning": {
        "is_warning": false,
        "message": null,
        "percentage_used": 84
    }
}
```

> ✅ `warning.is_warning: false` - User is at 84%, just below the 85% threshold.
</details>

<details>
<summary><b>Step 2: POST /v1/demo (Query that Triggers Warning)</b></summary>

**Request:**
```bash
curl -X POST "http://localhost:9090/v1/demo" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"input": "Hola", "language": "es"}'
```

**Response (200 OK):**
```json
{
    "success": true,
    "response": "¡Hola! Soy tu asistente de demostración de Odiseo IA. ¿En qué puedo ayudarte hoy con respecto a nuestro producto?",
    "tokens_used": 28,
    "tokens_remaining": 723,
    "warning": {
        "is_warning": true,
        "message": "You've consumed 85% of your daily quota",
        "percentage_used": 85
    },
    "session_id": "9adc0668-9255-4a52-a6ed-fac70b3f412a",
    "created_at": "2025-12-01T04:48:29.104871+00:00"
}
```

> ⚠️ **Warning activated:** The query consumed 28 tokens (4249 + 28 = 4277), crossing the 85% threshold (4250).
</details>

<details>
<summary><b>Step 3: GET /v1/demo/status (After - Warning Active)</b></summary>

**Request:**
```bash
curl -X GET "http://localhost:9090/v1/demo/status" \
  -H "Authorization: Bearer $JWT"
```

**Response (200 OK):**
```json
{
    "tokens_used": 4277,
    "tokens_remaining": 723,
    "daily_limit": 5000,
    "percentage_used": 85,
    "requests_count": 71,
    "is_blocked": false,
    "blocked_until": null,
    "user_timezone": "America/Costa_Rica",
    "last_reset": "2025-12-01T04:32:23.194167+00:00",
    "next_reset": "2025-12-01T20:00:00+00:00",
    "warning": {
        "is_warning": true,
        "message": "You've consumed 85% of your daily quota",
        "percentage_used": 85
    }
}
```

> ⚠️ **Warning now active:** `is_warning: true` with message indicating 85% consumption. User can still make requests but should be aware of approaching limit.
</details>

---

### Summary Table

| Scenario | % Used | `is_blocked` | `warning.is_warning` | POST Result |
|----------|--------|--------------|----------------------|-------------|
| Normal | 0-84% | `false` | `false` | ✅ 200 OK |
| Warning Transition | 84% → 85% | `false` | `false` → `true` | ✅ 200 OK (warning activated) |
| Warning | 85-99% | `false` | `true` | ✅ 200 OK (with warning) |
| Block Transition | 99% → 100% | `false` → `true` | `true` | ✅ 200 OK (last query) |
| Blocked | 100%+ | `true` | `true` | ❌ 403 Forbidden |

### Blocking Behavior

```
┌─────────────────────────────────────────────────────────────┐
│  User State Flow                                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Normal] ──(85%)──► [Warning] ──(100%)──► [Blocked]       │
│     │                    │                     │            │
│     ▼                    ▼                     ▼            │
│  is_blocked: false   is_blocked: false    is_blocked: true  │
│  warning: false      warning: true        blocked_until: +24h│
│                                                             │
│  After 24h OR next_reset (whichever comes first):           │
│  [Blocked] ──(auto-reset)──► [Normal]                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 🗄️ Database Schema

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryTextColor': '#000000', 'textColor': '#000000', 'lineColor': '#333333' }}}%%
erDiagram
    demo_users {
        int id PK
        string clerk_user_id UK
        string email UK
        string full_name
        boolean is_active
        timestamp created_at
        timestamp last_login_at
    }

    demo_usage {
        int id PK
        int user_id FK
        int tokens_consumed
        int requests_count
        boolean is_blocked
        timestamp blocked_until
        timestamp last_reset
    }

    demo_chat_history {
        int id PK
        int user_id FK
        string role
        text message_text
        int token_count
        timestamp created_at
    }

    demo_audit_log {
        int id PK
        int user_id FK
        string ip_address
        string action_taken
        float abuse_score
        timestamp created_at
    }

    demo_users ||--|| demo_usage : has
    demo_users ||--o{ demo_chat_history : has
    demo_users ||--o{ demo_audit_log : generates
```

## 🧪 Development

### Code Quality

```bash
# Format code
black app/

# Lint
ruff check app/

# Type checking
mypy app/ --ignore-missing-imports

# Run all checks
ruff check app/ && black --check app/ && isort --check app/
```

### Testing

```bash
# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

## 🔧 Troubleshooting

<details>
<summary><b>❌ "Authentication failed: Token expired"</b></summary>

Clerk JWTs expire after ~60 seconds. Generate a fresh token before each request.
</details>

<details>
<summary><b>❌ "Permission denied on aiplatform.endpoints.predict"</b></summary>

Add Vertex AI role to your service account:
```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:SA@PROJECT.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```
</details>

<details>
<summary><b>❌ "Demo quota exceeded"</b></summary>

Normal behavior - user reached 5,000 token limit. Quota resets automatically at midnight UTC.
</details>

<details>
<summary><b>❌ "PostgreSQL connection failed"</b></summary>

1. Verify `DATABASE_URL` in `.env`
2. Check PostgreSQL is running: `docker ps | grep postgres`
3. Test connection: `psql $DATABASE_URL`
</details>

## ⚡ Concurrency Architecture

The service is designed for high concurrency, supporting multiple simultaneous users through a combination of process-level parallelism and thread-based non-blocking I/O.

### Architecture Overview

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
    │ ThreadPool             │ ThreadPool             │ ThreadPool
    │ (10 threads)           │ (10 threads)           │ (10 threads)
    │                        │                        │
    │ DB Pool                │ DB Pool                │ DB Pool
    │ (5-20 conn)            │ (5-20 conn)            │ (5-20 conn)
    └─────────┘              └─────────┘              └─────────┘
```

### How It Works

1. **Uvicorn Workers**: Multiple worker processes handle requests in parallel. Each worker is an independent Python process with its own memory space.

2. **ThreadPoolExecutor**: Within each worker, a thread pool handles blocking Gemini API calls without blocking the asyncio event loop. This allows multiple concurrent API calls per worker.

3. **AsyncPG Connection Pool**: Database operations use async connections with a pool of 5-20 connections per worker, ensuring non-blocking database I/O.

### Configuration

```bash
# .env file

# Number of worker processes (default: 4)
# Recommended: 2-4 for most deployments, up to CPU cores for high load
UVICORN_WORKERS=4

# Max concurrent Gemini API calls per worker (default: 10)
# Controls ThreadPoolExecutor size for non-blocking API calls
MAX_CONCURRENT_REQUESTS=10

# Database pool settings per worker
DB_POOL_MIN_SIZE=5      # Minimum connections (default: 5)
DB_POOL_MAX_SIZE=20     # Maximum connections (default: 20)
DB_COMMAND_TIMEOUT=60   # Query timeout in seconds (default: 60)
```

### Capacity Planning

| Deployment Size | Workers | Concurrent/Worker | Total Capacity | Memory (est.) |
|-----------------|---------|-------------------|----------------|---------------|
| Development | 1 | 5 | 5 | ~200 MB |
| Small (startup) | 2 | 10 | 20 | ~400 MB |
| Medium (SMB) | 4 | 10 | 40 | ~800 MB |
| Large (enterprise) | 8 | 15 | 120 | ~1.6 GB |

### Performance Tips

1. **Scale Workers First**: Increase `UVICORN_WORKERS` before `MAX_CONCURRENT_REQUESTS` for better resource isolation.

2. **Monitor Memory**: Each worker uses ~100-200 MB. Adjust workers based on available RAM.

3. **Database Connections**: Total DB connections = `UVICORN_WORKERS × 20` (max pool). Ensure PostgreSQL `max_connections` is configured accordingly.

4. **API Quotas**: Check Google Cloud Vertex AI quotas. Default is ~60 requests/minute for Gemini 2.5 Flash.

### Docker Deployment

```bash
# Deploy with custom concurrency settings
UVICORN_WORKERS=4 MAX_CONCURRENT_REQUESTS=10 docker-compose up -d --build

# Or set in .env file and run
docker-compose up -d --build
```

## 📈 Roadmap

- [x] High concurrency support with ThreadPoolExecutor
- [ ] Redis caching for rate limiting
- [ ] Analytics dashboard
- [ ] A/B testing support
- [ ] GraphQL API endpoint
- [ ] WebSocket streaming responses

## 📜 Version History

| Version | Date | Changes |
|---------|------|---------|
| **2.2.0** | Dec 2025 | Security hardening: fail-closed rate limiters, configurable thresholds, idle connection management |
| **2.1.0** | Nov 2025 | High concurrency support with ThreadPoolExecutor |
| **2.0.0** | Nov 2025 | Simplified Clerk auth (JWKS-only) |
| **1.0.0** | Oct 2025 | Initial release |

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

## 👥 Authors

**Odiseo Team** - 2025

---

<p align="center">
  Made with ❤️ by <a href="https://www.nexusintelligent.ai/">Odiseo</a>
</p>
