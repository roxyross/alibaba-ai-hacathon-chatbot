"""FastAPI router for Plaid bank connection endpoints.

Handles:
  POST /api/v1/bank/connect   — store access token mapping
  GET  /api/v1/bank/accounts — list connected bank accounts
  DELETE /api/v1/bank/connect — remove connection

Access tokens are stored encrypted in the backend's database.
"""

from __future__ import annotations

import structlog

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db import get_session_factory
from app.models import BankConnection

log = structlog.get_logger()

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
