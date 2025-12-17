# Deployment Guide - Google Cloud Run

This guide explains how to deploy the Demo Agent service to Google Cloud Run.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Google Cloud                                    │
│                                                                        │
│  ┌─────────────┐     ┌──────────────┐     ┌───────────────────┐      │
│  │ API Gateway │────▶│  Cloud Run   │────▶│    Vertex AI      │      │
│  │  (public)   │     │ (demo-agent) │     │  (Gemini 2.5)     │      │
│  └─────────────┘     └──────────────┘     └───────────────────┘      │
│        │                    │                                         │
│        │              ┌─────▼────────┐                               │
│        │              │  Cloud SQL   │                               │
│        │              │ (PostgreSQL) │                               │
│        │              └──────────────┘                               │
│        │                                                              │
│   ┌────▼─────┐      ┌──────────────┐      ┌──────────────┐          │
│   │ Secret   │      │  Artifact    │      │ Workload ID  │          │
│   │ Manager  │      │  Registry    │      │ Federation   │          │
│   └──────────┘      └──────────────┘      └──────────────┘          │
└──────────────────────────────────────────────────────────────────────┘

Note: Due to organization IAM policies, public access is provided via
API Gateway instead of direct Cloud Run --allow-unauthenticated.
```

## Prerequisites

1. **Google Cloud SDK** installed and configured
   ```bash
   # Install: https://cloud.google.com/sdk/docs/install
   gcloud auth login
   ```

2. **Billing enabled** on your GCP project

3. **Docker** installed (for local builds)

## Quick Start

### Option 1: Automatic (GitHub Actions)

1. **Run initial setup** (one time only):
   ```bash
   make gcp-setup
   ```

2. **Add GitHub Secrets** (Settings > Secrets > Actions):
   - `GCP_PROJECT_ID`
   - `GCP_REGION`
   - `GCP_SA_EMAIL`
   - `GCP_WORKLOAD_IDENTITY_PROVIDER`
   - `CLOUD_SQL_CONNECTION`

3. **Push to main branch** - deployment triggers automatically

### Option 2: Manual Deployment

```bash
# One-time setup
make gcp-setup

# Deploy
make gcp-deploy
```

## Configuration Details

### GCP Project Info
| Setting | Value |
|---------|-------|
| Project ID | `gen-lang-client-0329024102` |
| Region | `us-central1` |
| Service Name | `demo-agent` |
| API Gateway URL | `https://demo-agent-gateway-vq1gs9i.uc.gateway.dev` |
| Custom Domain | `api.nexusintelligent.ai` (requires DNS setup) |
| Load Balancer IP | `34.54.168.237` |

### Cloud SQL
| Setting | Value |
|---------|-------|
| Instance | `demo-db` |
| Database | `demodb` |
| User | `demo_user` |
| Version | PostgreSQL 15 |
| Schema | `test` |

### Clerk JWT
| Setting | Value |
|---------|-------|
| JWT Template | `odiseo-api` |
| Required Claims | `email`, `name` |

### Secrets (Secret Manager)
| Secret Name | Description |
|-------------|-------------|
| `database-url` | Complete DATABASE_URL with password |
| `db-password` | Database password (legacy) |
| `clerk-secret-key` | Clerk backend API key |
| `clerk-publishable-key` | Clerk frontend key |
| `clerk-webhook-secret` | Clerk webhook verification |

## Files

```
deploy/
├── README.md              # This file
├── setup-gcp.sh           # Initial GCP infrastructure setup
├── deploy-manual.sh       # Manual deployment script
├── Dockerfile.cloudrun    # Production-optimized Dockerfile
└── env.production         # Production environment reference

.github/workflows/
└── deploy-gcp.yml         # GitHub Actions CI/CD workflow
```

## Commands

```bash
# Initial setup (run once)
make gcp-setup

# Manual deploy
make gcp-deploy

# View logs
make gcp-logs

# Service details
make gcp-describe

# Get service URL
make gcp-url
```

## Update Secrets

To update Clerk secrets after initial setup:

```bash
# Update secret value
echo -n "sk_live_YOUR_ACTUAL_KEY" | \
  gcloud secrets versions add clerk-secret-key --data-file=-

echo -n "pk_live_YOUR_ACTUAL_KEY" | \
  gcloud secrets versions add clerk-publishable-key --data-file=-

echo -n "whsec_YOUR_ACTUAL_SECRET" | \
  gcloud secrets versions add clerk-webhook-secret --data-file=-
```

## Custom Domain Setup

Due to organization IAM policies, custom domain setup uses Load Balancer:

1. **Configure DNS** to point to the Load Balancer IP:
   ```
   api.nexusintelligent.ai.  A  34.54.168.237
   ```

2. **Wait for SSL certificate provisioning** (automatic once DNS is configured):
   ```bash
   gcloud compute ssl-certificates describe demo-agent-cert \
     --global --format="yaml(managed.domainStatus)"
   ```

3. **Verify access** via custom domain:
   ```bash
   curl https://api.nexusintelligent.ai/health
   ```

**Alternative: API Gateway URL** (works immediately):
```
https://demo-agent-gateway-vq1gs9i.uc.gateway.dev
```

## Monitoring

```bash
# Real-time logs
gcloud run services logs tail demo-agent --region=us-central1

# Metrics dashboard
open https://console.cloud.google.com/run/detail/us-central1/demo-agent/metrics

# Error reporting
open https://console.cloud.google.com/errors
```

## Troubleshooting

### Deployment fails
```bash
# Check Cloud Build logs
gcloud builds list --limit=5

# Check specific build
gcloud builds log BUILD_ID
```

### Service not responding
```bash
# Check service status
gcloud run services describe demo-agent --region=us-central1

# Check recent logs
gcloud run services logs read demo-agent --region=us-central1 --limit=50
```

### Database connection issues
```bash
# Verify Cloud SQL instance
gcloud sql instances describe demo-db

# Check connectivity
gcloud sql connect demo-db --user=demo_user
```

## Cost Estimation

| Service | Configuration | Monthly Cost |
|---------|---------------|--------------|
| Cloud Run | 1 vCPU, 1GB, ~100k req | $5-20 |
| Cloud SQL | db-f1-micro, 10GB | $10-15 |
| Vertex AI | Gemini 2.5 Flash, ~1M tokens | $75 |
| Secret Manager | 5 secrets | <$1 |
| Artifact Registry | <1GB | <$1 |
| **Total** | | **~$90-110** |

## Scaling

Cloud Run scales automatically. To adjust:

```bash
# Set minimum instances (avoid cold starts)
gcloud run services update demo-agent \
  --min-instances=1 \
  --region=us-central1

# Set maximum instances
gcloud run services update demo-agent \
  --max-instances=20 \
  --region=us-central1
```
