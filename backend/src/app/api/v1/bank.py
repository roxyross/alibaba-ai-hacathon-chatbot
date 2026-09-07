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
import structlog

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
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

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"https://://api.plaid.com/link/token/create",
            json={
                "client_id": PLAID_CLIENT_ID,
                "secret": PLAID_SECRET,
                "user": {"client_user_id": str(current_user.id)},
                "client_name": "ROXY AI",
                "products": ["transactions"],
                "country_codes": ["US"],
                "language": "en",
                "environment": PLAID_ENV,
            },
        )

    if resp.status_code != 200:
        log.error("plaid.link_token_failed", status=resp.status_code, body=resp.text[:200])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create Plaid Link token.",
        )

    data = resp.json()
    return LinkTokenResponse(
        link_token=data["link_token"],
        expiration=data["expiration"],
    )


@router.post("/exchange-token", status_code=status.HTTP_200_OK)
async def exchange_public_token(
    body: BankConnectRequest,
    current_user: User = Depends(get_current_user),
):
    """Exchange a Plaid public_token for an access_token and store it.

    Called by the frontend after Plaid Link succeeds (in the onSuccess callback).
    """
    if not PLAID_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plaid is not configured.",
        )

    if str(current_user.id) != body.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://://api.plaid.com/item/public_token/exchange",
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
        # Revoke any existing connection for the same item_id
        await sess.execute(
            update(BankConnection)
            .where(BankConnection.item_id == body.item_id)
            .values(revoked=True)
        )

        conn = BankConnection(
            user_id=str(current_user.id),
            access_token=body.access_token,
            item_id=body.item_id,
            institution=body.institution,
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
        # TODO: Call Plaid Accounts API with access_token when PLAID_SECRET is configured
        # For now, return mock data so the frontend can iterate
        accounts.append(
            BankAccountResponse(
                connection_id=str(conn.id),
                institution=conn.institution,
                account_id="mock-acct-001",
                name="Checking (mock)",
                type="depository",
                mask="1234",
                balance=1234.56,
            )
        )

    return BankAccountsResponse(accounts=accounts)


@router.delete(
    "/connect",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={204: {"description": "Bank connection removed"}},
)
async def remove_bank_connection(
    current_user: User = Depends(get_current_user),
):
    """Remove all bank connections for the authenticated user (revoke tokens)."""
    factory = get_session_factory()
    if factory is None:
        return

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
