"""bank_connect skill — Plaid OAuth bank account connection and data retrieval.

Sensitive: requires explicit user confirmation before connecting a new institution.
Implements the Plaid Link OAuth 2.0 flow. Access tokens are stored in the
backend's encrypted token store (never in the runtime).

Operations:
  - connect    → initiate Plaid Link, return link_token
  - exchange   → exchange public_token for access_token
  - list_accounts  → return all accounts with balances
  - get_transactions → return categorized transactions for date range
  - get_balance    → return current balance for accounts
  - disconnect → revoke the Plaid access token

Requires: PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENVIRONMENT in runtime .env
"""

from __future__ import annotations

import structlog

import httpx

from runtime.config import settings
from runtime.skills.executor import SkillResult

log = structlog.get_logger()

_PLAID_BASE = "https://{environment}.plaid.com"
_TOKEN_EXCHANGE_URL = "https://{environment}.plaid.com/item/exchange_token"
_ACCOUNTS_URL = "https://{environment}.plaid.com/accounts/get"
_TRANSACTIONS_URL = "https://{environment}.plaid.com/transactions/get"
_BALANCE_URL = "https://{environment}.plaid.com/accounts/balance/get"
_REMOVE_URL = "https://{environment}.plaid.com/item/remove"
_LINK_URL = "https://{environment}.plaid.com/link/token/create"

# Plaid environments: sandbox, development, production
_PLAID_ENVIRONMENTS = {"sandbox", "development", "production"}


def _plaid_env() -> str:
    return getattr(settings, "plaid_environment", "sandbox")


def _plaid_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "PLAID-CLIENT-ID": settings.plaid_client_id or "",
        "PLAID-SECRET": settings.plaid_secret or "",
    }


def _available() -> bool:
    return bool(settings.plaid_client_id and settings.plaid_secret)


async def bank_connect(
    op: str,
    institution: str | None = None,
    access_token: str | None = None,
    public_token: str | None = None,
    account_ids: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    user_id: str,
) -> SkillResult:
    """Connect to and query bank accounts via Plaid.

    Args:
        op: One of: connect, exchange, list_accounts, get_transactions, get_balance, disconnect
        institution: Bank name (for logging only)
        access_token: Plaid access token (for authenticated operations)
        public_token: Plaid public token from Link callback (for exchange operation)
        account_ids: Optional list of account IDs to filter by
        start_date: Start date for transactions (YYYY-MM-DD)
        end_date: End date for transactions (YYYY-MM-DD)
        user_id: For audit logging

    Returns:
        SkillResult with bank data or confirmation/error
    """
    log.info("bank_connect.invoked", user_id=user_id, op=op, institution=institution)

    if op not in ("connect", "exchange", "list_accounts", "get_transactions", "get_balance", "disconnect"):
        return SkillResult(
            ok=False, data=None,
            error=f"Invalid op '{op}'. Must be one of: connect, exchange, list_accounts, get_transactions, get_balance, disconnect"
        )

    # ---- Plaid not configured ------------------------------------------------
    if not _available():
        return SkillResult(
            ok=True,
            data={
                "op": op,
                "configured": False,
                "message": (
                    "Bank Connect is not configured. "
                    "Set PLAID_CLIENT_ID and PLAID_SECRET in your runtime .env file. "
                    "Sign up at https://dashboard.plaid.com"
                ),
                "institutions": [],
            },
            warning="Bank Connect is not configured. Set PLAID_CLIENT_ID and PLAID_SECRET in runtime/.env",
        )

    env = _plaid_env()
    base_url = _PLAID_BASE.format(environment=env)

    # ---- connect: create link token -----------------------------------------
    if op == "connect":
        try:
            payload = {
                "user": {"client_user_id": user_id},
                "client_name": "ROXY AI",
                "products": ["transactions"],
                "country_codes": ["US"],
                "language": "en",
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    _LINK_URL.format(environment=env),
                    json=payload,
                    headers=_plaid_headers(),
                )
            if resp.is_success:
                data = resp.json()
                return SkillResult(
                    ok=True,
                    data={
                        "op": "connect",
                        "configured": True,
                        "link_token": data.get("link_token"),
                        "expiration": data.get("expiration"),
                        "request_id": data.get("request_id"),
                    },
                )
            return SkillResult(
                ok=False, data=None,
                error=f"Plaid link token creation failed: {resp.status_code} {resp.text[:200]}"
            )
        except httpx.HTTPError as exc:
            return SkillResult(
                ok=False, data=None,
                error=f"Failed to reach Plaid API: {exc}"
            )

    # ---- exchange: public_token → access_token -------------------------------
    if op == "exchange":
        if not public_token:
            return SkillResult(ok=False, data=None, error="public_token is required for exchange operation")
        try:
            payload = {"public_token": public_token}
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    _TOKEN_EXCHANGE_URL.format(environment=env),
                    json=payload,
                    headers=_plaid_headers(),
                )
            if resp.is_success:
                data = resp.json()
                access_token_val = data.get("access_token")
                item_id = data.get("item_id")
                # Store mapping in backend
                if access_token_val:
                    await _store_token_mapping(user_id, access_token_val, item_id, institution)
                return SkillResult(
                    ok=True,
                    data={
                        "op": "exchange",
                        "connected": True,
                        "institution": institution,
                        "item_id": item_id,
                    },
                )
            return SkillResult(
                ok=False, data=None,
                error=f"Plaid token exchange failed: {resp.status_code} {resp.text[:200]}"
            )
        except httpx.HTTPError as exc:
            return SkillResult(ok=False, data=None, error=f"Failed to reach Plaid API: {exc}")

    # ---- All authenticated operations below require access_token ---------------
    if not access_token:
        return SkillResult(
            ok=False, data=None,
            error=f"access_token is required for '{op}' operation"
        )

    headers = {**_plaid_headers(), "Authorization": f"Bearer {access_token}"}

    # ---- list_accounts ------------------------------------------------------
    if op == "list_accounts":
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    _ACCOUNTS_URL.format(environment=env),
                    json={},
                    headers=headers,
                )
            if not resp.is_success:
                return SkillResult(
                    ok=False, data=None,
                    error=f"Plaid accounts error: {resp.status_code} {resp.text[:200]}"
                )
            data = resp.json()
            accounts = []
            for acct in data.get("accounts", []):
                accounts.append({
                    "account_id": acct.get("account_id"),
                    "name": acct.get("name"),
                    "type": acct.get("type"),
                    "subtype": acct.get("subtype"),
                    "mask": acct.get("mask"),
                    "balance_available": acct.get("balances", {}).get("available"),
                    "balance_current": acct.get("balances", {}).get("current"),
                    "balance_limit": acct.get("balances", {}).get("limit"),
                    "currency": acct.get("balances", {}).get("iso_currency_code", "USD"),
                })
            return SkillResult(
                ok=True,
                data={
                    "op": "list_accounts",
                    "accounts": accounts,
                    "institution": institution,
                },
            )
        except httpx.HTTPError as exc:
            return SkillResult(ok=False, data=None, error=f"Failed to reach Plaid: {exc}")

    # ---- get_transactions ---------------------------------------------------
    if op == "get_transactions":
        try:
            from datetime import date, timedelta
            today = date.today()
            start = start_date or (today - timedelta(days=90)).isoformat()
            end = end_date or today.isoformat()
            payload = {
                "start_date": start,
                "end_date": end,
                "account_ids": account_ids or [],
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    _TRANSACTIONS_URL.format(environment=env),
                    json=payload,
                    headers=headers,
                )
            if not resp.is_success:
                return SkillResult(
                    ok=False, data=None,
                    error=f"Plaid transactions error: {resp.status_code} {resp.text[:200]}"
                )
            data = resp.json()
            transactions = []
            total_spend = 0.0
            for txn in data.get("transactions", []):
                amount = float(txn.get("amount", 0))
                # Positive = spending in Plaid convention
                transactions.append({
                    "id": txn.get("transaction_id"),
                    "date": txn.get("date"),
                    "name": txn.get("name"),
                    "merchant": txn.get("merchant_name"),
                    "amount": amount,
                    "category": txn.get("category", []),
                    "category_id": txn.get("category_id"),
                    "pending": txn.get("pending", False),
                    "account_id": txn.get("account_id"),
                    "currency": txn.get("iso_currency_code", "USD"),
                })
                if amount > 0:
                    total_spend += amount
            return SkillResult(
                ok=True,
                data={
                    "op": "get_transactions",
                    "transactions": transactions,
                    "count": len(transactions),
                    "total_spend": round(total_spend, 2),
                    "date_range": {"start": start, "end": end},
                },
            )
        except httpx.HTTPError as exc:
            return SkillResult(ok=False, data=None, error=f"Failed to reach Plaid: {exc}")

    # ---- get_balance --------------------------------------------------------
    if op == "get_balance":
        try:
            payload: dict = {}
            if account_ids:
                payload["account_ids"] = account_ids
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    _BALANCE_URL.format(environment=env),
                    json=payload,
                    headers=headers,
                )
            if not resp.is_success:
                return SkillResult(
                    ok=False, data=None,
                    error=f"Plaid balance error: {resp.status_code} {resp.text[:200]}"
                )
            data = resp.json()
            accounts = []
            for acct in data.get("accounts", []):
                accounts.append({
                    "account_id": acct.get("account_id"),
                    "name": acct.get("name"),
                    "type": acct.get("type"),
                    "mask": acct.get("mask"),
                    "balance_available": acct.get("balances", {}).get("available"),
                    "balance_current": acct.get("balances", {}).get("current"),
                    "currency": acct.get("balances", {}).get("iso_currency_code", "USD"),
                })
            return SkillResult(
                ok=True,
                data={"op": "get_balance", "accounts": accounts},
            )
        except httpx.HTTPError as exc:
            return SkillResult(ok=False, data=None, error=f"Failed to reach Plaid: {exc}")

    # ---- disconnect ---------------------------------------------------------
    if op == "disconnect":
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    _REMOVE_URL.format(environment=env),
                    json={},
                    headers=headers,
                )
            if resp.is_success or resp.status_code == 400:
                # 400 means already removed
                await _remove_token_mapping(user_id)
                return SkillResult(
                    ok=True,
                    data={"op": "disconnect", "disconnected": True, "institution": institution},
                )
            return SkillResult(
                ok=False, data=None,
                error=f"Plaid disconnect error: {resp.status_code} {resp.text[:200]}"
            )
        except httpx.HTTPError as exc:
            return SkillResult(ok=False, data=None, error=f"Failed to reach Plaid: {exc}")

    return SkillResult(ok=False, data=None, error=f"Unknown op: {op}")


async def _store_token_mapping(user_id: str, access_token: str, item_id: str, institution: str | None) -> None:
    """Store access token mapping in the backend's secure token store."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{settings.backend_base_url}/api/v1/bank/connect",
                json={
                    "user_id": user_id,
                    "access_token": access_token,
                    "item_id": item_id,
                    "institution": institution,
                },
                headers={"Authorization": f"Bearer {user_id}"},
            )
    except Exception as exc:
        log.warning("bank_connect.token_store_failed", user_id=user_id, error=str(exc))


async def _remove_token_mapping(user_id: str) -> None:
    """Remove token mapping from the backend."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.delete(
                f"{settings.backend_base_url}/api/v1/bank/connect",
                headers={"Authorization": f"Bearer {user_id}"},
            )
    except Exception as exc:
        log.warning("bank_connect.token_remove_failed", user_id=user_id, error=str(exc))
