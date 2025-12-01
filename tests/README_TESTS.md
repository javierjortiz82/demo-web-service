# Demo Agent Test Suite

Test suite for the Odiseo Demo Agent service.

## 📁 Test Files

| File | Type | Purpose |
|------|------|---------|
| `test_ip_limiter.py` | Unit Tests | IP-based rate limiting tests |
| `test_ip_limiter_async.py` | Async Tests | Async IP limiter tests |
| `test_token_bucket.py` | Unit Tests | Token bucket algorithm tests |
| `test_token_counting.py` | Unit Tests | Token counting tests |
| `conftest.py` | Pytest Config | Fixtures and configuration |

---

## 🚀 Running Tests

### Run All Tests

```bash
cd /home/javort/demo-service
pytest tests/ -v
```

### Run Specific Test Categories

```bash
# IP limiter tests
pytest tests/test_ip_limiter.py -v

# Token bucket tests
pytest tests/test_token_bucket.py -v

# Token counting tests
pytest tests/test_token_counting.py -v
```

### Run with Coverage

```bash
pytest tests/ --cov=app --cov-report=html
```

---

## 🔧 Test Configuration

Tests use fixtures defined in `conftest.py`. Environment variables are loaded from `.env`.

### Required Environment Variables

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/db
SCHEMA_NAME=test
```

---

## 📊 Test Categories

### 1. Rate Limiting Tests (`test_ip_limiter.py`)
- IP-based request limiting
- Sliding window algorithm
- Block/unblock logic

### 2. Token Bucket Tests (`test_token_bucket.py`)
- Token consumption tracking
- Daily limit enforcement
- Warning threshold detection
- Auto-reset functionality

### 3. Token Counting Tests (`test_token_counting.py`)
- Gemini response token counting
- Usage tracking accuracy

---

**Last Updated:** 2025-12-01
