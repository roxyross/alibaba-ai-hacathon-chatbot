# Spec: Minimal Audit Log

**Branch:** feature/audit-log
**Status:** Draft
**Date:** 2026-09-01
**Author:** AI (sp.specify)

---

## 1. Problem Statement

ROXY JARVIS performs actions on behalf of users — auth events, AI requests, memory operations, and agent tool calls. When something goes wrong, or when users want to understand what the system did, there must be an immutable, queryable record. An audit log is also required for compliance and for the "What did Jarvis do today" user-facing view.

## 2. User Stories

- As a user, I want to see a history of what Jarvis did today so that I can review its actions.
- As a user, I want to know which AI model handled my request so that I can evaluate the response.
- As a user, I want to see what data was accessed by Jarvis so that I maintain trust.
- As an operator, I want to query audit logs by user, date, and action type so that I can investigate incidents.
- As an operator, I want audit log entries to be immutable so that they cannot be altered to cover tracks.

## 3. Acceptance Criteria

- [ ] Every authenticated action (login, logout, message sent, memory created/deleted, agent invoked) creates an audit log entry.
- [ ] Audit log entries are stored in an append-only table (no UPDATE or DELETE permissions at app level).
- [ ] Each entry contains: timestamp (UTC), user ID, action type, agent name, model used, request metadata.
- [ ] Entries are queryable by user ID, date range, and action type.
- [ ] "What did Jarvis do today" view shows the current user's audit entries for today in reverse chronological order.
- [ ] User can export their own audit log as JSON.
- [ ] Audit logs are not modifiable or deletable by the user (immutable by design).
- [ ] Audit logs for all users are visible to operators (role: admin) for incident investigation.

## 4. Out of Scope

- Real-time audit log streaming to a SIEM (deferred).
- Audit log aggregation or trend visualization (deferred — "What did Jarvis do today" is the simple view).
- Audit log retention policy automation (manual purge after X years — future).
- Audit log compression or archival (future).

## 5. Privacy & Security Considerations

- Users can only view their own audit log entries (row-level security enforced).
- Operators with admin role can view all audit logs for incident investigation.
- Audit log entries do not contain the full prompt/response content (only action metadata).
- Audit log access is itself audited.

## 6. Accessibility Considerations

- "What did Jarvis do today" list is keyboard navigable and screen-reader accessible.
- Timestamps are shown in user's local timezone with UTC available on hover/focus.
- Action types use clear, human-readable labels (e.g., "Signed in with Google" not "OAUTH_GOOGLE_SUCCESS").

## 7. Open Questions / Needs Clarification

- [NEEDS CLARIFICATION: Should the user-facing "What did Jarvis do today" show ALL action types or a filtered subset (e.g., exclude heartbeat/health checks)?]
- [NEEDS CLARIFICATION: What is the retention period for audit logs before archival or deletion?]

## 8. Hackathon Scope Note

**In scope:** Append-only audit log table, all authenticated actions logged, user-facing "today" view, user export, operator query.  
**Deferred:** SIEM integration, retention automation, audit trend analytics.
