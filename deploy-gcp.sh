#!/bin/bash
# ROXY AI Backend — Google Cloud Run Deployment Script
# Usage: ./deploy-gcp.sh [PROJECT_ID]
#
# Prerequisites (one-time setup):
#   1. gcloud auth login
#   2. gcloud config set project YOUR_PROJECT_ID
#   3. gcloud services enable cloudbuild.googleapis.com run.googleapis.com containerregistry.googleapis.com

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ID=${1:-$(gcloud config get-value project 2>/dev/null)}
REGION="us-central1"
SERVICE_NAME="roxy-ai-backend"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         ROXY AI — Google Cloud Run Deployment            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check project
if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" == "" ]; then
    echo -e "${YELLOW}⚠  No project set. Usage: ./deploy-gcp.sh YOUR_PROJECT_ID${NC}"
    echo ""
    echo "Or set your project first:"
    echo "  gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo -e "${GREEN}✓${NC} Project: ${PROJECT_ID}"
echo -e "${GREEN}✓${NC} Region:  ${REGION}"
echo -e "${GREEN}✓${NC} Service: ${SERVICE_NAME}"
echo ""

# Enable APIs
echo -e "${YELLOW}→ Enabling required APIs...${NC}"
gcloud services enable cloudbuild.googleapis.com run.googleapis.com containerregistry.googleapis.com --quiet
echo ""

# Get commit SHA
COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "local")
echo -e "${GREEN}→ Building image: ${IMAGE}:${COMMIT_SHA}${NC}"
echo ""

# Build and push Docker image
echo -e "${YELLOW}→ Building Docker image...${NC}"
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=COMMIT_SHA=${COMMIT_SHA},_REGION=${REGION} \
  --quiet

echo ""

# Deploy to Cloud Run
echo -e "${YELLOW}→ Deploying to Cloud Run...${NC}"
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE}:${COMMIT_SHA} \
  --region ${REGION} \
  --platform managed \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 0 \
  --max-instances 10 \
  --concurrency 80 \
  --timeout 300 \
  --port 8080 \
  --set-env-vars "PYTHONPATH=/app" \
  --allow-unauthenticated \
  --quiet

echo ""
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format "value(status.url)")
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Deployment complete!${NC}"
echo ""
echo -e "  Service URL: ${SERVICE_URL}"
echo -e "  Health:      ${SERVICE_URL}/health"
echo ""
echo -e "${YELLOW}⚠  Next step: Set your environment variables in Cloud Console:${NC}"
echo "   Cloud Run → ${SERVICE_NAME} → Edit → Environment Variables"
echo ""
echo "   Required variables:"
echo "     GEMINI_API_KEY=your_gemini_api_key"
echo "     GROK_API_KEY=your_grok_api_key"
echo "     JWT_SERVICE_SECRET=your_secret"
echo "     JWT_SECRET=your_secret"
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
