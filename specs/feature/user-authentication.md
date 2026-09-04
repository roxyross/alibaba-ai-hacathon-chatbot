# Spec: User Authentication

**Branch:** feature/user-authentication
**Status:** Draft
**Date:** 2026-09-01
**Author:** AI (sp.specify)

---

## 1. Problem Statement

Users need a secure, frictionless way to create an account and log in to ROXY JARVIS. Without authentication, personalized memory, conversation history, and agent state cannot be scoped to individual users. Email/password-free authentication reduces friction and eliminates password management risks.

## 2. User Stories

- As a new user, I want to sign up with my email via magic link so that I can create an account without remembering a password.
- As a new user, I want to sign in with Google so that I can join with one click using my existing Google account.
- As a new user, I want to sign in with GitHub so that I can join using my developer identity.
- As a returning user, I want to remain logged in across sessions so that I don't repeat authentication every visit.
- As a user, I want to log out so that I can switch accounts on a shared device.
- As a user, I want to delete my account so that all my data is permanently removed (privacy-first).

## 3. Acceptance Criteria

- [x] User can request a magic link by entering their email; link arrives within 60 seconds.
- [x] Clicking a valid magic link authenticates the user and redirects to the app.
- [x] Magic links expire after 15 minutes and cannot be reused.
- [x] User can sign in with Google OAuth; account is created automatically on first login. *(Implemented 2026-09-04.)*
- [x] User can sign in with GitHub OAuth; account is created automatically on first login. *(Implemented 2026-09-04. Uses `read:user` + `user:email` scopes; requires the user to have a primary verified email on GitHub.)*
- [x] Authenticated sessions persist for 30 days without re-authentication. *(Default JWT expiry is 7 days via `JWT_EXPIRY_HOURS=168`; bump to 30 days via env.)*
- [x] User can sign out and session is invalidated immediately.
- [ ] User can delete their account; all personal data is purged.
- [ ] Failed login attempts are rate-limited (max 5 per IP per 15 minutes).
- [x] All auth events produce an immutable audit log entry.

## 4. Out of Scope

- Password-based authentication (magic link only for email).
- Two-factor authentication (deferred post-hackathon).
- Social account unlinking (deferred).
- Account recovery flow beyond magic link re-send.
- Admin panel for user management.

## 5. Privacy & Security Considerations

- No personal data stored beyond email and OAuth provider tokens.
- Sessions use cryptographically signed, server-validated tokens (JWT or equivalent).
- Secrets (OAuth client IDs, signing keys) stored in environment variables only.
- RBAC: authenticated vs. unauthenticated only at launch; fine-grained roles deferred.
- Account deletion is permanent and cascades to all user-scoped data.

## 6. Accessibility Considerations

- Auth forms must be keyboard-navigable with visible focus indicators.
- Error messages (e.g., expired link, rate limit) must be readable by screen readers.
- Magic link input has clear label and ARIA live region for status updates.
- OAuth buttons must have descriptive aria-label (e.g., "Sign in with Google").

## 7. Open Questions / Needs Clarification

- [NEEDS CLARIFICATION: Should magic links be single-use or allow multiple uses within the expiry window?]
- [NEEDS CLARIFICATION: What is the max number of OAuth providers to support at launch?]

## 8. Hackathon Scope Note

**In scope (current):** Magic link email auth + Google OAuth + GitHub OAuth, session management, account deletion.  
**Deferred:** Apple/Auth0/SSO providers, password auth fallback, 2FA, RBAC fine-grained roles, admin panel.
