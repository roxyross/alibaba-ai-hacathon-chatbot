"""Auth routes: request-link, verify, me, oauth/{provider}/{start|callback}."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import RedirectResponse

from app.auth import oauth as oauth_svc
from app.auth import oauth_state
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.schemas import (
    RequestLinkRequest,
    RequestLinkResponse,
    SessionResponse,
    UserResponse,
    VerifyTokenRequest,
)
from app.auth.service import MagicLinkService

router = APIRouter(prefix="/auth", tags=["auth"])
_service = MagicLinkService()

log = structlog.get_logger()

# Provider names accepted by the path param. Both are now wired; the
# `IMPLEMENTED` set controls which raise 501 vs run the flow.
SUPPORTED_PROVIDERS = ("google", "github")
IMPLEMENTED_PROVIDERS = ("google", "github")


@router.post("/request-link", response_model=RequestLinkResponse, status_code=status.HTTP_200_OK)
async def request_link(payload: RequestLinkRequest) -> RequestLinkResponse:
    """Send a magic link to the given email. Always returns dev_token/code for instant access so users are never locked out."""
    email_clean = str(payload.email).lower().strip()
    token = await _service.request_link(email_clean)
    return RequestLinkResponse(
        ok=True,
        dev_token=token,
    )


@router.post("/demo", response_model=SessionResponse, status_code=status.HTTP_200_OK)
async def demo_login() -> SessionResponse:
    """Instant login endpoint for demo access, testing, and judges."""
    token = await _service.request_link("demo@roxy.ai")
    result = await _service.verify(token)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize demo session",
        )
    user, jwt_token, ttl = result
    return SessionResponse(
        user=UserResponse.model_validate(user),
        access_token=jwt_token,
        token_type="bearer",
        expires_in=ttl,
    )


@router.post("/verify", response_model=SessionResponse)
async def verify(payload: VerifyTokenRequest) -> SessionResponse:
    """Exchange a magic-link token for a session JWT."""
    result = await _service.verify(payload.token)
    if result is None:
        # Use 400 for "bad token" — clearly distinct from 401 (auth challenge).
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or already-used token",
        )
    user, token, ttl = result
    return SessionResponse(
        user=UserResponse.model_validate(user),
        access_token=token,
        token_type="bearer",
        expires_in=ttl,
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the current authenticated user."""
    return UserResponse.model_validate(current_user)


# ---------------------------------------------------------------------------
# OAuth: GET /auth/oauth/{provider}/start
#       GET /auth/oauth/{provider}/callback
# ---------------------------------------------------------------------------


def _resolve_frontend_base(request: Request | None = None, explicit_origin: str | None = None) -> str:
    """Resolve the frontend base URL dynamically so new users are never redirected to an unreachable localhost."""
    # 1. Explicit origin passed from frontend
    if explicit_origin and (explicit_origin.startswith("http://") or explicit_origin.startswith("https://")):
        return explicit_origin.rstrip("/")

    # 2. Check origin cookie saved during /start
    if request:
        cookie_origin = request.cookies.get(oauth_state.ORIGIN_COOKIE)
        if cookie_origin and (cookie_origin.startswith("http://") or cookie_origin.startswith("https://")):
            return cookie_origin.rstrip("/")
        # Check referer or origin header
        ref = request.headers.get("referer") or request.headers.get("origin")
        if ref:
            from urllib.parse import urlparse
            p = urlparse(ref)
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}".rstrip("/")

    # 3. Check APP_BASE_URL env var if set
    env_base = (os.environ.get("APP_BASE_URL") or "").strip()
    if env_base:
        return env_base.rstrip("/")

    # 4. In production / cloud environments (e.g. Vercel), default to production frontend
    if oauth_state._is_production():
        return "https://roxy-personal-ai.vercel.app"

    # 5. Local development fallback
    return "http://localhost:5173"


@router.get("/oauth/{provider}/start")
async def oauth_start(
    request: Request,
    provider: str = Path(..., pattern="^(google|github)$"),
    origin: str | None = Query(default=None),
) -> RedirectResponse:
    """Redirect the user to the provider's consent screen.

    Issues a CSRF `state` cookie and origin cookie, then 302s.
    """
    if provider not in IMPLEMENTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"OAuth provider '{provider}' is not implemented yet",
        )

    frontend_base = _resolve_frontend_base(request, explicit_origin=origin)

    if provider == "google":
        google_config = oauth_svc.GoogleConfig.from_env()
        if google_config is None:
            log.error("auth.oauth.start.misconfigured", provider=provider)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Google OAuth is not configured. "
                    "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the backend .env."
                ),
            )
        state = oauth_state.new_state()
        authorize_url = oauth_svc.build_authorize_url(state, google_config)
        resp = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
        oauth_state.set_state(resp, state)
        oauth_state.set_origin(resp, frontend_base)
        log.info("auth.oauth.started", provider=provider, frontend_base=frontend_base)
        return resp

    if provider == "github":
        github_config = oauth_svc.GitHubConfig.from_env()
        if github_config is None:
            log.error("auth.oauth.start.misconfigured", provider=provider)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "GitHub OAuth is not configured. "
                    "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in the backend .env."
                ),
            )
        state = oauth_state.new_state()
        authorize_url = oauth_svc._github_authorize_url(state, github_config)
        resp = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
        oauth_state.set_state(resp, state)
        oauth_state.set_origin(resp, frontend_base)
        log.info("auth.oauth.github.started", frontend_base=frontend_base)
        return resp

    # Unreachable given the pattern check, but keeps the type-narrowing honest.
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider")


@router.get("/oauth/{provider}/callback")
async def oauth_callback(
    request: Request,
    provider: str = Path(..., pattern="^(google|github)$"),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Provider redirect target. Exchanges the code, mints a session, and
    302s to the frontend with the JWT in the URL hash.
    """
    if provider not in IMPLEMENTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"OAuth provider '{provider}' is not implemented yet",
        )

    frontend_base = _resolve_frontend_base(request)

    if error:
        log.warning("auth.oauth.provider_error", provider=provider, error=error)
        return _redirect_with_error(provider, error, frontend_base=frontend_base)

    if not code or not state:
        log.warning("auth.oauth.callback.missing_params", provider=provider)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state from provider",
        )

    # Pull the state cookie and compare. consume_state is single-use.
    state_cookie = request.cookies.get(oauth_state.STATE_COOKIE)
    if not oauth_state.consume_state(state, state_cookie):
        log.warning("auth.oauth.callback.bad_state", provider=provider)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state",
        )

    if provider == "google":
        google_config = oauth_svc.GoogleConfig.from_env()
        if google_config is None:
            # Configuration disappeared mid-flow — treat as misconfiguration.
            log.error("auth.oauth.callback.misconfigured", provider=provider)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google OAuth is not configured",
            )
        try:
            user, jwt_token, ttl = await oauth_svc.complete_google_callback(
                code, google_config
            )
        except oauth_svc.OAuthError as exc:
            log.warning(
                "auth.oauth.callback.failed",
                provider=provider,
                reason=exc.reason,
            )
            return _redirect_with_error(provider, exc.reason, frontend_base=frontend_base)
        log.info("auth.oauth.callback.success", provider=provider, user_id=user.id)
        return _redirect_with_jwt(jwt_token, ttl, frontend_base=frontend_base)

    if provider == "github":
        github_config = oauth_svc.GitHubConfig.from_env()
        if github_config is None:
            log.error("auth.oauth.callback.misconfigured", provider=provider)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GitHub OAuth is not configured",
            )
        try:
            user, jwt_token, ttl = await oauth_svc.complete_github_callback(
                code, github_config
            )
        except oauth_svc.OAuthError as exc:
            log.warning(
                "auth.oauth.callback.failed",
                provider=provider,
                reason=exc.reason,
            )
            return _redirect_with_error(provider, exc.reason, frontend_base=frontend_base)
        log.info("auth.oauth.callback.success", provider=provider, user_id=user.id)
        return _redirect_with_jwt(jwt_token, ttl, frontend_base=frontend_base)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider")


def _redirect_with_jwt(jwt_token: str, ttl: int, frontend_base: str | None = None) -> RedirectResponse:
    """Build the frontend redirect with the JWT in the URL hash.

    Hash (not query) means the token isn't sent in `Referer` headers if the
    user clicks an outbound link on the landing page.
    """
    base = (frontend_base or _resolve_frontend_base()).rstrip("/")
    fragment = urlencode(
        {
            "access_token": jwt_token,
            "token_type": "bearer",
            "expires_in": str(ttl),
        }
    )
    target = f"{base}/auth/callback#{fragment}"
    resp = RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
    oauth_state.clear_state(resp)
    return resp


def _redirect_with_error(provider: str, reason: str, frontend_base: str | None = None) -> RedirectResponse:
    """Send the user back to the frontend with a short error reason in the hash."""
    base = (frontend_base or _resolve_frontend_base()).rstrip("/")
    fragment = urlencode({"error": reason, "provider": provider})
    resp = RedirectResponse(
        url=f"{base}/auth/callback#{fragment}",
        status_code=status.HTTP_302_FOUND,
    )
    oauth_state.clear_state(resp)
    return resp
