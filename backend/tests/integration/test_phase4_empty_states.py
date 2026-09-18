"""Phase 4 Master Integration Test Suite: Purge Hardcoded Mock Data & Enforce Empty States.

Verifies:
1. Freshly registered users start with zero scheduled jobs, 0 workspace projects, 0 token usage,
   free plan default with no saved payment cards, zero invoices, zero finance accounts/alerts,
   and zero knowledge vault documents.
2. Cross-tenant isolation across all resources (User B cannot see, modify, or delete User A's jobs,
   projects, or payment methods).
3. All empty state contracts return empty collections rather than hardcoded mock fixtures.
"""

from __future__ import annotations

import sys
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


async def _get_auth_headers(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    jwt = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()["access_token"]
    return {"Authorization": f"Bearer {jwt}"}


async def test_fresh_user_jobs_empty_and_tenant_isolated(client: httpx.AsyncClient) -> None:
    user_a = await _get_auth_headers(client, "fresh_user_a@roxy.ai")
    user_b = await _get_auth_headers(client, "fresh_user_b@roxy.ai")

    # 1. Fresh user A receives empty jobs list
    resp = await client.get("/api/v1/jobs", headers=user_a)
    assert resp.status_code == 200
    assert resp.json()["jobs"] == []

    # 2. User A creates a scheduled job
    create_resp = await client.post(
        "/api/v1/jobs",
        headers=user_a,
        json={
            "name": "Daily Calendar Sync",
            "task": "Sync Google Calendar events and summarize upcoming schedule",
            "schedule": "0 8 * * *",
            "next_run": "Tomorrow at 8:00 AM",
        },
    )
    assert create_resp.status_code == 200
    job_a = create_resp.json()["job"]
    job_a_id = job_a["id"]

    # 3. User A now sees 1 job
    resp_a = await client.get("/api/v1/jobs", headers=user_a)
    assert resp_a.status_code == 200
    assert len(resp_a.json()["jobs"]) == 1
    assert resp_a.json()["jobs"][0]["id"] == job_a_id

    # 4. User B still receives 0 jobs (Strict Multi-Tenant Isolation)
    resp_b = await client.get("/api/v1/jobs", headers=user_b)
    assert resp_b.status_code == 200
    assert resp_b.json()["jobs"] == []

    # 5. User B cannot pause or delete User A's job (404 Not Found)
    patch_b = await client.patch(
        f"/api/v1/jobs/{job_a_id}/status",
        headers=user_b,
        json={"status": "paused"},
    )
    assert patch_b.status_code == 404

    del_b = await client.delete(f"/api/v1/jobs/{job_a_id}", headers=user_b)
    assert del_b.status_code == 404

    # 6. User A can pause and delete their own job
    patch_a = await client.patch(
        f"/api/v1/jobs/{job_a_id}/status",
        headers=user_a,
        json={"status": "Pause"},
    )
    assert patch_a.status_code == 200
    assert patch_a.json()["job"]["status"] in ("Pause", "paused")

    del_a = await client.delete(f"/api/v1/jobs/{job_a_id}", headers=user_a)
    assert del_a.status_code == 200
    assert (await client.get("/api/v1/jobs", headers=user_a)).json()["jobs"] == []


async def test_fresh_user_projects_empty_and_tenant_isolated(client: httpx.AsyncClient) -> None:
    user_a = await _get_auth_headers(client, "project_user_a@roxy.ai")
    user_b = await _get_auth_headers(client, "project_user_b@roxy.ai")

    # 1. Fresh user A receives empty projects list
    resp = await client.get("/api/v1/projects", headers=user_a)
    assert resp.status_code == 200
    assert resp.json()["projects"] == []

    # 2. User A creates a workspace project
    create_resp = await client.post(
        "/api/v1/projects",
        headers=user_a,
        json={
            "name": "Q4 SaaS Strategy",
            "description": "Cross-border marketing and pricing model analysis",
            "status": "In Progress",
            "tasks_count": 8,
            "tasks_completed": 2,
        },
    )
    assert create_resp.status_code == 200
    proj_a = create_resp.json()["project"]
    proj_a_id = proj_a["id"]

    # 3. User A sees their project
    resp_a = await client.get("/api/v1/projects", headers=user_a)
    assert len(resp_a.json()["projects"]) == 1

    # 4. User B receives empty projects (Isolation)
    resp_b = await client.get("/api/v1/projects", headers=user_b)
    assert resp_b.json()["projects"] == []

    # 5. User B cannot modify or delete User A's project (404)
    patch_b = await client.patch(
        f"/api/v1/projects/{proj_a_id}",
        headers=user_b,
        json={"status": "Completed"},
    )
    assert patch_b.status_code == 404

    del_b = await client.delete(f"/api/v1/projects/{proj_a_id}", headers=user_b)
    assert del_b.status_code == 404

    # 6. User A deletes their project
    del_a = await client.delete(f"/api/v1/projects/{proj_a_id}", headers=user_a)
    assert del_a.status_code == 200
    assert (await client.get("/api/v1/projects", headers=user_a)).json()["projects"] == []


async def test_fresh_user_usage_stats_is_zero(client: httpx.AsyncClient) -> None:
    user = await _get_auth_headers(client, "usage_fresh_user@roxy.ai")

    resp = await client.get("/api/v1/usage/stats", headers=user)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_tokens"] == 0
    assert data["prompt_tokens"] == 0
    assert data["completion_tokens"] == 0
    assert data["estimated_cost_usd"] == 0.0
    assert data["recent_activity"] == []
    assert len(data["daily_timeline"]) == 30
    assert all(point["tokens"] == 0 for point in data["daily_timeline"])


async def test_fresh_user_billing_defaults_and_isolation(client: httpx.AsyncClient) -> None:
    user_a = await _get_auth_headers(client, "billing_user_a@roxy.ai")
    user_b = await _get_auth_headers(client, "billing_user_b@roxy.ai")

    # 1. Fresh subscription defaults to Free (BYOK)
    sub_resp = await client.get("/api/v1/billing/subscription", headers=user_a)
    assert sub_resp.status_code == 200
    sub_data = sub_resp.json()
    assert sub_data["plan"]["id"] == "free"
    assert sub_data["plan"]["price_usd"] == 0.0
    assert sub_data["payment_method"] is None

    # 2. Fresh payment methods are completely empty
    pm_resp = await client.get("/api/v1/billing/payment-methods", headers=user_a)
    assert pm_resp.status_code == 200
    pm_data = pm_resp.json()
    assert pm_data["primary"] is None
    assert pm_data["saved_methods"] == []

    # 3. Fresh invoices are empty
    inv_resp = await client.get("/api/v1/billing/invoices", headers=user_a)
    assert inv_resp.status_code == 200
    assert inv_resp.json()["invoices"] == []

    # 4. User A saves a payment method
    add_pm_resp = await client.post(
        "/api/v1/billing/payment-methods",
        headers=user_a,
        json={
            "brand": "visa",
            "last4": "4242",
            "exp_month": 12,
            "exp_year": 2028,
            "set_as_default": True,
        },
    )
    assert add_pm_resp.status_code == 200
    pm_id = add_pm_resp.json()["payment_method"]["id"]

    # 5. User B still has 0 payment methods
    pm_resp_b = await client.get("/api/v1/billing/payment-methods", headers=user_b)
    assert pm_resp_b.json()["primary"] is None
    assert pm_resp_b.json()["saved_methods"] == []

    # 6. User B cannot delete User A's card (404)
    del_b = await client.delete(f"/api/v1/billing/payment-methods/{pm_id}", headers=user_b)
    assert del_b.status_code == 404

    # 7. User A deletes their card
    del_a = await client.delete(f"/api/v1/billing/payment-methods/{pm_id}", headers=user_a)
    assert del_a.status_code == 200
    assert (await client.get("/api/v1/billing/payment-methods", headers=user_a)).json()["primary"] is None


async def test_fresh_user_finance_and_documents_empty(client: httpx.AsyncClient) -> None:
    user = await _get_auth_headers(client, "finance_doc_fresh@roxy.ai")

    # 1. Finance summary starts with zero accounts, zero budgets, zero alerts
    fin_resp = await client.get("/api/v1/finance/summary", headers=user)
    assert fin_resp.status_code == 200
    fin_data = fin_resp.json()
    assert fin_data["accounts"] == []
    assert fin_data["total_balance"] == 0.0
    assert fin_data["budgets"] == []
    assert fin_data["alerts"] == []
    assert fin_data["month_spending"] == 0.0

    # 2. Documents repository starts empty
    doc_resp = await client.get("/api/v1/documents", headers=user)
    assert doc_resp.status_code == 200
    assert doc_resp.json()["documents"] == []
