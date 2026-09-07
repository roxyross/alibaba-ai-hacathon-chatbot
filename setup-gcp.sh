#!/bin/bash
# ROXY AI Backend — GCP One-Time Setup Script
# Run this once to configure your Google Cloud project
#
# Usage: ./setup-gcp.sh YOUR_PROJECT_ID

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_ID=$1

if [ -z "$PROJECT_ID" ]; then
    echo -e "${YELLOW}⚠  Usage: ./setup-gcp.sh YOUR_PROJECT_ID${NC}"
    exit 1
fi

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         GCP Project Setup — ROXY AI Backend             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Set project
echo -e "${YELLOW}→ Setting project: ${PROJECT_ID}${NC}"
gcloud config set project ${PROJECT_ID}

# Enable APIs
echo -e "${YELLOW}→ Enabling Cloud Build API...${NC}"
gcloud services enable cloudbuild.googleapis.com

echo -e "${YELLOW}→ Enabling Cloud Run API...${NC}"
gcloud services enable run.googleapis.com

echo -e "${YELLOW}→ Enabling Container Registry API...${NC}"
gcloud services enable containerregistry.googleapis.com

# Configure docker
echo -e "${YELLOW}→ Configuring Docker authentication...${NC}"
gcloud auth configure-docker --quiet

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ GCP Setup Complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Run: ./deploy-gcp.sh ${PROJECT_ID}"
echo "  2. Set environment variables in Cloud Console after deploy"
echo ""
echo "Or do it all at once:"
echo "  ./deploy-gcp.sh ${PROJECT_ID}"
echo ""
