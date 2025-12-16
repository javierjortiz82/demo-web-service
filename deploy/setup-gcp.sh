#!/bin/bash
# =============================================================================
# GCP Initial Setup Script for Demo Service
# =============================================================================
# This script sets up all required GCP infrastructure for the demo-service.
# Run this ONCE before the first deployment.
#
# Prerequisites:
#   - Google Cloud SDK installed (gcloud)
#   - Authenticated with: gcloud auth login
#   - Billing enabled on the project
#
# Usage:
#   chmod +x deploy/setup-gcp.sh
#   ./deploy/setup-gcp.sh
#
# Best Practices Applied:
#   - Principle of least privilege for IAM roles
#   - SSL enforcement for Cloud SQL
#   - Workload Identity Federation (no service account keys)
#   - Secret Manager for sensitive data
#   - Idempotent operations (safe to re-run)
# =============================================================================

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# =============================================================================
# CONFIGURATION
# =============================================================================
PROJECT_ID="gen-lang-client-0329024102"
REGION="us-central1"
SERVICE_NAME="demo-agent"
DB_INSTANCE_NAME="demo-db"
DB_NAME="demodb"
DB_USER="demo_user"
DB_TIER="db-f1-micro"
REPO_NAME="demo-repo"
SA_NAME="demo-service-sa"
GITHUB_REPO="javierjortiz82/demo-web-service"
CUSTOM_DOMAIN="api.nexusintelligent.ai"

# Output file for GitHub secrets
OUTPUT_FILE="deploy/.gcp-setup-output.txt"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 is not installed. Please install it first."
        exit 1
    fi
}

# Check if resource exists (returns 0 if exists)
resource_exists() {
    local type=$1
    shift
    case $type in
        "sql-instance")
            gcloud sql instances describe "$1" &>/dev/null
            ;;
        "sql-database")
            gcloud sql databases describe "$1" --instance="$2" &>/dev/null
            ;;
        "service-account")
            gcloud iam service-accounts describe "$1" &>/dev/null
            ;;
        "secret")
            gcloud secrets describe "$1" &>/dev/null
            ;;
        "artifact-repo")
            gcloud artifacts repositories describe "$1" --location="$2" &>/dev/null
            ;;
        "wif-pool")
            gcloud iam workload-identity-pools describe "$1" --location=global &>/dev/null
            ;;
        "wif-provider")
            gcloud iam workload-identity-pools providers describe "$1" \
                --workload-identity-pool="$2" --location=global &>/dev/null
            ;;
    esac
}

# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║       GCP Setup for Demo Service (Odiseo)                    ║"
echo "║       Project: $PROJECT_ID                    ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

log_step "Pre-flight Checks"

check_command gcloud
check_command openssl

# Verify authentication
CURRENT_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -n1)
if [ -z "$CURRENT_ACCOUNT" ]; then
    log_error "Not authenticated. Run: gcloud auth login"
    exit 1
fi
log_success "Authenticated as: $CURRENT_ACCOUNT"

# Set and verify project
gcloud config set project "$PROJECT_ID" --quiet
if ! gcloud projects describe "$PROJECT_ID" &>/dev/null; then
    log_error "Project $PROJECT_ID not found or no access"
    exit 1
fi
log_success "Project: $PROJECT_ID"

# Get project number (needed later)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
log_success "Project Number: $PROJECT_NUMBER"

# =============================================================================
# STEP 1: Enable Required APIs
# =============================================================================
log_step "Step 1/7: Enabling APIs"

APIS=(
    "run.googleapis.com"              # Cloud Run
    "sqladmin.googleapis.com"         # Cloud SQL Admin
    "secretmanager.googleapis.com"    # Secret Manager
    "artifactregistry.googleapis.com" # Artifact Registry
    "aiplatform.googleapis.com"       # Vertex AI
    "cloudbuild.googleapis.com"       # Cloud Build
    "compute.googleapis.com"          # Compute Engine (networking)
    "iam.googleapis.com"              # IAM
    "iamcredentials.googleapis.com"   # IAM Credentials (for WIF)
    "cloudresourcemanager.googleapis.com"  # Resource Manager
)

for api in "${APIS[@]}"; do
    if gcloud services list --enabled --filter="name:$api" --format="value(name)" | grep -q "$api"; then
        log_success "$api (already enabled)"
    else
        log_info "Enabling $api..."
        gcloud services enable "$api" --quiet
        log_success "$api"
    fi
done

# =============================================================================
# STEP 2: Create Artifact Registry
# =============================================================================
log_step "Step 2/7: Artifact Registry"

if resource_exists artifact-repo "$REPO_NAME" "$REGION"; then
    log_success "Repository '$REPO_NAME' already exists"
else
    log_info "Creating repository..."
    gcloud artifacts repositories create "$REPO_NAME" \
        --repository-format=docker \
        --location="$REGION" \
        --description="Demo Service Docker images"
    log_success "Repository '$REPO_NAME' created"
fi

# =============================================================================
# STEP 3: Create Cloud SQL Instance
# =============================================================================
log_step "Step 3/7: Cloud SQL (PostgreSQL 15)"

if resource_exists sql-instance "$DB_INSTANCE_NAME"; then
    log_success "Instance '$DB_INSTANCE_NAME' already exists"
else
    log_warning "Creating Cloud SQL instance (this takes 5-10 minutes)..."
    gcloud sql instances create "$DB_INSTANCE_NAME" \
        --database-version=POSTGRES_15 \
        --tier="$DB_TIER" \
        --region="$REGION" \
        --storage-type=SSD \
        --storage-size=10GB \
        --storage-auto-increase \
        --availability-type=zonal \
        --backup-start-time=03:00 \
        --maintenance-window-day=SUN \
        --maintenance-window-hour=04 \
        --database-flags=log_checkpoints=on,log_connections=on,log_disconnections=on \
        --quiet
    log_success "Instance '$DB_INSTANCE_NAME' created"
fi

# Enforce SSL connections
log_info "Enforcing SSL connections..."
gcloud sql instances patch "$DB_INSTANCE_NAME" \
    --require-ssl \
    --quiet 2>/dev/null || log_warning "SSL may already be enforced"

# Create database
if resource_exists sql-database "$DB_NAME" "$DB_INSTANCE_NAME"; then
    log_success "Database '$DB_NAME' already exists"
else
    gcloud sql databases create "$DB_NAME" --instance="$DB_INSTANCE_NAME"
    log_success "Database '$DB_NAME' created"
fi

# Generate secure password
DB_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%' | head -c 32)

# Create/update user
log_info "Configuring database user..."
if gcloud sql users list --instance="$DB_INSTANCE_NAME" --format="value(name)" | grep -q "^${DB_USER}$"; then
    gcloud sql users set-password "$DB_USER" \
        --instance="$DB_INSTANCE_NAME" \
        --password="$DB_PASSWORD" \
        --quiet
    log_success "User '$DB_USER' password updated"
else
    gcloud sql users create "$DB_USER" \
        --instance="$DB_INSTANCE_NAME" \
        --password="$DB_PASSWORD"
    log_success "User '$DB_USER' created"
fi

# Get connection name
CLOUD_SQL_CONNECTION=$(gcloud sql instances describe "$DB_INSTANCE_NAME" --format='value(connectionName)')
log_success "Connection: $CLOUD_SQL_CONNECTION"

# =============================================================================
# STEP 4: Create Service Account
# =============================================================================
log_step "Step 4/7: Service Account & IAM"

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if resource_exists service-account "$SA_EMAIL"; then
    log_success "Service account '$SA_NAME' already exists"
else
    gcloud iam service-accounts create "$SA_NAME" \
        --display-name="Demo Service Account" \
        --description="Service account for demo-agent Cloud Run service"
    log_success "Service account '$SA_NAME' created"
fi

# Grant minimal required roles (principle of least privilege)
ROLES=(
    "roles/aiplatform.user"              # Vertex AI API calls
    "roles/cloudsql.client"              # Cloud SQL connections
    "roles/secretmanager.secretAccessor" # Read secrets
    "roles/logging.logWriter"            # Write logs
    "roles/monitoring.metricWriter"      # Write metrics
    "roles/run.developer"                # Deploy to Cloud Run (not admin)
    "roles/artifactregistry.writer"      # Push Docker images
)

log_info "Granting IAM roles..."
for role in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="$role" \
        --condition=None \
        --quiet &>/dev/null
done
log_success "IAM roles granted (${#ROLES[@]} roles)"

# Allow SA to act as itself (required for Cloud Run deployment)
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --role="roles/iam.serviceAccountUser" \
    --member="serviceAccount:${SA_EMAIL}" \
    --quiet &>/dev/null
log_success "Service account self-impersonation enabled"

# =============================================================================
# STEP 5: Secret Manager
# =============================================================================
log_step "Step 5/7: Secret Manager"

create_secret() {
    local name=$1
    local value=$2
    local description=$3

    if resource_exists secret "$name"; then
        log_success "Secret '$name' already exists"
        # Update if value provided
        if [ -n "$value" ] && [ "$value" != "PLACEHOLDER" ]; then
            echo -n "$value" | gcloud secrets versions add "$name" --data-file=- &>/dev/null
            log_info "  └─ New version added"
        fi
    else
        echo -n "$value" | gcloud secrets create "$name" \
            --data-file=- \
            --labels="app=demo-agent" \
            --replication-policy="automatic"
        log_success "Secret '$name' created"
    fi
}

create_secret "db-password" "$DB_PASSWORD" "PostgreSQL database password"
create_secret "clerk-secret-key" "PLACEHOLDER" "Clerk backend API key"
create_secret "clerk-publishable-key" "PLACEHOLDER" "Clerk publishable key"
create_secret "clerk-webhook-secret" "PLACEHOLDER" "Clerk webhook secret"

log_warning "Update Clerk secrets after setup completes!"

# =============================================================================
# STEP 6: Workload Identity Federation (GitHub Actions)
# =============================================================================
log_step "Step 6/7: Workload Identity Federation"

WIF_POOL="github-pool"
WIF_PROVIDER="github-provider"

# Create Workload Identity Pool
if resource_exists wif-pool "$WIF_POOL"; then
    log_success "Pool '$WIF_POOL' already exists"
else
    gcloud iam workload-identity-pools create "$WIF_POOL" \
        --location="global" \
        --description="GitHub Actions authentication pool" \
        --display-name="GitHub Actions"
    log_success "Pool '$WIF_POOL' created"
fi

# Create OIDC Provider
if resource_exists wif-provider "$WIF_PROVIDER" "$WIF_POOL"; then
    log_success "Provider '$WIF_PROVIDER' already exists"
else
    gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" \
        --location="global" \
        --workload-identity-pool="$WIF_POOL" \
        --display-name="GitHub OIDC" \
        --issuer-uri="https://token.actions.githubusercontent.com" \
        --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
        --attribute-condition="assertion.repository=='${GITHUB_REPO}'"
    log_success "Provider '$WIF_PROVIDER' created"
fi

# Allow GitHub repo to impersonate service account
WIF_MEMBER="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPO}"

gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --role="roles/iam.workloadIdentityUser" \
    --member="$WIF_MEMBER" \
    --quiet &>/dev/null
log_success "GitHub repo authorized: $GITHUB_REPO"

WIF_PROVIDER_FULL="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}"

# =============================================================================
# STEP 7: Configure Docker
# =============================================================================
log_step "Step 7/7: Docker Configuration"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
log_success "Docker configured for Artifact Registry"

# =============================================================================
# SAVE OUTPUT
# =============================================================================
cat > "$OUTPUT_FILE" << EOF
# =============================================================================
# GCP Setup Output - Generated $(date)
# =============================================================================
# IMPORTANT: Keep this file secure! Contains sensitive information.
# Add to .gitignore if not already there.
# =============================================================================

# GitHub Actions Secrets (copy these to your repository settings)
# Repository: https://github.com/${GITHUB_REPO}/settings/secrets/actions

GCP_PROJECT_ID=${PROJECT_ID}
GCP_REGION=${REGION}
GCP_SA_EMAIL=${SA_EMAIL}
GCP_WORKLOAD_IDENTITY_PROVIDER=${WIF_PROVIDER_FULL}
CLOUD_SQL_CONNECTION=${CLOUD_SQL_CONNECTION}

# Database (stored in Secret Manager, but saved here for reference)
DB_PASSWORD=${DB_PASSWORD}

# =============================================================================
# Manual Commands to Update Clerk Secrets
# =============================================================================
# Run these commands and paste your actual Clerk keys when prompted:

# echo -n "YOUR_SK_LIVE_KEY" | gcloud secrets versions add clerk-secret-key --data-file=-
# echo -n "YOUR_PK_LIVE_KEY" | gcloud secrets versions add clerk-publishable-key --data-file=-
# echo -n "YOUR_WHSEC_KEY" | gcloud secrets versions add clerk-webhook-secret --data-file=-

EOF

# Add to .gitignore if not present
if ! grep -q ".gcp-setup-output.txt" .gitignore 2>/dev/null; then
    echo "deploy/.gcp-setup-output.txt" >> .gitignore
    log_info "Added output file to .gitignore"
fi

# =============================================================================
# FINAL SUMMARY
# =============================================================================
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    Setup Complete!                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo -e "${CYAN}GitHub Actions Secrets${NC} (add to repository settings):"
echo "────────────────────────────────────────────────────────────────"
echo ""
echo -e "${GREEN}GCP_PROJECT_ID${NC}="
echo "  $PROJECT_ID"
echo ""
echo -e "${GREEN}GCP_REGION${NC}="
echo "  $REGION"
echo ""
echo -e "${GREEN}GCP_SA_EMAIL${NC}="
echo "  $SA_EMAIL"
echo ""
echo -e "${GREEN}GCP_WORKLOAD_IDENTITY_PROVIDER${NC}="
echo "  $WIF_PROVIDER_FULL"
echo ""
echo -e "${GREEN}CLOUD_SQL_CONNECTION${NC}="
echo "  $CLOUD_SQL_CONNECTION"
echo ""
echo "────────────────────────────────────────────────────────────────"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. Add GitHub secrets:"
echo "   https://github.com/${GITHUB_REPO}/settings/secrets/actions"
echo ""
echo "2. Update Clerk secrets (run in terminal):"
echo ""
echo -e "   ${CYAN}# Secret Key${NC}"
echo "   echo -n 'sk_live_YOUR_KEY' | gcloud secrets versions add clerk-secret-key --data-file=-"
echo ""
echo -e "   ${CYAN}# Publishable Key${NC}"
echo "   echo -n 'pk_live_YOUR_KEY' | gcloud secrets versions add clerk-publishable-key --data-file=-"
echo ""
echo "3. Push to main branch to deploy:"
echo "   git add . && git commit -m 'feat: add GCP deployment' && git push"
echo ""
echo -e "${GREEN}Output saved to:${NC} $OUTPUT_FILE"
echo ""
