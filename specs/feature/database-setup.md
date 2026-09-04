# Spec: Database Setup (Neon PostgreSQL + Prisma)

**Branch:** feature/database-setup
**Status:** Draft
**Date:** 2026-09-01
**Author:** AI (sp.specify)

---

## 1. Problem Statement

ROXY JARVIS requires persistent storage for users, conversations, memories, audit logs, and agent state. Neon PostgreSQL provides a serverless, scalable relational database; Prisma provides type-safe database access. The schema must support all must-ship features while remaining clean enough for future expansion.

## 2. User Stories

- As a developer, I want a Prisma schema that covers all current entities so that I can query data type-safely.
- As a developer, I want database migrations managed by Prisma so that schema changes are reproducible.
- As a developer, I want Redis configured for session caching and queue management so that the app performs well under load.
- As a developer, I want pgvector configured for semantic memory search so that memory queries are fast.
- As a operator, I want the database connection string configurable via environment variable so that secrets are not hardcoded.

## 3. Acceptance Criteria

- [ ] Prisma schema defines: User, Session, Conversation, Message, Memory, AuditLog, AgentConfig entities.
- [ ] Prisma migrations can be run locally and in CI; schema changes are version-controlled.
- [ ] Database connection uses connection pooling (Neon built-in) and environment-variable URL.
- [ ] Redis is configured for caching and queue Pub/Sub; connection URL from environment variable.
- [ ] pgvector extension is enabled; Memory table has vector column for embeddings.
- [ ] All database clients (Prisma, Redis) are instantiated via dependency injection.
- [ ] Health check endpoint verifies database connectivity.
- [ ] No secrets appear in schema files, migration files, or code.

## 4. Out of Scope

- Database backup strategy (handled by Neon managed backups).
- Multi-tenancy schema (future consideration).
- Sharding or partitioning strategies (future).
- Read replica configuration (deferred).

## 5. Privacy & Security Considerations

- Connection strings and credentials are never committed to the repository.
- Database migrations are reviewed before application in production.
- Row-level security policies are defined for multi-user data isolation.
- All PII fields are documented in the schema.

## 6. Accessibility Considerations

- This is a backend infrastructure spec; no direct user-facing accessibility impact.
- Schema documentation should be clear so future developers can maintain it.

## 7. Open Questions / Needs Clarification

- [NEEDS CLARIFICATION: Should Memory embeddings be generated on write (synchronously) or on read (asynchronously)?]
- [NEEDS CLARIFICATION: Is there a max vector dimension we should standardize on (e.g., 1536 for OpenAI ada)?]

## 8. Hackathon Scope Note

**In scope:** Prisma schema with all core entities, migrations, Redis caching/queues, pgvector for semantic search, DI-based clients, environment-variable configuration.  
**Deferred:** Read replicas, multi-tenancy, vector embedding batch jobs.
