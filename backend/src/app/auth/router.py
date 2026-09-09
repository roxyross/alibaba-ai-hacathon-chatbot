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
    """Send a magic link to the given email. Returns dev_token when SMTP is not configured."""
    token = await _service.request_link(str(payload.email).lower().strip())
    smtp_configured = bool(os.environ.get("SMTP_HOST"))
    return RequestLinkResponse(
        ok=True,
        dev_token=token if not smtp_configured else None,
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


@router.get("/oauth/{provider}/start")
async def oauth_start(
    provider: str = Path(..., pattern="^(google|github)$"),
) -> RedirectResponse:
    """Redirect the user to the provider's consent screen.

    Issues a CSRF `state` cookie and 302s. With no client_id configured we
    refuse to redirect — silently falling through would be a security risk.
    """
    if provider not in IMPLEMENTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"OAuth provider '{provider}' is not implemented yet",
        )

    if provider == "google":
        config = oauth_svc.GoogleConfig.from_env()
        if config is None:
            log.error("auth.oauth.start.misconfigured", provider=provider)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Google OAuth is not configured. "
                    "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the backend .env."
                ),
            )
        state = oauth_state.new_state()
        authorize_url = oauth_svc.build_authorize_url(state, config)
        resp = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
        oauth_state.set_state(resp, state)
        log.info("auth.oauth.started", provider=provider)
        return resp

    if provider == "github":
        config = oauth_svc.GitHubConfig.from_env()
        if config is None:
            log.error("auth.oauth.start.misconfigured", provider=provider)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "GitHub OAuth is not configured. "
                    "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET in the backend .env."
                ),
            )
        state = oauth_state.new_state()
        authorize_url = oauth_svc._github_authorize_url(state, config)
        resp = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
        oauth_state.set_state(resp, state)
        log.info("auth.oauth.github.started")
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

    if error:
        log.warning("auth.oauth.provider_error", provider=provider, error=error)
        return _redirect_with_error(provider, error)

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
        config = oauth_svc.GoogleConfig.from_env()
        if config is None:
            # Configuration disappeared mid-flow — treat as misconfiguration.
            log.error("auth.oauth.callback.misconfigured", provider=provider)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google OAuth is not configured",
            )
        try:
            user, jwt_token, ttl = await oauth_svc.complete_google_callback(
                code, config
            )
        except oauth_svc.OAuthError as exc:
            log.warning(
                "auth.oauth.callback.failed",
                provider=provider,
                reason=exc.reason,
            )
            return _redirect_with_error(provider, exc.reason)
        log.info("auth.oauth.callback.success", provider=provider, user_id=user.id)
        return _redirect_with_jwt(jwt_token, ttl)

    if provider == "github":
        config = oauth_svc.GitHubConfig.from_env()
        if config is None:
            log.error("auth.oauth.callback.misconfigured", provider=provider)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GitHub OAuth is not configured",
            )
        try:
            user, jwt_token, ttl = await oauth_svc.complete_github_callback(
                code, config
            )
        except oauth_svc.OAuthError as exc:
            log.warning(
                "auth.oauth.callback.failed",
                provider=provider,
                reason=exc.reason,
            )
            return _redirect_with_error(provider, exc.reason)
        log.info("auth.oauth.callback.success", provider=provider, user_id=user.id)
        return _redirect_with_jwt(jwt_token, ttl)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown provider")


def _redirect_with_jwt(jwt_token: str, ttl: int) -> RedirectResponse:
    """Build the frontend redirect with the JWT in the URL hash.

    Hash (not query) means the token isn't sent in `Referer` headers if the
    user clicks an outbound link on the landing page.
    """
    frontend_base = os.environ.get("APP_BASE_URL", "http://localhost:5173").rstrip("/")
    fragment = urlencode(
        {
            "access_token": jwt_token,
            "token_type": "bearer",
            "expires_in": str(ttl),
        }
    )
    target = f"{frontend_base}/auth/callback#{fragment}"
    resp = RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)
    oauth_state.clear_state(resp)
    return resp


def _redirect_with_error(provider: str, reason: str) -> RedirectResponse:
    """Send the user back to the frontend with a short error reason in the hash."""
    frontend_base = os.environ.get("APP_BASE_URL", "http://localhost:5173").rstrip("/")
    fragment = urlencode({"error": reason, "provider": provider})
    resp = RedirectResponse(
        url=f"{frontend_base}/auth/callback#{fragment}",
        status_code=status.HTTP_302_FOUND,
    )
    oauth_state.clear_state(resp)
    return resp
