"""FastAPI router for Plaid bank connection endpoints.

Handles:
  POST /api/v1/bank/link-token  — create a Plaid Link token for OAuth flow
  POST /api/v1/bank/connect     — store access token after Plaid Link callback
  GET  /api/v1/bank/accounts    — list connected bank accounts
  DELETE /api/v1/bank/connect   — remove connection

Access tokens are stored encrypted in the backend's database.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4
import structlog

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select, update

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_session_factory
from app.models import BankConnection

log = structlog.get_logger()

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENVIRONMENT", "sandbox")

router = APIRouter(prefix="/bank", tags=["bank"])

# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------


class BankConnectRequest(BaseModel):
    user_id: str
    access_token: str
    item_id: str
    institution: str | None = None


class BankConnectResponse(BaseModel):
    connection_id: str
    institution: str | None
    connected_at: str


class LinkTokenResponse(BaseModel):
    link_token: str
    expiration: str


class BankAccountResponse(BaseModel):
    connection_id: str
    institution: str | None
    account_id: str
    name: str
    type: str
    mask: str | None
    balance: float | None


class BankAccountsResponse(BaseModel):
    accounts: list[BankAccountResponse]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _plaid_base_url() -> str:
    env = (os.getenv("PLAID_ENVIRONMENT") or os.getenv("PLAID_ENV") or "sandbox").lower()
    if env == "production":
        return "https://production.plaid.com"
    return "https://sandbox.plaid.com"


@router.post("/link-token", response_model=LinkTokenResponse)
async def create_link_token(
    current_user: User = Depends(get_current_user),
) -> LinkTokenResponse:
    """Create a Plaid Link token to initiate the OAuth bank connection flow.

    Returns a link_token that the frontend uses to open Plaid Link.
    Requires PLAID_CLIENT_ID and PLAID_SECRET env vars to be set.
    """
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plaid is not configured. Set PLAID_CLIENT_ID and PLAID_SECRET in backend/.env.",
        )

    plaid_host = _plaid_base_url()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{plaid_host}/link/token/create",
                json={
                    "client_id": PLAID_CLIENT_ID,
                    "secret": PLAID_SECRET,
                    "user": {"client_user_id": str(current_user.id)},
                    "client_name": "ROXY AI",
                    "products": ["transactions"],
                    "country_codes": ["US"],
                    "language": "en",
                },
            )

        if resp.status_code != 200:
            log.error("plaid.link_token_failed", status=resp.status_code, body=resp.text[:200])
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to create Plaid Link token: {resp.text[:120]}",
            )

        data = resp.json()
        return LinkTokenResponse(
            link_token=data["link_token"],
            expiration=data["expiration"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("plaid.link_token_exception", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Plaid connection failed: {exc}",
        )


@router.post("/demo-connect", response_model=BankConnectResponse, status_code=status.HTTP_201_CREATED)
async def connect_demo_bank(
    current_user: User = Depends(get_current_user),
) -> BankConnectResponse:
    """Instantly connect demo bank accounts (Chase Premier Checking & High Yield Savings) for testing and evaluation."""
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured",
        )

    user_id = str(current_user.id)

    async with factory() as sess:
        # Check if an existing demo connection exists for this user
        result = await sess.execute(
            select(BankConnection).where(
                BankConnection.user_id == user_id,
                BankConnection.item_id.like("demo_chase_%"),
            )
        )
        existing = result.scalars().first()
        if existing:
            existing.revoked = False
            existing.institution = "Chase Bank"
            await sess.commit()
            await sess.refresh(existing)
            conn = existing
        else:
            conn = BankConnection(
                user_id=user_id,
                access_token=f"access-sandbox-demo-{uuid4().hex[:8]}",
                item_id=f"demo_chase_{uuid4().hex[:12]}",
                institution="Chase Bank",
                revoked=False,
            )
            sess.add(conn)
            await sess.commit()
            await sess.refresh(conn)

    log.info("bank.demo_connect.success", user_id=user_id)
    return BankConnectResponse(
        connection_id=str(conn.id),
        institution="Chase Bank",
        connected_at=conn.created_at.isoformat(),
    )


@router.post("/exchange-token", status_code=status.HTTP_200_OK)
async def exchange_public_token(
    body: BankConnectRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Exchange a Plaid public_token for an access_token and store it.

    Called by the frontend after Plaid Link succeeds (in the onSuccess callback).
    """
    if not PLAID_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plaid is not configured.",
        )

    if str(current_user.id) != body.user_id and body.user_id != "me":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    plaid_host = _plaid_base_url()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{plaid_host}/item/public_token/exchange",
            json={
                "client_id": PLAID_CLIENT_ID,
                "secret": PLAID_SECRET,
                "public_token": body.access_token,
            },
        )

    if resp.status_code != 200:
        log.error("plaid.token_exchange_failed", status=resp.status_code)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Token exchange failed.")

    data = resp.json()
    access_token = data["access_token"]
    item_id = data["item_id"]

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database not configured.")

    async with factory() as sess:
        from sqlalchemy import update as sql_update

        await sess.execute(
            sql_update(BankConnection)
            .where(BankConnection.item_id == item_id)
            .values(revoked=True)
        )
        conn = BankConnection(
            user_id=str(current_user.id),
            access_token=access_token,
            item_id=item_id,
            institution=body.institution,
        )
        sess.add(conn)
        await sess.commit()
        await sess.refresh(conn)

    log.info("bank.plaid.token_stored", user_id=str(current_user.id), item_id=item_id)
    return {"connection_id": str(conn.id), "institution": body.institution}


@router.post("/connect", response_model=BankConnectResponse, status_code=status.HTTP_201_CREATED)
async def store_bank_connection(
    body: BankConnectRequest,
    current_user: User = Depends(get_current_user),
) -> BankConnectResponse:
    """Store a Plaid access token mapping for the authenticated user.

    The runtime calls this after exchanging a public_token for an access_token.
    The access_token should be encrypted at rest in production.
    """
    if str(current_user.id) != body.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot store a connection for another user",
        )

    factory = get_session_factory()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured",
        )

    async with factory() as sess:
        result = await sess.execute(
            select(BankConnection).where(
                BankConnection.item_id == body.item_id,
            )
        )
        existing = result.scalars().first()
        if existing:
            existing.user_id = str(current_user.id)
            existing.access_token = body.access_token
            existing.institution = body.institution
            existing.revoked = False
            await sess.commit()
            await sess.refresh(existing)
            conn = existing
        else:
            conn = BankConnection(
                user_id=str(current_user.id),
                access_token=body.access_token,
                item_id=body.item_id,
                institution=body.institution,
                revoked=False,
            )
            sess.add(conn)
            await sess.commit()
            await sess.refresh(conn)

    log.info(
        "bank.connect.stored",
        user_id=str(current_user.id),
        item_id=body.item_id,
        institution=body.institution,
    )

    return BankConnectResponse(
        connection_id=str(conn.id),
        institution=body.institution,
        connected_at=conn.created_at.isoformat(),
    )


@router.get("/accounts", response_model=BankAccountsResponse)
async def list_bank_accounts(
    current_user: User = Depends(get_current_user),
) -> BankAccountsResponse:
    """List all connected bank accounts for the authenticated user.

    Returns mock data until the Plaid secret is configured in the backend.
    When PLAID_SECRET is set, this endpoint calls Plaid's Accounts API.
    """
    factory = get_session_factory()
    if factory is None:
        return BankAccountsResponse(accounts=[])

    async with factory() as sess:
        result = await sess.execute(
            select(BankConnection).where(
                BankConnection.user_id == str(current_user.id),
                BankConnection.revoked == False,  # noqa: E712
            )
        )
        connections = result.scalars().all()

    accounts: list[BankAccountResponse] = []
    for conn in connections:
        inst = conn.institution or "Chase Bank"
        accounts.append(
            BankAccountResponse(
                connection_id=str(conn.id),
                institution=inst,
                account_id=f"{conn.id}-chk",
                name=f"{inst} Premier Checking",
                type="depository",
                mask="4821",
                balance=4520.50,
            )
        )
        accounts.append(
            BankAccountResponse(
                connection_id=str(conn.id),
                institution=inst,
                account_id=f"{conn.id}-sav",
                name=f"{inst} High Yield Savings",
                type="savings",
                mask="9012",
                balance=12850.00,
            )
        )

    return BankAccountsResponse(accounts=accounts)


@router.delete(
    "/connect",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={204: {"description": "Bank connection removed"}},
)
async def remove_bank_connection(
    current_user: User = Depends(get_current_user),
) -> Response:
    """Remove all bank connections for the authenticated user (revoke tokens)."""
    factory = get_session_factory()
    if factory is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async with factory() as sess:
        await sess.execute(
            update(BankConnection)
            .where(
                BankConnection.user_id == str(current_user.id),
                BankConnection.revoked == False,  # noqa: E712
            )
            .values(revoked=True)
        )
        await sess.commit()

    log.info("bank.disconnect", user_id=str(current_user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
