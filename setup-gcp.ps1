# ROXY AI Backend — GCP One-Time Setup Script (PowerShell)
# Usage: .\setup-gcp.ps1 -ProjectId "your-project-id"

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectId
)

$GREEN = "`e[0;32m"
$YELLOW = "`e[1;33m"
$NC = "`e[0m"

Write-Host ""
Write-Host "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}" -NoNewline
Write-Host ""
Write-Host "${GREEN}║         GCP Project Setup — ROXY AI Backend              ║${NC}" -NoNewline
Write-Host ""
Write-Host "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}" -NoNewline
Write-Host ""
Write-Host ""

Write-Host "${YELLOW}→${NC} Setting project: ${ProjectId}"
gcloud config set project $ProjectId

Write-Host "${YELLOW}→${NC} Enabling Cloud Build API..."
gcloud services enable cloudbuild.googleapis.com

Write-Host "${YELLOW}→${NC} Enabling Cloud Run API..."
gcloud services enable run.googleapis.com

Write-Host "${YELLOW}→${NC} Enabling Container Registry API..."
gcloud services enable containerregistry.googleapis.com

Write-Host "${YELLOW}→${NC} Configuring Docker authentication..."
gcloud auth configure-docker --quiet

Write-Host ""
Write-Host "${GREEN}════════════════════════════════════════════════════════════${NC}"
Write-Host "${GREEN}✓ GCP Setup Complete!${NC}"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Run: .\deploy-gcp.ps1 -ProjectId ${ProjectId}"
Write-Host "  2. Set environment variables in Cloud Console after deploy"
Write-Host ""
