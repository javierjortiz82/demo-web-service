#!/bin/bash
# =============================================================================
# Manual Deployment Script for Cloud Run
# =============================================================================
# Use this script to deploy manually without GitHub Actions.
#
# Prerequisites:
#   - GCP setup completed (run setup-gcp.sh first)
#   - Authenticated with: gcloud auth login
#
# Usage:
#   ./deploy/deploy-manual.sh [tag]
#
# Examples:
#   ./deploy/deploy-manual.sh           # Uses 'latest' tag
#   ./deploy/deploy-manual.sh v1.0.0    # Uses specified tag
# =============================================================================

set -e

# =============================================================================
# CONFIGURATION
# =============================================================================
PROJECT_ID="gen-lang-client-0997131817"
REGION="us-central1"
SERVICE_NAME="demo-agent"
REPO_NAME="demo-repo"
SA_EMAIL="demo-service-sa@${PROJECT_ID}.iam.gserviceaccount.com"

# Image tag (default: latest, or use git commit hash)
TAG="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo 'latest')}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================
echo ""
echo "=============================================="
echo "  Manual Deployment to Cloud Run"
echo "=============================================="
echo ""

log_info "Image: ${IMAGE}:${TAG}"

# Check gcloud auth
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n1 > /dev/null 2>&1; then
    log_error "Not authenticated. Run: gcloud auth login"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID 2>/dev/null

# =============================================================================
# STEP 1: Build Docker Image
# =============================================================================
echo ""
log_info "Step 1: Building Docker image..."

docker build \
    -f deploy/Dockerfile.cloudrun \
    -t ${IMAGE}:${TAG} \
    -t ${IMAGE}:latest \
    .

log_success "Image built: ${IMAGE}:${TAG}"

# =============================================================================
# STEP 2: Push to Artifact Registry
# =============================================================================
echo ""
log_info "Step 2: Pushing to Artifact Registry..."

# Configure Docker for Artifact Registry
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

docker push ${IMAGE}:${TAG}
docker push ${IMAGE}:latest

log_success "Image pushed!"

# =============================================================================
# STEP 3: Get Cloud SQL Connection
# =============================================================================
CLOUD_SQL_CONNECTION=$(gcloud sql instances describe demo-db --format='value(connectionName)' 2>/dev/null || echo "")

if [ -z "$CLOUD_SQL_CONNECTION" ]; then
    log_warning "Could not get Cloud SQL connection. Make sure the instance exists."
    log_warning "Continuing without Cloud SQL connection..."
    CLOUDSQL_FLAG=""
else
    log_info "Cloud SQL: ${CLOUD_SQL_CONNECTION}"
    CLOUDSQL_FLAG="--add-cloudsql-instances=${CLOUD_SQL_CONNECTION}"
fi

# =============================================================================
# STEP 4: Deploy to Cloud Run
# =============================================================================
echo ""
log_info "Step 3: Deploying to Cloud Run..."

gcloud run deploy ${SERVICE_NAME} \
    --image=${IMAGE}:${TAG} \
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
    ${CLOUDSQL_FLAG} \
    --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars="GCP_LOCATION=${REGION}" \
    --set-env-vars="MODEL=gemini-2.5-flash" \
    --set-env-vars="ENABLE_CLERK_AUTH=true" \
    --set-env-vars="CLERK_FRONTEND_API=mighty-leopard-52.clerk.accounts.dev" \
    --set-env-vars="CORS_ALLOW_ORIGINS=https://www.nexusintelligent.ai" \
    --set-env-vars="CORS_ALLOW_CREDENTIALS=true" \
    --set-env-vars="LOG_JSON_FORMAT=true" \
    --set-env-vars="LOG_LEVEL=INFO" \
    --set-env-vars="DEMO_MAX_TOKENS=5000" \
    --set-env-vars="DATABASE_URL=postgresql://demo_user:\${DB_PASSWORD}@/demodb?host=/cloudsql/${CLOUD_SQL_CONNECTION}" \
    --set-secrets="DB_PASSWORD=db-password:latest" \
    --set-secrets="CLERK_SECRET_KEY=clerk-secret-key:latest" \
    --set-secrets="CLERK_PUBLISHABLE_KEY=clerk-publishable-key:latest" \
    --quiet

log_success "Deployment complete!"

# =============================================================================
# STEP 5: Get Service URL and Health Check
# =============================================================================
echo ""
log_info "Step 4: Verifying deployment..."

SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --region=${REGION} \
    --format='value(status.url)')

echo ""
log_info "Service URL: ${SERVICE_URL}"

# Health check
log_info "Running health check..."
for i in {1..10}; do
    if curl -sf "${SERVICE_URL}/health" > /dev/null 2>&1; then
        log_success "Health check passed!"
        break
    fi
    echo "Attempt $i/10 - waiting..."
    sleep 5
done

# =============================================================================
# SUMMARY
# =============================================================================
echo ""
echo "=============================================="
echo "  Deployment Summary"
echo "=============================================="
echo ""
echo "Service:  ${SERVICE_NAME}"
echo "Region:   ${REGION}"
echo "Image:    ${IMAGE}:${TAG}"
echo "URL:      ${SERVICE_URL}"
echo ""
echo "Useful commands:"
echo "  View logs:    gcloud run services logs read ${SERVICE_NAME} --region=${REGION}"
echo "  Describe:     gcloud run services describe ${SERVICE_NAME} --region=${REGION}"
echo "  Traffic:      gcloud run services update-traffic ${SERVICE_NAME} --to-latest --region=${REGION}"
echo ""
