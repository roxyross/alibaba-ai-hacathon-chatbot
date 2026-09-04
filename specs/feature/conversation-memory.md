# Spec: Conversation + Semantic Memory

**Branch:** feature/conversation-memory
**Status:** Draft
**Date:** 2026-09-01
**Author:** AI (sp.specify)

---

## 1. Problem Statement

A personal AI assistant is only useful if it remembers. ROXY JARVIS must store conversation history and extract semantic knowledge that can be recalled in future sessions. Memory must be user-scoped (each user sees only their own data) and deletable (privacy-first).

## 2. User Stories

- As a user, I want my conversation history to persist across sessions so that I can continue previous conversations.
- As a user, I want Jarvis to remember facts about me (e.g., my name, preferences) so that it personalizes responses.
- As a user, I want to search my past conversations by keyword so that I can find something I discussed before.
- As a user, I want to delete specific memories so that I can correct or remove information I no longer want stored.
- As a user, I want to delete all my data so that I can exercise my right to erasure (privacy).
- As a user, I want to export all my data so that I can take my data with me.

## 3. Acceptance Criteria

- [ ] Conversation history persists across browser sessions for authenticated users.
- [ ] User can search past conversations by keyword; results show message text and timestamp.
- [ ] Semantic memory entries are created automatically from conversation context (e.g., "User prefers metric units").
- [ ] User can view a list of all stored semantic memories.
- [ ] User can delete individual semantic memories.
- [ ] User can delete all conversation history in one action.
- [ ] User can export all their data (conversations + memories) as a JSON file.
- [ ] All memory operations are user-scoped — users cannot access other users' data.
- [ ] Memory deletion is permanent (no recovery).
- [ ] Memory operations produce an immutable audit log entry.

## 4. Out of Scope

- Automatic memory decay or aging (future).
- Memory deduplication or merging (future).
- Cross-user shared knowledge bases (explicitly out of scope — privacy violation).
- Memory summarization to reduce token usage (deferred).
- Memory retraining or feedback loop to model selection.

## 5. Privacy & Security Considerations

- All memory data is user-scoped; row-level security enforced at database level.
- Memory deletion is permanent and cascading (deleting user deletes all associated memories).
- Data export includes all user-scoped data in a portable, machine-readable format (JSON).
- Semantic memory extraction uses the same prompt injection protection as regular AI calls.
- No third-party analytics on memory content.

## 6. Accessibility Considerations

- Memory list is navigable by keyboard with proper list semantics.
- Delete buttons have visible focus states and are not purely icon-based (text label + icon).
- Export action has clear confirmation and success feedback.
- Screen reader announces when a memory is deleted.

## 7. Open Questions / Needs Clarification

- [NEEDS CLARIFICATION: How aggressively should semantic memories be extracted? Every significant fact or only explicitly stated preferences?]
- [NEEDS CLARIFICATION: Is there a maximum memory retention period (e.g., 90 days) before auto-archival, or infinite by default?]

## 8. Hackathon Scope Note

**In scope:** Conversation persistence, keyword search, semantic memory extraction (basic), individual deletion, full data export.  
**Deferred:** Memory summarization, memory deduplication, cross-session memory persistence tuning, automatic memory aging.
