# Spec: Docker Compose Local Setup

**Branch:** feature/docker-compose
**Status:** Draft
**Date:** 2026-09-01
**Author:** AI (sp.specify)

---

## 1. Problem Statement

Every developer on the team must be able to run the full ROXY JARVIS stack locally with a single command. Without Docker Compose parity between local and staging, developers waste time on environment-specific bugs that don't reproduce in CI or staging.

## 2. User Stories

- As a new developer, I want to run `docker compose up` and have the full app running so that I can start developing in under 10 minutes.
- As a developer, I want my local environment to match staging so that bugs I find locally reproduce in CI.
- As a developer, I want hot reload enabled so that code changes are reflected without rebuilding containers.
- As a developer, I want seeded development data so that I can test without manually creating test users and conversations.
- As a developer, I want all services logs visible in one terminal so that I can debug end-to-end flows.

## 3. Acceptance Criteria

- [ ] `docker compose up` starts all services: Next.js frontend, FastAPI backend, PostgreSQL (Neon-compatible), Redis, pgvector.
- [ ] Frontend is accessible at http://localhost:3000 with hot reload.
- [ ] Backend is accessible at http://localhost:8000 with auto-reload.
- [ ] Database migrations run automatically on backend startup (with health check gate).
- [ ] `.env.example` is committed; all required env vars are documented with placeholder values.
- [ ] No real secrets (API keys, database URLs) are in the repository; `.env` is gitignored.
- [ ] `docker compose down` cleanly stops and removes all containers, networks, and volumes.
- [ ] `docker compose logs` shows combined output from all services.
- [ ] README section "Getting Started" allows a new developer to run the project in under 10 minutes.

## 4. Out of Scope

- Kubernetes deployment manifests (deferred — handled by cloud provider).
- Production-grade Docker optimizations (multi-stage builds, layer caching for prod).
- Docker Scout or security scanning in CI (future).
- Local HTTPS/TLS termination (deferred).

## 5. Privacy & Security Considerations

- No secrets are baked into Docker images (use docker-compose override or env files).
- Development data is clearly separated from production data; no cross-contamination risk.
- Ports are exposed on localhost only by default (127.0.0.1 in docker-compose.yml).

## 6. Accessibility Considerations

- This is a developer tooling spec; no direct user-facing accessibility impact.

## 7. Open Questions / Needs Clarification

- [NEEDS CLARIFICATION: Should pgvector run as part of the PostgreSQL container (pgvector extension) or as a separate Qdrant container?]
- [NEEDS CLARIFICATION: Should there be a `seed` target to populate dev data, or is an init container sufficient?]

## 8. Hackathon Scope Note

**In scope:** Full Docker Compose stack, hot reload, env var documentation, README getting started guide.  
**Deferred:** Kubernetes manifests, production optimizations, security scanning.
