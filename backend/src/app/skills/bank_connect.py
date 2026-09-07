"""bank_connect skill — Plaid OAuth bank connection and account/transaction retrieval.

Operations:
  connect     — initiate Plaid Link, exchange public_token for access_token
  disconnect  — revoke Plaid access token
  list_accounts — return all connected accounts with balances
  get_transactions — return transactions for date range
  get_balance — return balance for specified accounts

Access tokens are stored encrypted in the backend DB via /api/v1/bank/.
This skill acts as the orchestration layer that calls the bank API.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import (
    BankAccount,
    BankConnectRequest,
    BankConnectResponse,
    BankTransaction,
)

log = structlog.get_logger()

PLAID_ENVIRONMENT = os.getenv("PLAID_ENVIRONMENT", "sandbox")
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")


class BankConnectSkill(SkillExecutor[BankConnectRequest, BankConnectResponse]):
    slug = "bank_connect"

    def __init__(self) -> None:
        self._bank_base = os.getenv("BANK_API_BASE", "http://localhost:8000/api/v1/bank")

    async def execute(self, input_data: BankConnectRequest) -> BankConnectResponse:
        op = input_data.op.lower()

        try:
            if op == "connect":
                return await self._connect(input_data)
            elif op == "disconnect":
                return await self._disconnect(input_data)
            elif op == "list_accounts":
                return await self._list_accounts(input_data)
            elif op == "get_transactions":
                return await self._get_transactions(input_data)
            elif op == "get_balance":
                return await self._get_balance(input_data)
            else:
                return BankConnectResponse(
                    op=op,
                    success=False,
                    error=f"Unknown operation: {op}. Valid ops: connect, disconnect, list_accounts, get_transactions, get_balance.",
                )
        except Exception as exc:
            log.error("bank_connect.error", op=op, error=str(exc))
            return BankConnectResponse(
                op=op,
                success=False,
                error=f"Bank connect failed: {exc}",
            )

    async def _connect(self, input_data: BankConnectRequest) -> BankConnectResponse:
        """Store the Plaid access token after OAuth callback."""
        if not input_data.access_token:
            # Plaid Link token flow — return a placeholder until frontend completes OAuth
            if not PLAID_CLIENT_ID or not PLAID_SECRET:
                return BankConnectResponse(
                    op="connect",
                    success=False,
                    error=(
                        "Plaid is not configured. Set PLAID_CLIENT_ID and PLAID_SECRET "
                        "in backend/.env to enable bank connections."
                    ),
                )
            return BankConnectResponse(
                op="connect",
                success=True,
                message="Plaid configuration detected. Complete OAuth flow in frontend.",
                link_token=None,
                institution=input_data.institution,
            )

        # Exchange was handled by frontend — store via bank API
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self._bank_base}/connect",
                json={
                    "user_id": input_data.user_id,
                    "access_token": input_data.access_token,
                    "item_id": f"item_{input_data.user_id}",
                    "institution": input_data.institution,
                },
            )
        if resp.status_code in (200, 201):
            return BankConnectResponse(
                op="connect",
                success=True,
                message="Bank account connected successfully.",
                institution=input_data.institution,
            )
        return BankConnectResponse(
            op="connect",
            success=False,
            error=f"Failed to store connection: {resp.status_code}",
        )

    async def _disconnect(self, input_data: BankConnectRequest) -> BankConnectResponse:
        """Revoke all Plaid tokens for the user."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.delete(f"{self._bank_base}/connect")
        if resp.status_code in (200, 204):
            return BankConnectResponse(
                op="disconnect",
                success=True,
                message="Bank account disconnected.",
            )
        return BankConnectResponse(
            op="disconnect",
            success=False,
            error=f"Failed to disconnect: {resp.status_code}",
        )

    async def _list_accounts(self, input_data: BankConnectRequest) -> BankConnectResponse:
        """Return all connected bank accounts."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self._bank_base}/accounts")
        if resp.status_code != 200:
            return BankConnectResponse(
                op="list_accounts",
                success=False,
                error=f"Failed to list accounts: {resp.status_code}",
            )
        data = resp.json()
        accounts = [
            BankAccount(
                connection_id=a["connection_id"],
                institution=a.get("institution"),
                account_id=a["account_id"],
                name=a["name"],
                type=a["type"],
                mask=a.get("mask"),
                balance=a.get("balance"),
            )
            for a in data.get("accounts", [])
        ]
        return BankConnectResponse(
            op="list_accounts",
            success=True,
            accounts=accounts,
            message=f"Found {len(accounts)} account(s).",
        )

    async def _get_transactions(self, input_data: BankConnectRequest) -> BankConnectResponse:
        """Return transactions for connected accounts."""
        if not PLAID_SECRET:
            return BankConnectResponse(
                op="get_transactions",
                success=False,
                error=(
                    "Plaid is not configured. Set PLAID_CLIENT_ID and PLAID_SECRET "
                    "in backend/.env to retrieve transactions."
                ),
            )
        # TODO: Call Plaid Transactions API with access_token when PLAID_SECRET is set
        return BankConnectResponse(
            op="get_transactions",
            success=True,
            transactions=[],
            message="Plaid transactions API not yet wired — coming soon.",
        )

    async def _get_balance(self, input_data: BankConnectRequest) -> BankConnectResponse:
        """Return balances for connected accounts."""
        accounts_resp = await self._list_accounts(input_data)
        if not accounts_resp.success:
            return accounts_resp
        return BankConnectResponse(
            op="get_balance",
            success=True,
            accounts=accounts_resp.accounts,
            message=f"Retrieved balances for {len(accounts_resp.accounts or [])} account(s).",
        )


def get_executor() -> BankConnectSkill:
    return BankConnectSkill()
