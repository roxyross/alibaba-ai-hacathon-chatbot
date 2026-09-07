# Deploy ROXY AI Backend to Google Cloud

This guide deploys your full multi-agent backend (FastAPI + AI gateway + all routers) to **Google Cloud Run**.

## Prerequisites

1. Google Cloud account with billing enabled
2. Google Cloud SDK installed: https://cloud.google.com/sdk/docs/install
3. Project created in Google Cloud Console

## Quick Deploy (One-Time Setup)

```bash
# 1. Authenticate
gcloud auth login
gcloud auth configure-docker

# 2. Set your project
gcloud config set project YOUR_PROJECT_ID

# 3. Enable required APIs
gcloud services enable cloudbuild.googleapis.com run.googleapis.com containerregistry.googleapis.com

# 4. Build and deploy (first time)
cd huggingface-space-roxy-hub
gcloud builds submit --config=../cloudbuild.yaml --substitutions=COMMIT_SHA=$(git rev-parse --short HEAD)

# Or for quick testing (one command):
gcloud run deploy roxy-ai-backend \
  --source ./huggingface-space-roxy-hub \
  --region us-central1 \
  --platform managed \
  --memory 2Gi \
  --cpu 2 \
  --allow-unauthenticated
```

## Set Environment Variables

In Cloud Console > Cloud Run > roxy-ai-backend > Edit & Deploy New Revision > Variables:

```env
# AI Provider Keys (from your Google AI Pro plan)
GEMINI_API_KEY=your_gemini_api_key
GROK_API_KEY=your_grok_api_key

# Optional: Disable DeepSeek/OpenAI if not using
# DEEPSEEK_API_KEY=
# OPENAI_API_KEY=

# JWT Secrets (generate with: openssl rand -hex 32)
JWT_SERVICE_SECRET=your_generated_secret
JWT_SECRET=your_generated_secret

# Database (use Cloud SQL for production)
DATABASE_URL=postgresql+asyncpg://user:pass@/db?host=/cloudsql/PROJECT:REGION:INSTANCE

# Optional: Redis for session caching
REDIS_URL=redis://localhost:6379
```

## Use Vertex AI (Optional — for Google AI Pro integration)

If you want to use Vertex AI instead of direct Gemini API:

```env
# Vertex AI configuration
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
VERTEX_AI_LOCATION=us-central1
MODEL_ID=gemini-1.5-pro
```

Then update the AI adapter to use Vertex AI SDK.

## Verify Deployment

```bash
# Check service status
gcloud run services describe roxy-ai-backend --region us-central1

# Get service URL
gcloud run services describe roxy-ai-backend --region us-central1 --format "value(status.url)"

# Test health endpoint
curl $(gcloud run services describe roxy-ai-backend --region us-central1 --format "value(status.url)")/health
```

Expected response:
```json
{"status": "ok", "service": "ai-gateway"}
```

## Custom Domain (Optional)

```bash
gcloud run domain-mappings create --service roxy-ai-backend --domain api.yourdomain.com
```

## Continuous Deployment

Set up Cloud Build trigger for automatic deployments on git push:

1. Go to Cloud Console > Cloud Build > Triggers
2. Create trigger:
   - Name: `deploy-roxy-backend`
   - Repository: your repo
   - Branch: `master`
   - Config: `cloudbuild.yaml`

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Cloud Run                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              ROXY AI Backend (FastAPI)               │    │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────┐  │    │
│  │  │ Runtime  │ │  Skills  │ │  AI Gateway        │  │    │
│  │  │ Router   │ │ (17)     │ │ ┌────┐┌────┐┌────┐ │  │    │
│  │  │(Coord.)  │ │          │ │ │Gem.││Grok││Deep│ │  │    │
│  │  └──────────┘ └──────────┘ │ └────┘└────┘└────┘ │  │    │
│  │  ┌──────────┐ ┌──────────┐ └────────────────────┘  │    │
│  │  │ Session  │ │  Bank    │                          │    │
│  │  │ History  │ │  (Plaid) │                          │    │
│  │  └──────────┘ └──────────┘                          │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │ Cloud SQL│       │  Vertex  │       │  Gmail   │
    │(optional)│       │   AI     │       │   API    │
    └──────────┘       └──────────┘       └──────────┘
```

## Troubleshooting

**Build fails:**
```bash
gcloud builds log $BUILD_ID
```

**Container doesn't start:**
```bash
gcloud run services describe roxy-ai-backend --region us-central1
# Check Cloud Logging: Cloud Console > Cloud Run > roxy-ai-backend > Logs
```

**Out of memory:**
Increase in `cloudbuild.yaml`:
```yaml
--memory 4Gi
--cpu 4
```

**Cold start too slow:**
Cloud Run scales to 0 by default. Set minimum instances:
```bash
gcloud run services update roxy-ai-backend \
  --region us-central1 \
  --min-instances 1
```
