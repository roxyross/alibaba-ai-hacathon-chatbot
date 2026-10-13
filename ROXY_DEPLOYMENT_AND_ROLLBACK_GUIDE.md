# ROXY-AI Production Deployment & Rollback Guide

**Audience:** Site Reliability Engineers, DevOps, System Administrators  
**Applies To:** Roxy-AI Multi-Platform Production Deployments  
**Release Version:** 2.0.0  
**Verification Status:** Validated & Tested

---

## 1. Architectural Deployment Topology

Roxy-AI operates under a modern decoupled container architecture:
```
[ Client Traffic (Web / Mobile / Desktop) ]
                   │
                   ▼
         [ Cloudflare CDN / WAF ]
                   │
                   ▼
     [ Nginx / Ingress Controller ]
        ├─── /api/v1/*   ──────►  [ FastAPI Backend Service ] (Port 8000)
        │                                  │
        │                                  ├──► [ PostgreSQL 16 + pgvector ] (Port 5432)
        │                                  └──► [ Redis 7 Cache & Queue ]   (Port 6379)
        └─── /*          ──────►  [ Vite Static Web Assets ]  (Nginx Alpine / CDN)
```

---

## 2. Step-by-Step Deployment Procedure

### 2.1 Pre-Flight Deployment Checklist
- [ ] Working tree is clean and checked out to `master`.
- [ ] Submodule status verified (`git submodule status` exits 0).
- [ ] Database schema is up-to-date (`python scripts/validate_migrations.py` confirms single head).
- [ ] Frontend tests pass (`npm run typecheck`, `npm run lint`, `npx vitest run`).
- [ ] Frontend build succeeds (`npm run build`).

### 2.2 Database Migration Execution
Always execute migrations before routing traffic to newly deployed backend containers:
```bash
# 1. Run database backup snapshot
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME -Fc -f "/backups/roxy_predeploy_$(date +%Y%m%d_%H%M%S).dump"

# 2. Execute Alembic migrations
cd backend
alembic upgrade head

# 3. Validate migration head
python scripts/validate_migrations.py
```

### 2.3 Container Build & Rollout (Docker Compose / Kubernetes)
```bash
# Build containers
docker compose -f docker-compose.prod.yml build --no-cache

# Start services with zero-downtime rolling update
docker compose -f docker-compose.prod.yml up -d --remove-orphans

# Verify health probes
curl -f http://localhost:8000/api/v1/health || exit 1
```

### 2.4 Multi-Platform Distribution Build

#### Desktop (Windows, macOS, Linux):
```bash
cd desktop
npm run build
npm run package:all
```
Artifacts output to `desktop/dist/` (`roxy-setup.exe`, `roxy.dmg`, `roxy.AppImage`).

#### Mobile (Android & iOS via Capacitor):
```bash
cd frontend
npm run build
npx cap sync
# Android APK:
cd android && ./gradlew assembleRelease
# iOS Archive:
cd ios && xcodebuild -workspace App.xcworkspace -scheme App -archivePath App.xcarchive archive
```

---

## 3. Production Rollback Runbooks

In the event of an unhandled runtime anomaly, degradation in user experience, or critical failure, initiate rollback procedures immediately.

### 3.1 Scenario A: Frontend Regressions Only
If the defect is isolated to web client assets:
```bash
# 1. Revert Nginx or CDN root to previous stable release bundle
ln -sfn /var/www/roxy/releases/PREVIOUS_STABLE /var/www/roxy/current

# 2. Invalidate CDN cache
cloudflare-cli purge --all

# 3. Reload Nginx
nginx -s reload
```

### 3.2 Scenario B: Backend Service Degradation
If backend API service fails health checks:
```bash
# 1. Revert application container to previous image tag
docker compose -f docker-compose.prod.yml down backend
docker tag roxy-backend:previous roxy-backend:latest
docker compose -f docker-compose.prod.yml up -d backend

# 2. Verify recovery
curl -I http://localhost:8000/api/v1/health
```

### 3.3 Scenario C: Database Schema Reversal
If an Alembic migration introduced a data constraint failure:
```bash
# 1. Determine current revision
cd backend
alembic current

# 2. Rollback single migration step safely
alembic downgrade -1

# 3. If rolling back to a specific target revision:
# alembic downgrade 008_device_agent_enrollment

# 4. In catastrophic corruption cases, restore physical snapshot:
# pg_restore -h $DB_HOST -U $DB_USER -d $DB_NAME --clean "/backups/roxy_predeploy_TIMESTAMP.dump"
```

---

## 4. Post-Rollback Verification

1. Check HTTP response status codes: `curl -I https://roxy.ai/api/v1/health`.
2. Verify WebSocket connectivity: connect test client to `/api/v1/ws`.
3. Inspect `structlog` error volume for anomaly reduction:
   ```bash
   docker logs --tail 200 -f roxy-backend | grep -i error
   ```
4. Verify user authentication and token exchange: perform test login on staging clone.
