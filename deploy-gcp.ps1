# ROXY AI Backend — Google Cloud Run Deployment (PowerShell)
# Usage: .\deploy-gcp.ps1 -ProjectId "your-project-id"
#
# One-time setup first:
#   1. gcloud auth login
#   2. gcloud services enable cloudbuild.googleapis.com run.googleapis.com containerregistry.googleapis.com

param(
    [Parameter(Mandatory=$false)]
    [string]$ProjectId
)

$GREEN = "`e[0;32m"
$YELLOW = "`e[1;33m"
$NC = "`e[0m"

Write-Host ""
Write-Host "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}" -NoNewline
Write-Host ""
Write-Host "${GREEN}║         ROXY AI — Google Cloud Run Deployment              ║${NC}" -NoNewline
Write-Host ""
Write-Host "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}" -NoNewline
Write-Host ""
Write-Host ""

# Get project ID if not provided
if ([string]::IsNullOrEmpty($ProjectId)) {
    $ProjectId = (gcloud config get-value project 2>$null)
}

if ([string]::IsNullOrEmpty($ProjectId)) {
    Write-Host "${YELLOW}⚠  No project set. Usage: .\deploy-gcp.ps1 -ProjectId YOUR_PROJECT_ID${NC}"
    Write-Host ""
    Write-Host "Or set your project first:"
    Write-Host "  gcloud config set project YOUR_PROJECT_ID"
    exit 1
}

$Region = "us-central1"
$ServiceName = "roxy-ai-backend"
$Image = "gcr.io/${ProjectId}/${ServiceName}"

Write-Host "${GREEN}✓${NC} Project: ${ProjectId}"
Write-Host "${GREEN}✓${NC} Region:  ${Region}"
Write-Host "${GREEN}✓${NC} Service: ${ServiceName}"
Write-Host ""

# Get commit SHA
$CommitSha = git rev-parse --short HEAD 2>$null
if ([string]::IsNullOrEmpty($CommitSha)) {
    $CommitSha = "local"
}
Write-Host "${GREEN}→${NC} Building image: ${Image}:${CommitSha}"
Write-Host ""

# Enable APIs
Write-Host "${YELLOW}→ Enabling required APIs...${NC}"
gcloud services enable cloudbuild.googleapis.com run.googleapis.com containerregistry.googleapis.com --quiet
Write-Host ""

# Build and push Docker image
Write-Host "${YELLOW}→ Building and pushing Docker image...${NC}"
gcloud builds submit `
  --config=cloudbuild.yaml `
  --substitutions="COMMIT_SHA=${CommitSha},_REGION=${Region}" `
  --quiet

Write-Host ""

# Deploy to Cloud Run
Write-Host "${YELLOW}→ Deploying to Cloud Run...${NC}"
gcloud run deploy $ServiceName `
  --image "${Image}:${CommitSha}" `
  --region $Region `
  --platform managed `
  --memory 2Gi `
  --cpu 2 `
  --min-instances 0 `
  --max-instances 10 `
  --concurrency 80 `
  --timeout 300 `
  --port 8080 `
  --set-env-vars "PYTHONPATH=/app" `
  --allow-unauthenticated `
  --quiet

Write-Host ""
$ServiceUrl = gcloud run services describe $ServiceName --region $Region --format "value(status.url)"
Write-Host "${GREEN}════════════════════════════════════════════════════════════${NC}"
Write-Host "${GREEN}✓ Deployment complete!${NC}"
Write-Host ""
Write-Host "  Service URL: ${ServiceUrl}"
Write-Host "  Health:      ${ServiceUrl}/health"
Write-Host ""
Write-Host "${YELLOW}⚠  Next step: Set your environment variables in Cloud Console:${NC}"
Write-Host "   Cloud Run → ${ServiceName} → Edit → Environment Variables"
Write-Host ""
Write-Host "   Required variables:"
Write-Host "     GEMINI_API_KEY=your_gemini_api_key"
Write-Host "     GROK_API_KEY=your_grok_api_key"
Write-Host "     JWT_SERVICE_SECRET=your_secret"
Write-Host "     JWT_SECRET=your_secret"
Write-Host ""
