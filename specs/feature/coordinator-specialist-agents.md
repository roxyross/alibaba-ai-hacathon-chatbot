# Spec: Coordinator + Specialist Agents

**Branch:** feature/coordinator-specialist-agents
**Status:** Draft
**Date:** 2026-09-01
**Author:** AI (sp.specify)

---

## 1. Problem Statement

ROXY JARVIS needs a Coordinator Agent that can understand a user's request and delegate to the right specialist. Without delegation, a single monolithic agent becomes bloated and slow. The Coordinator ensures requests reach the right specialist (Coding, Research at launch) so users get domain-expert responses rather than generic ones.

## 2. User Stories

- As a user, I want to ask a coding question and get a response from a Coding Agent so that I get expert-level help.
- As a user, I want to ask a research question and get a response from a Research Agent so that I get thorough, cited help.
- As a user, I want to ask a general question and have the Coordinator handle it directly so that I don't need to know which agent exists.
- As a user, I want the agent to explain which specialist handled my request so that I understand the system.
- As a system operator, I want new specialists to be addable without modifying the Coordinator so that the system scales.

## 3. Acceptance Criteria

- [ ] All user requests enter through the Coordinator Agent.
- [ ] Coordinator analyzes the request and routes to the appropriate specialist (Coding or Research) based on intent classification.
- [ ] If no specialist matches, Coordinator handles the request directly.
- [ ] Coordinator and each specialist are separate execution contexts with distinct system prompts.
- [ ] Coding Agent receives coding-related requests; response includes relevant code examples.
- [ ] Research Agent receives research-related requests; response includes information synthesis and sources.
- [ ] Every response is labeled with the handling agent name (e.g., "Coding Agent").
- [ ] Adding a new specialist requires only registering it in the agent registry — no changes to Coordinator routing logic.
- [ ] Each agent call is logged with: user ID, request timestamp, agent name, model used, routing rationale.

## 4. Out of Scope

- Voice input routed to agents (deferred — Voice Agent).
- IoT command routing (deferred — Home/IoT Agent).
- Meeting scheduling (deferred — Meeting Agent).
- Browser automation (deferred — Browser Agent).
- File processing (deferred — Files Agent).
- Study, Finance, Automation, Planner agents — deferred beyond initial two.

## 5. Privacy & Security Considerations

- Agents only receive user content that is relevant to the request (principle of minimal data).
- Agent prompts (system prompts) are not exposed to users.
- Tool calls made by agents are made through the sandboxed tool execution layer.
- All agent actions produce audit log entries.
- High-risk actions (e.g., agent attempts to execute shell commands) require human-in-the-loop confirmation.

## 6. Accessibility Considerations

- Agent attribution is visually distinct and programmatically available to screen readers.
- If an agent takes longer than expected, user receives a loading status update.

## 7. Open Questions / Needs Clarification

- [NEEDS CLARIFICATION: Should Coordinator fall back to a default specialist if intent classification is uncertain, or respond directly?]
- [NEEDS CLARIFICATION: Is there a timeout per agent response, and what should happen if a specialist times out?]

## 8. Hackathon Scope Note

**In scope:** Coordinator Agent with intent routing, Coding Agent, Research Agent, agent registry with pluggable design.  
**Deferred:** Voice, Browser, Files, Study, Finance, Automation, Planner, Home/IoT, Health, Meeting agents.
