# Demo Service - Deployment Guide for Google Cloud

This guide provides step-by-step instructions to deploy the demo-service to Google Cloud Run with Clerk authentication and Cloud SQL (PostgreSQL).

## Overview

| Component | Value |
|-----------|-------|
| **Project ID** | `gen-lang-client-0329024102` |
| **Region** | `us-central1` |
| **Service Name** | `demo-agent` |
| **Service Account** | `demo-service-sa@gen-lang-client-0329024102.iam.gserviceaccount.com` |
| **Cloud SQL** | `gen-lang-client-0329024102:us-central1:demo-db` |
| **API Gateway** | `https://demo-agent-gateway-vq1gs9i.uc.gateway.dev` |

### Clerk Configuration

| Setting | Value |
|---------|-------|
| **Frontend API** | `mighty-leopard-52.clerk.accounts.dev` |
| **JWKS URL** | `https://mighty-leopard-52.clerk.accounts.dev/.well-known/jwks.json` |
| **Publishable Key** | `pk_test_bWlnaHR5LWxlb3BhcmQtNTIuY2xlcmsuYWNjb3VudHMuZGV2JA` |

---

## Prerequisites

1. **Google Cloud SDK** installed and authenticated:
   ```bash
   gcloud auth login
   gcloud config set project gen-lang-client-0329024102
   ```

2. **Docker** installed locally

3. **PostgreSQL client** (optional, for schema setup)

---

## Step 1: Authenticate to Google Cloud

```bash
# Login to Google Cloud
gcloud auth login

# Set project
gcloud config set project gen-lang-client-0329024102

# Verify authentication
gcloud auth list
```

---

## Step 2: Setup Cloud SQL Database Schema

### Option A: Via Cloud SQL Proxy (Recommended)

```bash
# Install Cloud SQL Auth Proxy if not installed
# https://cloud.google.com/sql/docs/postgres/connect-auth-proxy

# Start proxy in a separate terminal
cloud-sql-proxy gen-lang-client-0329024102:us-central1:demo-db --port=5433

# Connect and run schema
PGPASSWORD='QvAio2n7owgI690aOhzbS1KD4SCbqkHh' psql -h localhost -p 5433 -U demo_user -d demodb -f deploy/schema-cloud-sql.sql
```

### Option B: Via gcloud sql connect

```bash
# Connect directly (interactive)
gcloud sql connect demo-db --user=demo_user --database=demodb

# Then paste the contents of deploy/schema-cloud-sql.sql
```

### Dynamic Schema Name

The schema script supports dynamic schema names via psql variable:

```bash
# Default schema (test)
psql -f deploy/schema-cloud-sql.sql

# Custom schema (production)
psql -v schema_name='production' -f deploy/schema-cloud-sql.sql
```

### Verify Schema

```sql
-- After running the schema, verify (replace 'test' with your schema):
\dt test.*

-- Expected tables:
--  demo_users
--  demo_usage
--  demo_audit_log
--  conversation_sessions
--  conversation_messages

-- Verify functions:
SELECT routine_name FROM information_schema.routines WHERE routine_schema = 'test';
```

---

## Step 3: Configure Secrets in Secret Manager

### Create/Update DATABASE_URL Secret

```bash
# Create the database-url secret with full connection string
echo -n "postgresql://demo_user:QvAio2n7owgI690aOhzbS1KD4SCbqkHh@/demodb?host=/cloudsql/gen-lang-client-0329024102:us-central1:demo-db" | \
  gcloud secrets create database-url --data-file=- 2>/dev/null || \
  gcloud secrets versions add database-url --data-file=-
```

### Update Clerk Publishable Key

```bash
echo -n "pk_test_bWlnaHR5LWxlb3BhcmQtNTIuY2xlcmsuYWNjb3VudHMuZGV2JA" | \
  gcloud secrets versions add clerk-publishable-key --data-file=-
```

### Verify Secrets

```bash
# List all secrets
gcloud secrets list

# Expected:
#  - database-url
#  - db-password (legacy)
#  - clerk-publishable-key
#  - clerk-secret-key (only needed for webhooks)
```

---

## Step 4: Build and Deploy to Cloud Run

### Option A: Manual Deployment Script

```bash
cd /home/javort/demo-service
./deploy/deploy-manual.sh
```

### Option B: Manual Commands

```bash
# Variables
PROJECT_ID="gen-lang-client-0329024102"
REGION="us-central1"
SERVICE_NAME="demo-agent"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/demo-repo/${SERVICE_NAME}"
SA_EMAIL="demo-service-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Build Docker image
docker build -f deploy/Dockerfile.cloudrun -t ${IMAGE}:latest .

# Configure Docker for Artifact Registry
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

# Push image
docker push ${IMAGE}:latest

# Deploy to Cloud Run
gcloud run deploy ${SERVICE_NAME} \
    --image=${IMAGE}:latest \
    --region=${REGION} \
    --platform=managed \
    --service-account=${SA_EMAIL} \
    --allow-unauthenticated \
    --port=8080 \
    --memory=1Gi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=10 \
    --timeout=300 \
    --concurrency=80 \
    --add-cloudsql-instances=gen-lang-client-0329024102:us-central1:demo-db \
    --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars="GCP_LOCATION=${REGION}" \
    --set-env-vars="MODEL=gemini-2.5-flash" \
    --set-env-vars="ENABLE_CLERK_AUTH=true" \
    --set-env-vars="CLERK_FRONTEND_API=mighty-leopard-52.clerk.accounts.dev" \
    --set-env-vars="CORS_ALLOW_ORIGINS=https://www.nexusintelligent.ai,https://odiseo-sales-ai.vercel.app,http://localhost:3000" \
    --set-env-vars="CORS_ALLOW_CREDENTIALS=true" \
    --set-env-vars="LOG_JSON_FORMAT=true" \
    --set-env-vars="LOG_LEVEL=INFO" \
    --set-env-vars="DEMO_MAX_TOKENS=5000" \
    --set-env-vars="SCHEMA_NAME=test" \
    --set-env-vars="DB_POOL_MIN_SIZE=2" \
    --set-env-vars="DB_POOL_MAX_SIZE=10" \
    --set-env-vars="ENABLE_FINGERPRINT=true" \
    --set-secrets="DATABASE_URL=database-url:latest" \
    --set-secrets="CLERK_PUBLISHABLE_KEY=clerk-publishable-key:latest"
```

---

## Step 5: Verify Deployment

### Check Service Status

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe demo-agent --region=us-central1 --format='value(status.url)')
echo "Service URL: $SERVICE_URL"

# Health check
curl "${SERVICE_URL}/health"
# Expected: {"status":"ok","service":"demo_agent","version":"2.0.0"}

# Root endpoint
curl "${SERVICE_URL}/"
```

### Check Logs

```bash
# View recent logs
gcloud run services logs read demo-agent --region=us-central1 --limit=50

# Stream logs in real-time
gcloud run services logs tail demo-agent --region=us-central1
```

---

## Step 6: Test Endpoints with curl

### Test Health Endpoint (No Auth)

```bash
curl -s https://demo-agent-gateway-vq1gs9i.uc.gateway.dev/health | jq
```

### Test Protected Endpoint (With Auth)

To test protected endpoints, you need a valid Clerk JWT token:

1. **Get a token from your frontend app** (inspect network requests after login)

2. **Or use Clerk API to generate a test token:**
   ```bash
   # Get session token from frontend Network tab (after login)
   TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
   ```

3. **Test /v1/demo/status:**
   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" \
     https://demo-agent-gateway-vq1gs9i.uc.gateway.dev/v1/demo/status | jq
   ```

4. **Test /v1/demo (POST):**
   ```bash
   curl -s -X POST \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"input": "Hello, what is Odiseo?", "language": "es"}' \
     https://demo-agent-gateway-vq1gs9i.uc.gateway.dev/v1/demo | jq
   ```

---

## Step 7: Update Frontend Configuration

Update the frontend `.env` to point to the cloud service:

**File: `/home/javort/odiseo-web/odiseo-sales-ai/.env`**

```env
# For development (direct to API Gateway)
VITE_API_URL="https://demo-agent-gateway-vq1gs9i.uc.gateway.dev"
VITE_DEMO_AGENT_URL="https://demo-agent-gateway-vq1gs9i.uc.gateway.dev"

# For production (using Vercel proxy)
# VITE_API_URL="/api"
# VITE_DEMO_AGENT_URL="/api"
```

---

## Troubleshooting

### Error: "Authentication failed: Token verification error"

1. **Check JWKS connectivity:**
   ```bash
   curl -s https://mighty-leopard-52.clerk.accounts.dev/.well-known/jwks.json | jq
   ```

2. **Verify Clerk Frontend API is correct:**
   ```bash
   gcloud run services describe demo-agent --region=us-central1 \
     --format='value(spec.template.spec.containers[0].env)' | grep CLERK
   ```

3. **Check token is valid** (decode at jwt.io)

### Error: "Database connection failed"

1. **Verify Cloud SQL connection:**
   ```bash
   gcloud sql instances describe demo-db --format='value(state)'
   # Expected: RUNNABLE
   ```

2. **Check DATABASE_URL secret:**
   ```bash
   gcloud secrets versions access latest --secret=database-url
   ```

3. **Verify service account has Cloud SQL Client role:**
   ```bash
   gcloud projects get-iam-policy gen-lang-client-0329024102 \
     --flatten="bindings[].members" \
     --filter="bindings.members:demo-service-sa" \
     --format="table(bindings.role)"
   ```

### Error: "CORS policy blocked"

1. **Check CORS_ALLOW_ORIGINS includes your frontend domain:**
   ```bash
   gcloud run services describe demo-agent --region=us-central1 \
     --format='value(spec.template.spec.containers[0].env)' | grep CORS
   ```

2. **Update CORS if needed:**
   ```bash
   gcloud run services update demo-agent --region=us-central1 \
     --set-env-vars="CORS_ALLOW_ORIGINS=https://www.nexusintelligent.ai,https://your-frontend.vercel.app"
   ```

### Error: "User not found" / 403 Forbidden

1. **Schema might not be applied.** Check if tables exist:
   ```bash
   gcloud sql connect demo-db --user=demo_user --database=demodb
   # Then: \dt test.*
   ```

2. **Run schema script if tables are missing:**
   ```bash
   # Using Cloud SQL Proxy
   PGPASSWORD='xxx' psql -h localhost -p 5433 -U demo_user -d demodb \
     -v schema_name='test' -f deploy/schema-cloud-sql.sql
   ```

### Error: "Email not in JWT claims"

1. **Frontend must use the custom JWT template:**
   ```typescript
   // Use odiseo-api template which includes email claim
   const token = await getToken({ template: 'odiseo-api' });
   ```

2. **Verify JWT template in Clerk Dashboard:**
   - Go to: https://dashboard.clerk.com/ > JWT Templates
   - Template name: `odiseo-api`
   - Ensure it includes: `email`, `name` claims

---

## Monitoring & Logs

### Cloud Console Links

- **Cloud Run:** https://console.cloud.google.com/run/detail/us-central1/demo-agent/metrics?project=gen-lang-client-0329024102
- **Logs:** https://console.cloud.google.com/logs/query?project=gen-lang-client-0329024102
- **Cloud SQL:** https://console.cloud.google.com/sql/instances/demo-db?project=gen-lang-client-0329024102

### Useful Commands

```bash
# View logs
gcloud run services logs read demo-agent --region=us-central1 --limit=100

# Check service status
gcloud run services describe demo-agent --region=us-central1

# Check revisions
gcloud run revisions list --service=demo-agent --region=us-central1

# Scale to 1 minimum instance (avoid cold starts)
gcloud run services update demo-agent --region=us-central1 --min-instances=1
```

---

## Summary of URLs

| Environment | URL |
|-------------|-----|
| **API Gateway** | `https://demo-agent-gateway-vq1gs9i.uc.gateway.dev` |
| **Cloud Run (direct)** | `https://demo-agent-4k3haexkga-uc.a.run.app` |
| **Custom Domain (pending DNS)** | `https://api.nexusintelligent.ai` |

---

*Last Updated: December 2025*
