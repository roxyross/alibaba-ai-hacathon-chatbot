# ADR-002: OAuth Identity Provider Integration

> **Scope**: This is a decision *cluster* covering how ROXY JARVIS integrates third-party identity providers (Google today, GitHub and others later) alongside the existing email magic-link flow. The cluster groups the flow choice, the CSRF/state model, the token handoff, the account-linking rule, and the multi-provider extension pattern — they all evolve together.

- **Status:** Accepted
- **Date:** 2026-09-04
- **Feature:** `user-authentication` (specs/feature/user-authentication.md)
- **Context:** `specs/feature/user-authentication.md` (status: Draft) lists Google OAuth and GitHub OAuth as in-scope acceptance criteria, but until 2026-09-04 only the email magic-link path was implemented. Users who prefer a one-click sign-in — and don't want to check email on every session — had no alternative. Implementing OAuth is a cross-cutting change that adds a new identity surface (Google's `sub` + email), a new external trust boundary (Google's JWKS), a new env-var contract (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `OAUTH_REDIRECT_BASE_URL`), and a new security primitive (CSRF state cookie). Decisions in this cluster were made together because each constrains the others: changing the flow (e.g. PKCE) forces the handoff to change; changing the linking rule (e.g. per-`sub` accounts) changes schema; changing the handoff (e.g. JSON response) breaks the state model.

<!-- Significance checklist — ALL true:
     1) Impact: long-term consequence for auth architecture, security posture, and future provider additions. YES
     2) Alternatives: multiple viable options (Authorization Code vs PKCE vs Implicit; URL-hash handoff vs JSON; link-by-email vs link-by-sub). YES
     3) Scope: cross-cutting across backend (router, service, security, env), frontend (auth gate, context, routing), and ops (Google Cloud Console setup, env config). YES
     → Justified as an ADR (not a PHR note). -->

## Decision

**Cluster: OAuth identity-provider integration.**

- **Flow:** OAuth 2.0 **Authorization Code** (server-side). The backend holds the `client_secret`; the browser never sees it. No PKCE — the `client_secret` already authenticates the backend to Google, and adding PKCE on top would be cargo-culted defense with no marginal security benefit in our threat model (the backend is the only confidential client).
- **CSRF defense:** Server-issued opaque `state` value, delivered to the browser as an `HttpOnly`, `SameSite=Lax`, single-use cookie scoped to `/api/v1/auth`. Cookie TTL: 10 minutes. `consume_state` deletes the value on read so a replay is impossible.
- **Token handoff:** Backend → 302 → `${APP_BASE_URL}/auth/callback#access_token=…&expires_in=…&token_type=bearer`. The session JWT lives in the **URL fragment** (hash), not the query string, so it is never sent in `Referer` headers or server access logs. The frontend's `AuthGate` deep-link `useEffect` parses the hash, calls `completeOAuth` (which validates via `/auth/me` and stores the token in `localStorage`), then `history.replaceState`s to strip the hash.
- **Identity verification:** Google's RS256 id_token is verified against Google's JWKS (cached in-process for 5 minutes; `kid` miss forces a refetch). Required claims: `iss ∈ {https://accounts.google.com, accounts.google.com}`, `aud == GOOGLE_CLIENT_ID`, `exp` (with 60 s leeway), `iat`, `sub`, `email`. `email_verified` **must** be `true`; otherwise we 302 the user back to the frontend with `#error=email_unverified`. We do not persist Google's `sub`, `name`, or `picture` in v1.
- **Account linking:** Auto-link by verified email. After id_token verification, look up `User.email`; if a user exists, reuse it; otherwise create one. This makes Google's email and the magic-link email land on the same `users` row, so a user who starts with magic-link can later use Google (or vice-versa) without losing their session/history.
- **Session token format:** HS256 JWT (existing `create_session_token` in `app/auth/jwt.py`). OAuth and magic-link produce **indistinguishable** session tokens, so `get_current_user` (which only validates the JWT) works for both without change.
- **Multi-provider extension:** `provider` is a `Path(..., regex="^(google|github)$")` param. The router dispatches to a per-provider config; `IMPLEMENTED_PROVIDERS = ("google",)` today, `github` returns `501`. Adding GitHub is a config + handler, not a refactor.
- **Audit log events:** `auth.oauth.started`, `auth.oauth.callback.received`, `auth.oauth.exchange_failed`, `auth.oauth.callback.bad_state`, `auth.oauth.callback.failed`, `auth.oauth.email_not_allowed`, `auth.oauth.signed_in`. Reuses the structlog setup in `main.py`.
- **No-creds fail-closed:** If `GOOGLE_CLIENT_ID`/`SECRET` are unset, `GET /api/v1/auth/oauth/google/start` returns `503 Google OAuth is not configured` — never a silent 302 to a provider we can't talk to.
- **Storage parity:** OAuth follows the magic-link pattern — `users` and session state work via SQLAlchemy when `DATABASE_URL` is set, and via module-level in-memory dicts in dev/tests. No new tables; `users` is the only persistence.

## Consequences

### Positive

- **Provider neutrality at the session layer:** the frontend `AuthContext` doesn't know or care whether the session came from Google or magic-link. Switching providers, adding a third, or returning to email-only is a backend-only change.
- **Defense in depth on CSRF:** `state` cookie is `HttpOnly` (JS can't read), `SameSite=Lax` (works for top-level OAuth navigations), single-use (replay returns 400), and short-lived (10 min).
- **No new PII:** we store only `email` (already collected for magic-link). Google's `sub`, `name`, `picture` are discarded after the JWT verifies.
- **Account continuity:** the link-by-email rule means existing magic-link users can adopt OAuth without admin help. New users get one-click sign-in. No "which email did I use?" friction.
- **Fail-closed by default:** the 503-when-unconfigured behavior makes it obvious in dev that OAuth needs real keys; we don't ship a "dev mode" that signs fake tokens.
- **Multi-provider scaffolding is cheap:** the GitHub path is registered, the dispatcher is provider-keyed, and the existing CSRF/upsert/JWT machinery is provider-agnostic. Adding GitHub is a config + handler pair.

### Negative

- **One OAuth round-trip per new device:** users who bounce between devices more often than they check email get a slower UX than the magic-link flow (extra Google redirect).
- **Vendor lock-in to Google's identity surface:** switching primary providers (e.g. Apple Sign-In, Auth0) requires another `ProviderConfig` and probably a small schema migration if we want to persist `sub` for unlink UX. The current "email only" storage is a deliberate trade for v1 simplicity.
- **JWKS rotation window:** the 5-minute in-process JWKS cache means a Google key rotation longer than 5 minutes (rare but real) can produce a brief failure window until the cache expires. `kid`-cache-miss refetch covers the common case.
- **CORS still `allow_origins=["*"]`:** the OAuth callback is a server-side redirect, so it isn't affected, but the rest of the API is. This is a pre-existing concern from the magic-link era; not regressed by this change.
- **Per-`sub` linking is deferred:** if a user has a Google account with one email and later gets a Google account with a different email, they end up with two `users` rows. The spec already notes "Social account unlinking (deferred)"; this ADR inherits that trade-off.
- **No PKCE:** acceptable because the backend is the only confidential client, but if a future feature exposes a public/mobile client, PKCE must be added — a follow-up ADR will be needed.
- **In-memory `state` is per-process:** if the backend restarts mid-flow, the user's `/start` cookie becomes invalid. Acceptable for hackathon; a sticky Redis store would be the prod answer.

## Alternatives Considered

- **Alternative A — Authorization Code with PKCE:** industry-recommended for any client that can't safely hold a secret, including SPAs. *Rejected* because we are not a public client — the FastAPI backend holds `GOOGLE_CLIENT_SECRET`. PKCE on top adds key generation, storage, and verification for no incremental security in our threat model. Reconsider only if a public/mobile client is added.
- **Alternative B — Implicit flow / token-in-fragment direct from Google:** the legacy Google-recommended path for SPAs. *Rejected*: deprecated by Google (deprecated 2020, removed for new apps 2023), exposes access tokens to the browser unnecessarily, and offers no advantage over the hash-handoff of an Authorization-Code-issued JWT.
- **Alternative C — Backend returns JSON `{access_token, user}` from a popup:** frontend opens the OAuth flow in a popup, polls a backend endpoint for the result. *Rejected*: more UX complexity (popup blockers, focus management), more client code (a polling state machine), and the token still has to be stored somewhere — typically `localStorage`, which we already do. The hash-handoff achieves the same final state with one less moving piece.
- **Alternative D — Link accounts by Google's `sub` instead of email:** each Google identity gets a fresh `users` row. *Rejected* as the v1 default: it produces orphan magic-link accounts once a user moves to Google, and the email is already verified by Google, so link-by-email is strictly more useful. Per-`sub` storage is a future enhancement (e.g. for explicit unlink), not a replacement.
- **Alternative E — Use an OIDC identity library (Authlib, oauthlib) instead of hand-rolled `httpx` + `pyjwt`:** *Considered.* Authlib would give us discovery, JWKS rotation, and PKCE out of the box. *Deferred*: for a single provider with a fixed JWKS URL and one supported flow, the hand-rolled implementation is ~150 lines and removes a heavy dependency. Revisit when a second OIDC provider is added (GitHub is OAuth 2.0 but not OIDC, so it wouldn't drive this), or when JWKS rotation becomes operationally painful.
- **Alternative F — Store the OAuth `sub` in a new `oauth_identities` table now:** *Considered for v1, rejected.* It's the right shape for "list my connected providers" and unlink UX, but the spec defers both, and adding a table we won't query for the hackathon is dead weight. The plan calls this out as a follow-up.

## References

- Feature spec: `specs/feature/user-authentication.md` (AC §3, Scope §8).
- Implementation plan: `.claude/plans/merry-hugging-creek.md` (the plan-mode file backing this work).
- Backend code: `backend/src/app/auth/oauth.py` (provider config + JWKS verification), `backend/src/app/auth/oauth_state.py` (CSRF state cookie), `backend/src/app/auth/router.py` (`/auth/oauth/{provider}/{start,callback}`), `backend/src/app/auth/service.py` (user upsert parity), `backend/src/app/auth/jwt.py:25` (session token issuer), `backend/src/app/auth/dependencies.py:21` (consumer, unchanged).
- Frontend code: `frontend/src/auth/AuthGate.tsx` (button + deep-link hash parser), `frontend/src/auth/AuthContext.tsx` (`completeOAuth`), `frontend/src/auth/api.ts` (`getOAuthStartUrl`).
- Tests: `backend/tests/integration/test_oauth_google.py` (9 cases; happy path, missing/bad `state`, `?error=` from provider, `email_verified: false` rejection, account linking, single-use state).
- Env contract: `backend/.env.example` — `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `OAUTH_REDIRECT_BASE_URL`, `GOOGLE_ALLOWED_EMAILS`.
- Docs: `backend/README.md` (`## Authentication` section with the flow diagram and Google Cloud Console steps).
- Related ADRs: `history/adr/ADR-001-implementation-stack-reconciliation.md` (platform stack; no conflict — ADR-001 covers Vite/React/SQLAlchemy; this ADR covers auth).
- Follow-ups: GitHub OAuth (drop-in second provider, not a new ADR); Authlib migration (Alternative E) if a second OIDC provider lands; per-`sub` storage in `oauth_identities` if unlink UX ships; per-process `state` → Redis for multi-instance prod.

## Addendum: GitHub OAuth (2026-09-04)

GitHub OAuth was implemented under the **Multi-provider extension** decision above, as anticipated by the "Follow-ups" line. No new ADR was created — by design and per the project decision (the architectural choice is the dispatcher pattern; GitHub is a slot in it). Concretely:

- `oauth.py` gained `GitHubConfig`, `_github_authorize_url`, `_github_exchange_code`, `_github_fetch_verified_primary_email`, and `complete_github_callback`. No JWKS — GitHub's `/user/emails` is the source of truth for verified primary email; we require `primary && verified` ourselves.
- `router.py` added the `github` branch to `oauth_start` and `oauth_callback`, and refactored the JWT-in-hash 302 into a shared `_redirect_with_jwt` helper.
- Frontend: `AuthGate.tsx` got a second button using an inline GitHub mark; the `getOAuthStartUrl` helper was already provider-typed.
- Tests: `backend/tests/integration/test_oauth_github.py` (8 cases) — happy path, bad `state`, `?error=` from GitHub, unverified primary, empty emails list, account linking by email, single-use state.
- `backend/tests/integration/test_oauth_google.py::test_github_provider_returns_501` was updated to assert GitHub now 302s (in-cluster behavior).
- Env: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_ALLOWED_EMAILS` added to `.env.example`; `OAUTH_REDIRECT_BASE_URL` is shared with Google.
