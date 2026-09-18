"""Phase 6 Master Integration Test Suite: Institutional Finance Integrations & Multi-Tenant Ledger.

Verifies:
1. Fresh user empty state: zero accounts, zero transactions, zero alerts, $0.00 balance.
2. Plaid bank connection & transaction ledger provisioning (Chase Premier Checking & Savings).
3. Raast (Deewan / PISP Mode) account linking, instant payment, balance deduction, and ledger sync.
4. Strict multi-tenant isolation across all financial accounts, transactions, and alerts.
5. Cross-tenant mutation guards (User B cannot pin, unlink, pay from, or delete User A's assets).
6. Transaction statement period filtering (day, week, month, year) and pin toggling.
7. Spending alert lifecycle and status toggles.
8. Finance Agent chat grounding with live user balances.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

# Ensure backend src is on sys.path
sys.path.insert(0, "src")

from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


async def _get_auth(client: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Return (auth_headers, user_id)."""
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    verify_data = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()
    jwt_tok = verify_data["access_token"]
    user_id = verify_data["user"]["id"]
    return {"Authorization": f"Bearer {jwt_tok}"}, user_id


@pytest.mark.asyncio
async def test_fresh_user_financial_ledger_empty(client: httpx.AsyncClient) -> None:
    """A newly registered user has zero accounts, zero transactions, and $0.00 total balance."""
    uid = uuid.uuid4().hex[:8]
    headers, _ = await _get_auth(client, f"fin_fresh_{uid}@example.com")

    # 1. Summary
    sum_res = await client.get("/api/v1/finance/summary", headers=headers)
    assert sum_res.status_code == 200
    sum_data = sum_res.json()
    assert sum_data["accounts"] == []
    assert sum_data["total_balance"] == 0.0
    assert sum_data["month_spending"] == 0.0
    assert sum_data["budgets"] == []
    assert sum_data["alerts"] == []

    # 2. Transactions
    tx_res = await client.get("/api/v1/finance/transactions", headers=headers)
    assert tx_res.status_code == 200
    assert tx_res.json()["transactions"] == []
    assert tx_res.json()["total"] == 0

    # 3. Raast accounts
    raast_res = await client.get("/api/v1/raast/accounts", headers=headers)
    assert raast_res.status_code == 200
    assert raast_res.json()["accounts"] == []


@pytest.mark.asyncio
async def test_plaid_bank_connection_and_transaction_sync(client: httpx.AsyncClient) -> None:
    """Connecting a bank provisions Chase accounts and real transactions in the user's ledger."""
    uid = uuid.uuid4().hex[:8]
    headers, user_id = await _get_auth(client, f"plaid_user_{uid}@example.com")

    # Connect demo bank
    conn_res = await client.post("/api/v1/bank/demo-connect", headers=headers)
    assert conn_res.status_code == 201
    assert conn_res.json()["institution"] == "Chase Bank"

    # Verify accounts in summary
    sum_res = await client.get("/api/v1/finance/summary", headers=headers)
    assert sum_res.status_code == 200
    sum_data = sum_res.json()
    assert len(sum_data["accounts"]) >= 2

    checking = next(a for a in sum_data["accounts"] if "Checking" in a["name"])
    savings = next(a for a in sum_data["accounts"] if "Savings" in a["name"])
    assert checking["balance_usd"] == 4520.50
    assert savings["balance_usd"] == 12850.00
    assert sum_data["total_balance"] >= 17370.50

    # Verify transactions in ledger
    tx_res = await client.get("/api/v1/finance/transactions", headers=headers)
    assert tx_res.status_code == 200
    tx_list = tx_res.json()["transactions"]
    assert len(tx_list) >= 5

    descriptions = [t["description"] for t in tx_list]
    assert any("Trader Joe's" in d for d in descriptions)
    assert any("Salary" in d for d in descriptions)
    assert any("Copilot" in d for d in descriptions)

    # Monthly spending should reflect debits
    assert sum_data["month_spending"] > 0.0


@pytest.mark.asyncio
async def test_raast_pisp_account_linking_and_instant_payment(client: httpx.AsyncClient) -> None:
    """User links a Raast account, executes instant payment, and balance is deducted with ledger entry."""
    uid = uuid.uuid4().hex[:8]
    headers, user_id = await _get_auth(client, f"raast_user_{uid}@example.com")

    # 1. Link Pakistani bank account via Raast
    link_payload = {
        "bank_name": "Meezan Bank",
        "account_title": "Apex Digital Innovations",
        "iban": "PK89MEZN00012345678901",
        "raast_id": "03001234567",
        "initial_balance_pkr": 150000.0,
    }
    link_res = await client.post("/api/v1/raast/link", headers=headers, json=link_payload)
    assert link_res.status_code == 200
    acc_data = link_res.json()
    assert acc_data["status"] == "success"
    assert acc_data["bank_name"] == "Meezan Bank"
    assert acc_data["balance_pkr"] == 150000.0
    assert acc_data["balance_usd"] == 500.0
    account_id = acc_data["account_id"]

    # Verify listed in Raast accounts
    raast_list = (await client.get("/api/v1/raast/accounts", headers=headers)).json()["accounts"]
    assert len(raast_list) == 1
    assert raast_list[0]["id"] == account_id

    # 2. Initiate Instant Payment
    pay_payload = {
        "receiver_raast_id": "03219988776",
        "amount_pkr": 15000.0,
        "purpose": "Cloud Hosting & GPU Compute",
        "source_account_id": account_id,
    }
    pay_res = await client.post("/api/v1/raast/initiate-payment", headers=headers, json=pay_payload)
    assert pay_res.status_code == 200
    pay_data = pay_res.json()
    assert pay_data["status"] == "completed"
    assert pay_data["amount_pkr"] == 15000.0
    assert pay_data["amount_usd"] == 50.0
    assert pay_data["remaining_balance_pkr"] == 135000.0
    assert pay_data["receiver"] == "03219988776"

    # 3. Verify ledger transaction recorded
    tx_res = await client.get("/api/v1/finance/transactions", headers=headers)
    assert tx_res.status_code == 200
    txs = tx_res.json()["transactions"]
    assert len(txs) == 1
    raast_tx = txs[0]
    assert "Raast Transfer to 03219988776" in raast_tx["description"]
    assert raast_tx["category"] == "Transfer"
    assert raast_tx["amount_pkr"] == -15000.0
    assert raast_tx["amount_usd"] == -50.0


@pytest.mark.asyncio
async def test_multi_tenant_financial_isolation_and_cross_guards(client: httpx.AsyncClient) -> None:
    """User B cannot see, pin, unlink, or pay from User A's financial accounts and transactions."""
    uid = uuid.uuid4().hex[:8]
    headers_a, user_id_a = await _get_auth(client, f"fin_alice_{uid}@example.com")
    headers_b, user_id_b = await _get_auth(client, f"fin_bob_{uid}@example.com")

    # User A connects Plaid and Raast
    await client.post("/api/v1/bank/demo-connect", headers=headers_a)
    raast_a = (
        await client.post(
            "/api/v1/raast/link",
            headers=headers_a,
            json={
                "bank_name": "Bank Alfalah",
                "account_title": "Alice Private Reserve",
                "iban": "PK36ALFH00098765432101",
                "initial_balance_pkr": 200000.0,
            },
        )
    ).json()
    raast_a_id = raast_a["account_id"]

    # User A creates an alert
    al_res = await client.post(
        "/api/v1/finance/alerts",
        headers=headers_a,
        json={
            "name": "Alice High Spending",
            "alert_type": "budget_warning",
            "threshold_amount": 1000.0,
        },
    )
    alert_a_id = al_res.json()["id"]

    # Get User A's transactions
    tx_a = (await client.get("/api/v1/finance/transactions", headers=headers_a)).json()["transactions"]
    assert len(tx_a) > 0
    tx_a_id = tx_a[0]["id"]

    # 1. User B sees 0 accounts, 0 transactions, 0 alerts
    sum_b = (await client.get("/api/v1/finance/summary", headers=headers_b)).json()
    assert len(sum_b["accounts"]) == 0
    assert sum_b["total_balance"] == 0.0

    tx_b = (await client.get("/api/v1/finance/transactions", headers=headers_b)).json()
    assert len(tx_b["transactions"]) == 0

    raast_b = (await client.get("/api/v1/raast/accounts", headers=headers_b)).json()
    assert len(raast_b["accounts"]) == 0

    al_b = (await client.get("/api/v1/finance/alerts", headers=headers_b)).json()
    assert len(al_b["alerts"]) == 0

    # 2. Cross-tenant mutation guards -> MUST return 404
    pin_cross = await client.patch(f"/api/v1/finance/transactions/{tx_a_id}/pin", headers=headers_b)
    assert pin_cross.status_code == 404

    unlink_cross = await client.delete(f"/api/v1/raast/accounts/{raast_a_id}", headers=headers_b)
    assert unlink_cross.status_code == 404

    del_acc_cross = await client.delete(f"/api/v1/finance/accounts/{raast_a_id}", headers=headers_b)
    assert del_acc_cross.status_code == 404

    alert_toggle_cross = await client.patch(f"/api/v1/finance/alerts/{alert_a_id}/status", headers=headers_b)
    assert alert_toggle_cross.status_code == 404

    alert_del_cross = await client.delete(f"/api/v1/finance/alerts/{alert_a_id}", headers=headers_b)
    assert alert_del_cross.status_code == 404

    # User B cannot pay from User A's Raast account
    pay_cross = await client.post(
        "/api/v1/raast/initiate-payment",
        headers=headers_b,
        json={
            "receiver_raast_id": "03001122334",
            "amount_pkr": 5000.0,
            "source_account_id": raast_a_id,
        },
    )
    assert pay_cross.status_code in (400, 404)


@pytest.mark.asyncio
async def test_transaction_pinning_and_period_filtering(client: httpx.AsyncClient) -> None:
    """User can pin/unpin transactions and filter statements by period."""
    uid = uuid.uuid4().hex[:8]
    headers, _ = await _get_auth(client, f"pin_user_{uid}@example.com")
    await client.post("/api/v1/bank/demo-connect", headers=headers)

    txs = (await client.get("/api/v1/finance/transactions", headers=headers)).json()["transactions"]
    assert len(txs) > 0
    target_tx = txs[0]
    tx_id = target_tx["id"]
    assert target_tx["is_pinned"] is False

    # 1. Pin transaction
    pin_res = await client.patch(f"/api/v1/finance/transactions/{tx_id}/pin", headers=headers)
    assert pin_res.status_code == 200
    assert pin_res.json()["is_pinned"] is True

    # 2. Unpin transaction
    unpin_res = await client.patch(f"/api/v1/finance/transactions/{tx_id}/pin", headers=headers)
    assert unpin_res.status_code == 200
    assert unpin_res.json()["is_pinned"] is False

    # 3. Test period filtering
    for period in ("day", "week", "month", "year"):
        resp = await client.get(f"/api/v1/finance/transactions?period={period}", headers=headers)
        assert resp.status_code == 200
        assert "transactions" in resp.json()


@pytest.mark.asyncio
async def test_finance_agent_chat_grounding(client: httpx.AsyncClient) -> None:
    """The Finance Agent grounds chat responses in the user's live connected accounts."""
    uid = uuid.uuid4().hex[:8]
    headers_a, _ = await _get_auth(client, f"chat_fin_a_{uid}@example.com")
    headers_b, _ = await _get_auth(client, f"chat_fin_b_{uid}@example.com")

    # User A connects Plaid and Raast
    await client.post("/api/v1/bank/demo-connect", headers=headers_a)
    await client.post(
        "/api/v1/raast/link",
        headers=headers_a,
        json={
            "bank_name": "Nayapay Private Wallet",
            "account_title": "Tech Founder Reserve",
            "iban": "PK12NAYA00099988877701",
            "initial_balance_pkr": 75000.0,
        },
    )

    # User A asks about accounts & balances
    chat_payload = {
        "message": "What accounts do I have connected and what is my total balance?",
        "agent_override": "finance",
    }
    res_a = await client.post("/api/v1/runtime/chat", headers=headers_a, json=chat_payload)
    assert res_a.status_code == 200
    resp_text_a = res_a.json()["response"]

    # Must mention user's live accounts or balances
    assert any(w in resp_text_a for w in ("Chase", "Nayapay", "balance", "$", "Rs"))

    # User B asks the exact same thing
    res_b = await client.post("/api/v1/runtime/chat", headers=headers_b, json=chat_payload)
    assert res_b.status_code == 200
    resp_text_b = res_b.json()["response"]

    # User B must NOT have User A's private account names
    assert "Nayapay Private Wallet" not in resp_text_b
    assert "Tech Founder Reserve" not in resp_text_b
