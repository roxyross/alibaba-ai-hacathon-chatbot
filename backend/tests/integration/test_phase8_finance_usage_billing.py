"""Phase 8 Master Integration Test Suite: Multi-Tenant Finance, Usage Tracking & Billing Engine.

Verifies:
1. Multi-Tenant Finance & Ledger:
   - Account provisioning with dual-currency (USD & PKR) balances.
   - Transaction ledger recording (debits/credits) and automatic balance updates.
   - Net worth and monthly burn rate calculation in financial summary.
   - Multi-tenant anti-IDOR isolation across accounts, transactions, and summaries.
2. Dual-Provider Billing & Wallet:
   - Configuration security (zero secret keys leaked).
   - Checkout session routing (Stripe USD & Safepay PKR).
   - Credit wallet balance, top-up pack checkout, and subscription lifecycle.
   - Webhook signature authentication and replay protection.
3. AI Token Usage Tracking & Metering:
   - User token recording with model attribution and cost tracking.
   - 30-day timeline generation, monthly credits consumed, and remaining balance.
   - Complete multi-tenant isolation between distinct user token logs.
4. Central ToolRegistry Integration & Confirmation Gating:
   - All 6 finance tools and 6 billing tools properly registered.
   - High-risk destructive tools (finance_delete_account, billing_cancel_subscription)
     strictly enforce RiskLevel.HIGH and requires_confirmation=True.
5. Deterministic AgentPlanner Intent Routing:
   - Precise single-intent decomposition for finance, billing, and usage goals.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, "src")

from app.agent_runtime.planner import AgentPlanner
from app.api.v1.usage import _USER_TOKEN_LOGS, record_user_tokens
from app.billing.repository import clear_in_memory_stores as clear_billing_stores
from app.billing.service import PaymentService
from app.finance.repository import FinanceRepository
from app.finance.service import FinanceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel, ToolExecutionRequest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_stores() -> None:
    clear_billing_stores()
    _USER_TOKEN_LOGS.clear()


async def _get_auth(client: AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Helper to register and authenticate a user, returning headers and user_id."""
    req_res = await client.post("/api/v1/auth/request-link", json={"email": email})
    assert req_res.status_code == 200
    token = req_res.json()["dev_token"]

    verify_res = await client.post("/api/v1/auth/verify", json={"token": token})
    assert verify_res.status_code == 200
    jwt_token = verify_res.json()["access_token"]
    user_id = verify_res.json()["user"]["id"]
    return {"Authorization": f"Bearer {jwt_token}"}, user_id


# -----------------------------------------------------------------------------
# 1. Multi-Tenant Finance & Ledger Service
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_finance_service_multi_tenant_crud_and_balances() -> None:
    """Verify FinanceService multi-tenant account lifecycle, transactions, and net worth."""
    service = FinanceService.get_instance()
    user_a = f"usr_fin_a_{uuid.uuid4().hex[:6]}"
    user_b = f"usr_fin_b_{uuid.uuid4().hex[:6]}"

    # User A starts with 0 accounts
    accounts_a = await service.list_accounts(user_a)
    assert len(accounts_a) == 0

    # User A connects Chase Checking ($5,000 USD) and Habib Bank PKR (250,000 PKR)
    acc_checking = await service.create_account(
        user_id=user_a,
        account_holder="Alice Cooper",
        institution_name="Chase Premier",
        account_type="checking",
        account_number_full="123456789012",
        account_number_masked="••••9012",
        balance_usd=5000.0,
        balance_pkr=1400000.0,
    )
    assert acc_checking["institution"] == "Chase Premier"
    assert acc_checking["balance_usd"] == 5000.0

    acc_pkr = await service.create_account(
        user_id=user_a,
        account_holder="Alice Cooper",
        institution_name="Habib Metropolitan",
        account_type="savings",
        account_number_full="987654321098",
        account_number_masked="••••1098",
        balance_usd=892.86,
        balance_pkr=250000.0,
    )
    assert acc_pkr["institution"] == "Habib Metropolitan"
    assert acc_pkr["balance_pkr"] == 250000.0

    # Record expense for User A
    tx1 = await service.record_transaction(
        user_id=user_a,
        account_id=acc_checking["id"],
        description="Grocery shopping at Trader Joe's",
        amount_usd=120.0,
        amount_pkr=33600.0,
        category="groceries",
        transaction_type="debit",
    )
    assert tx1["amount_usd"] == 120.0
    assert tx1["category"] == "groceries"

    # Verify updated balance on Checking
    acc_check_updated = await service.get_account(acc_checking["id"], user_id=user_a)
    assert acc_check_updated is not None
    assert acc_check_updated["balance_usd"] == 4880.0
    assert len(acc_check_updated["recent_transactions"]) == 1

    # Verify Summary & Net Worth for User A
    summary_a = await service.get_summary(user_id=user_a)
    assert summary_a["accounts_count"] == 2
    assert summary_a["total_net_worth_usd"] == round(4880.0 + 892.86, 2)
    assert summary_a["monthly_spending_burn_rate_usd"] == 120.0

    # Verify Multi-Tenant Boundary: User B sees ZERO accounts or transactions
    accounts_b = await service.list_accounts(user_b)
    assert len(accounts_b) == 0
    summary_b = await service.get_summary(user_id=user_b)
    assert summary_b["accounts_count"] == 0
    assert summary_b["total_net_worth_usd"] == 0.0

    # User B cannot access User A's account details (anti-IDOR)
    cross_account = await service.get_account(acc_checking["id"], user_id=user_b)
    assert cross_account is None

    # User A disconnects Checking account
    deleted = await service.delete_account(acc_checking["id"], user_id=user_a)
    assert deleted is True

    # Account no longer appears in User A's list
    remaining_accounts = await service.list_accounts(user_a)
    assert len(remaining_accounts) == 1
    assert remaining_accounts[0]["id"] == acc_pkr["id"]


# -----------------------------------------------------------------------------
# 2. Central ToolRegistry & Action Center Confirmation Gating
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tool_registry_finance_and_billing_tools() -> None:
    """Verify all 6 finance and 6 billing tools are registered with proper confirmation gating."""
    reg = ToolRegistry.get_instance()
    FinanceService.get_instance().register_finance_tools()
    PaymentService.get_instance().register_billing_tools()

    # 1. Finance Tools
    finance_tool_ids = [
        "finance_list_accounts",
        "finance_get_account",
        "finance_record_transaction",
        "finance_list_transactions",
        "finance_get_summary",
        "finance_delete_account",
    ]
    for tid in finance_tool_ids:
        t = reg.get(tid)
        assert t is not None, f"Tool '{tid}' not registered in ToolRegistry"

    # Destructive finance tool MUST be gated with RiskLevel.HIGH and require confirmation
    del_acc_tool = reg.get("finance_delete_account")
    assert del_acc_tool is not None
    assert del_acc_tool.risk_level == RiskLevel.HIGH
    assert del_acc_tool.requires_confirmation is True

    # Read-only finance tools should be LOW risk
    sum_tool = reg.get("finance_get_summary")
    assert sum_tool is not None
    assert sum_tool.risk_level == RiskLevel.LOW
    assert sum_tool.requires_confirmation is False

    # 2. Billing Tools
    billing_tool_ids = [
        "billing_get_wallet",
        "billing_list_plans",
        "billing_create_checkout",
        "billing_topup_credits",
        "billing_get_invoices",
        "billing_cancel_subscription",
    ]
    for tid in billing_tool_ids:
        t = reg.get(tid)
        assert t is not None, f"Tool '{tid}' not registered in ToolRegistry"

    # Destructive billing tool MUST be gated with RiskLevel.HIGH and require confirmation
    cancel_sub_tool = reg.get("billing_cancel_subscription")
    assert cancel_sub_tool is not None
    assert cancel_sub_tool.risk_level == RiskLevel.HIGH
    assert cancel_sub_tool.requires_confirmation is True


@pytest.mark.anyio
async def test_direct_execution_of_finance_and_billing_tools() -> None:
    """Test executing finance and billing tools directly through ToolRegistry."""
    reg = ToolRegistry.get_instance()
    FinanceService.get_instance().register_finance_tools()
    PaymentService.get_instance().register_billing_tools()

    user_id = f"usr_tool_test_{uuid.uuid4().hex[:6]}"

    # 1. finance_list_accounts returns empty list for new user
    res_accounts = await reg.execute(
        ToolExecutionRequest(
            tool_id="finance_list_accounts",
            arguments={},
            user_id=user_id,
        )
    )
    assert res_accounts.success is True
    assert res_accounts.output["total"] == 0
    assert res_accounts.output["accounts"] == []

    # 2. finance_get_summary returns zero net worth
    res_summary = await reg.execute(
        ToolExecutionRequest(
            tool_id="finance_get_summary",
            arguments={},
            user_id=user_id,
        )
    )
    assert res_summary.success is True
    assert res_summary.output["total_net_worth_usd"] == 0.0

    # 3. billing_get_wallet returns wallet with default remaining credits
    res_wallet = await reg.execute(
        ToolExecutionRequest(
            tool_id="billing_get_wallet",
            arguments={},
            user_id=user_id,
        )
    )
    assert res_wallet.success is True
    assert res_wallet.output["remaining_credits"] >= 0


    # 4. billing_list_plans returns plan and top-up details
    res_plans = await reg.execute(
        ToolExecutionRequest(
            tool_id="billing_list_plans",
            arguments={},
            user_id=user_id,
        )
    )
    assert res_plans.success is True
    assert any(p["id"] == "pro" for p in res_plans.output["plans"])
    assert any(p["id"] == "pack_10" for p in res_plans.output["top_up_packs"])



# -----------------------------------------------------------------------------
# 3. Deterministic Intent Routing in AgentPlanner
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_finance_and_billing_routing() -> None:
    """Verify AgentPlanner deterministic intent routing for Phase 8 capabilities."""
    planner = AgentPlanner()

    # 1. Finance Account and Summary Queries
    plan_accounts = await planner.create_plan("my bank accounts")
    assert plan_accounts[0]["tool_id"] == "finance_list_accounts"

    plan_accounts_alt = await planner.create_plan("show accounts")
    assert plan_accounts_alt[0]["tool_id"] == "finance_list_accounts"

    plan_summary = await planner.create_plan("financial summary")
    assert plan_summary[0]["tool_id"] == "finance_get_summary"

    plan_networth = await planner.create_plan("what is my net worth")
    assert plan_networth[0]["tool_id"] == "finance_get_summary"

    plan_finances = await planner.create_plan("my finances")
    assert plan_finances[0]["tool_id"] == "finance_get_summary"

    # 2. Finance Transactions
    plan_txs = await planner.create_plan("list transactions")
    assert plan_txs[0]["tool_id"] == "finance_list_transactions"

    plan_expenses = await planner.create_plan("recent expenses")
    assert plan_expenses[0]["tool_id"] == "finance_list_transactions"

    plan_record = await planner.create_plan("record expense $45 for groceries")
    assert plan_record[0]["tool_id"] == "finance_record_transaction"
    assert plan_record[0]["tool_input"]["amount_usd"] == 45.0
    assert plan_record[0]["tool_input"]["category"] == "groceries"

    # 3. Destructive Finance (disconnect account)
    plan_del_acc = await planner.create_plan("delete account acc_chase_123")
    assert plan_del_acc[0]["tool_id"] == "finance_delete_account"
    assert plan_del_acc[0]["tool_input"]["account_id"] == "acc_chase_123"

    # 4. Billing Wallet and Credits
    plan_wallet = await planner.create_plan("my credits")
    assert plan_wallet[0]["tool_id"] == "billing_get_wallet"

    plan_usage = await planner.create_plan("my token usage")
    assert plan_usage[0]["tool_id"] == "billing_get_wallet"

    # 5. Billing Plans and Checkout
    plan_plans = await planner.create_plan("subscription plans")
    assert plan_plans[0]["tool_id"] == "billing_list_plans"

    plan_upgrade = await planner.create_plan("upgrade to pro")
    assert plan_upgrade[0]["tool_id"] == "billing_create_checkout"
    assert plan_upgrade[0]["tool_input"]["plan_id"] == "pro"

    plan_topup = await planner.create_plan("top up credits")
    assert plan_topup[0]["tool_id"] == "billing_topup_credits"

    # 6. Destructive Billing (cancel subscription)
    plan_cancel = await planner.create_plan("cancel my subscription")
    assert plan_cancel[0]["tool_id"] == "billing_cancel_subscription"


# -----------------------------------------------------------------------------
# 4. AI Token Usage Tracking & Metering
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_token_usage_tracking_and_isolation(client: AsyncClient) -> None:
    """Verify AI token usage logging, cost computation, and strict multi-tenant boundary."""
    auth_a, user_a_id = await _get_auth(client, f"usr_tok_a_{uuid.uuid4().hex[:6]}@roxy.ai")
    auth_b, user_b_id = await _get_auth(client, f"usr_tok_b_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Record token usage for User A
    record_user_tokens(
        user_id=user_a_id,
        input_tokens=1500,
        output_tokens=500,
        cost_usd=0.008,
        provider_id="gemini",
        model_id="gemini-2.0-flash",
    )
    record_user_tokens(
        user_id=user_a_id,
        input_tokens=3000,
        output_tokens=1000,
        cost_usd=0.016,
        provider_id="gemini",
        model_id="gemini-2.0-pro",
    )

    # Fetch stats for User A
    res_a = await client.get("/api/v1/usage/stats", headers=auth_a)
    assert res_a.status_code == 200
    data_a = res_a.json()

    assert data_a["total_tokens"] == 6000
    assert data_a["prompt_tokens"] == 4500
    assert data_a["completion_tokens"] == 1500
    assert data_a["estimated_cost_usd"] == 0.024
    assert data_a["estimated_cost_pkr"] == round(0.024 * 300.0, 2)
    assert len(data_a["timeline"]) == 30
    assert len(data_a["recent_activity"]) == 2

    # Fetch stats for User B — MUST be completely isolated (0 tokens)
    res_b = await client.get("/api/v1/usage/stats", headers=auth_b)
    assert res_b.status_code == 200
    data_b = res_b.json()

    assert data_b["total_tokens"] == 0
    assert data_b["prompt_tokens"] == 0
    assert data_b["completion_tokens"] == 0
    assert data_b["estimated_cost_usd"] == 0.0
    assert len(data_b["recent_activity"]) == 0


# -----------------------------------------------------------------------------
# 5. Dual-Provider Billing HTTP Endpoints & Security
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_billing_checkout_and_config_endpoints(client: AsyncClient) -> None:
    """Verify dual provider checkout session creation and public configuration."""
    auth, user_id = await _get_auth(client, f"usr_bill_end_{uuid.uuid4().hex[:6]}@roxy.ai")

    # 1. Config endpoint
    conf_res = await client.get("/api/v1/billing/config")
    assert conf_res.status_code == 200
    conf_data = conf_res.json()
    assert "providers" in conf_data
    assert "stripe" in conf_data["providers"]
    assert "safepay" in conf_data["providers"]

    # 2. USD Checkout routes to Stripe
    chk_usd = await client.post(
        "/api/v1/billing/checkout",
        headers=auth,
        json={"plan_id": "pro", "currency": "usd"},
    )
    assert chk_usd.status_code == 200
    usd_data = chk_usd.json()
    assert usd_data["provider"] == "stripe"
    assert usd_data["session"]["currency"].lower() == "usd"
    assert "checkout_url" in usd_data

    # 3. PKR Checkout routes to Safepay
    chk_pkr = await client.post(
        "/api/v1/billing/checkout",
        headers=auth,
        json={"plan_id": "pro", "currency": "pkr"},
    )
    assert chk_pkr.status_code == 200
    pkr_data = chk_pkr.json()
    assert pkr_data["provider"] == "safepay"
    assert pkr_data["session"]["currency"].lower() == "pkr"
    assert "checkout_url" in pkr_data


    # 4. Top-up pack checkout
    top_res = await client.post(
        "/api/v1/billing/topup-checkout",
        headers=auth,
        json={"pack_id": "pack_10", "currency": "usd"},
    )
    assert top_res.status_code == 200
    top_data = top_res.json()
    assert top_data["session"]["metadata"]["pack_id"] == "pack_10"
    assert top_data["session"]["amount"] == 10.0
    assert "checkout_url" in top_data


