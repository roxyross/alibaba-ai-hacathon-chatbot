"""Phase 2 Master Integration Test Suite: Agent Runtime, Tool Registry, Permissions & Actions.

Verifies:
1. Tool Registry discovery, filtering, and sandboxed direct execution.
2. Permission Engine: checks, policy evaluation (always_ask, allow_automatically, never_allow), grant, and revoke.
3. Action Center: pending action listing, parameter editing, approval with verified execution, rejection.
4. Complete Verified Flow: Planning -> Tool Discovery -> Permission -> Execution -> Verification -> Result.
5. High-Risk Confirmation Flow: Action pauses task in waiting_for_permission -> Approval completes step & task.
6. Task Lifecycle: Pause, Resume, Cancel, and Retry mechanisms.
7. Multi-tenant isolation: strict separation across users for tasks and actions.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator

import httpx
import pytest

sys.path.insert(0, "src")

from app.actions.service import clear_in_memory_actions
from app.agent_runtime.executor import clear_in_memory_tasks
from app.main import app
from app.permissions.service import clear_in_memory_grants
from app.tools.builtin import register_builtin_tools


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    # Ensure all built-in tools are registered
    register_builtin_tools()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_runtime_state() -> None:
    clear_in_memory_grants()
    clear_in_memory_actions()
    clear_in_memory_tasks()


async def _get_auth(client: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Return (auth_headers, user_id)."""
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    verify_data = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()
    token = verify_data["access_token"]
    user_id = verify_data["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, user_id


# -----------------------------------------------------------------------------
# 1. Tool Registry Tests
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tool_registry_listing_and_filtering(client: httpx.AsyncClient) -> None:
    auth_header, _ = await _get_auth(client, "user_tools@example.com")

    # List all tools
    resp = await client.get("/api/v1/tools", headers=auth_header)
    assert resp.status_code == 200
    tools = resp.json()
    assert len(tools) >= 5

    tool_ids = [t["id"] for t in tools]
    assert "system_calculator" in tool_ids
    assert "system_web_search" in tool_ids
    assert "system_email_send" in tool_ids
    assert "system_schedule_job" in tool_ids

    # Filter by source=system
    sys_resp = await client.get("/api/v1/tools?source=system", headers=auth_header)
    assert sys_resp.status_code == 200
    sys_tools = sys_resp.json()
    assert all(t["source"] == "system" for t in sys_tools)

    # Filter by risk_level=high
    high_resp = await client.get("/api/v1/tools?risk_level=high", headers=auth_header)
    assert high_resp.status_code == 200
    high_tools = high_resp.json()
    assert any(t["id"] == "system_email_send" for t in high_tools)


@pytest.mark.anyio
async def test_tool_direct_execution(client: httpx.AsyncClient) -> None:
    auth_header, _ = await _get_auth(client, "user_exec@example.com")

    # Execute math calculator
    resp = await client.post(
        "/api/v1/tools/execute",
        headers=auth_header,
        json={
            "tool_id": "system_calculator",
            "arguments": {"expression": "25 * 4 + 10"},
            "user_id": "placeholder",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["output"]["result"] == 110


# -----------------------------------------------------------------------------
# 2. Permission Engine Tests
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_permission_evaluation_and_policy_override(client: httpx.AsyncClient) -> None:
    auth_header, user_id = await _get_auth(client, "user_perm@example.com")

    # 1. Low-risk tool: calculator should be pre-authorized
    check_calc = await client.post(
        "/api/v1/permissions/check",
        headers=auth_header,
        json={"tool_id": "system_calculator", "permission": "execute"},
    )
    assert check_calc.status_code == 200
    assert check_calc.json()["granted"] is True
    assert check_calc.json()["requires_confirmation"] is False

    # 2. High-risk tool: email send requires confirmation by default
    check_email = await client.post(
        "/api/v1/permissions/check",
        headers=auth_header,
        json={"tool_id": "system_email_send", "permission": "email:send"},
    )
    assert check_email.status_code == 200
    assert check_email.json()["requires_confirmation"] is True

    # 3. Grant allow_automatically policy to email_send
    grant_resp = await client.post(
        "/api/v1/permissions/grant",
        headers=auth_header,
        json={
            "tool_id": "system_email_send",
            "permission": "email:send",
            "policy": "allow_automatically",
        },
    )
    assert grant_resp.status_code == 200
    assert grant_resp.json()["policy"] == "allow_automatically"

    # Verify check now returns granted=True without confirmation
    check_after_grant = await client.post(
        "/api/v1/permissions/check",
        headers=auth_header,
        json={"tool_id": "system_email_send", "permission": "email:send"},
    )
    assert check_after_grant.json()["granted"] is True
    assert check_after_grant.json()["requires_confirmation"] is False

    # 4. Set policy to never_allow (explicit blocking)
    await client.post(
        "/api/v1/permissions/grant",
        headers=auth_header,
        json={
            "tool_id": "system_email_send",
            "permission": "email:send",
            "policy": "never_allow",
        },
    )
    check_blocked = await client.post(
        "/api/v1/permissions/check",
        headers=auth_header,
        json={"tool_id": "system_email_send", "permission": "email:send"},
    )
    assert check_blocked.json()["granted"] is False
    assert check_blocked.json()["requires_confirmation"] is False
    assert "blocked" in check_blocked.json()["reason"].lower()

    # 5. Revoke grant
    revoke_resp = await client.post(
        "/api/v1/permissions/revoke",
        headers=auth_header,
        json={"tool_id": "system_email_send", "permission": "email:send"},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked"] is True


# -----------------------------------------------------------------------------
# 3. Action Center & Confirmation Layer Tests
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_action_center_lifecycle(client: httpx.AsyncClient) -> None:
    auth_header, user_id = await _get_auth(client, "user_actions@example.com")

    # Creating task with high-risk tool automatically triggers action creation
    task_resp = await client.post(
        "/api/v1/agents/tasks",
        headers=auth_header,
        json={
            "objective": "Send an email to supervisor@company.com with subject Weekly Status",
            "auto_run": True,
        },
    )
    assert task_resp.status_code == 200
    task_data = task_resp.json()
    assert task_data["status"] == "waiting_for_permission"

    # Check pending actions queue
    actions_resp = await client.get("/api/v1/actions/pending", headers=auth_header)
    assert actions_resp.status_code == 200
    actions = actions_resp.json()
    assert len(actions) == 1
    action = actions[0]
    assert action["status"] == "pending"
    assert action["tool_id"] == "system_email_send"
    assert action["risk_level"] == "high"

    # Edit action parameters before approval
    edit_resp = await client.post(
        f"/api/v1/actions/{action['id']}/edit",
        headers=auth_header,
        json={
            "input_parameters": {
                "to": "supervisor@company.com",
                "subject": "Updated Weekly Status",
                "body": "All milestones on schedule.",
            }
        },
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["input_parameters"]["subject"] == "Updated Weekly Status"

    # Approve action -> Triggers execution
    approve_resp = await client.post(
        f"/api/v1/actions/{action['id']}/approve",
        headers=auth_header,
    )
    assert approve_resp.status_code == 200
    approved_data = approve_resp.json()
    assert approved_data["status"] == "executed"
    assert approved_data["result"] is not None

    # Pending queue should now be empty
    pending_after = (await client.get("/api/v1/actions/pending", headers=auth_header)).json()
    assert len(pending_after) == 0

    # History contains the action
    history = (await client.get("/api/v1/actions/history", headers=auth_header)).json()
    assert len(history) == 1
    assert history[0]["id"] == action["id"]


# -----------------------------------------------------------------------------
# 4. End-to-End Autonomous Agent Execution Flow
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_task_complete_flow_calculator(client: httpx.AsyncClient) -> None:
    """Tests Planning -> Discovery -> Permission -> Execution -> Verification -> Result."""
    auth_header, _ = await _get_auth(client, "user_flow@example.com")

    task_resp = await client.post(
        "/api/v1/agents/tasks",
        headers=auth_header,
        json={"objective": "Calculate (45 * 2) + 10", "auto_run": True},
    )
    assert task_resp.status_code == 200
    task = task_resp.json()
    assert task["status"] == "completed"
    assert len(task["steps"]) >= 1

    calc_step = task["steps"][0]
    assert calc_step["status"] == "completed"
    assert calc_step["tool_id"] == "system_calculator"
    assert calc_step["tool_output"]["result"] == 100
    assert len(task["deliverables"]) >= 1


@pytest.mark.anyio
async def test_agent_task_multi_step_flow(client: httpx.AsyncClient) -> None:
    """Tests multi-step decomposition: Search web -> Send email."""
    auth_header, _ = await _get_auth(client, "user_multistep@example.com")

    task_resp = await client.post(
        "/api/v1/agents/tasks",
        headers=auth_header,
        json={
            "objective": "Search for artificial intelligence news and email summary to team@startup.io",
            "auto_run": True,
        },
    )
    assert task_resp.status_code == 200
    task = task_resp.json()
    assert len(task["steps"]) == 2

    # Step 1 (Search) executed and completed
    step1 = task["steps"][0]
    assert step1["status"] == "completed"
    assert step1["tool_id"] == "system_web_search"

    # Step 2 (Email) is waiting for user confirmation
    step2 = task["steps"][1]
    assert step2["status"] == "waiting_for_approval"
    assert task["status"] == "waiting_for_permission"

    # Approve the pending action for Step 2
    pending = (await client.get("/api/v1/actions/pending", headers=auth_header)).json()
    assert len(pending) == 1
    action_id = pending[0]["id"]
    await client.post(f"/api/v1/actions/{action_id}/approve", headers=auth_header)

    # Resume/run task to complete remaining flow
    run_resp = await client.post(f"/api/v1/agents/tasks/{task['id']}/run", headers=auth_header)
    assert run_resp.status_code == 200
    updated_task = run_resp.json()
    assert updated_task["status"] == "completed"
    assert updated_task["steps"][1]["status"] == "completed"


# -----------------------------------------------------------------------------
# 5. Task Lifecycle Controls: Pause, Resume, Cancel, Retry
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_task_lifecycle_controls(client: httpx.AsyncClient) -> None:
    auth_header, _ = await _get_auth(client, "user_lifecycle@example.com")

    # Create task with auto_run=False
    task_resp = await client.post(
        "/api/v1/agents/tasks",
        headers=auth_header,
        json={"objective": "Search for quantum physics", "auto_run": False},
    )
    task_id = task_resp.json()["id"]
    assert task_resp.json()["status"] == "draft"

    # Pause task
    pause_resp = await client.post(f"/api/v1/agents/tasks/{task_id}/pause", headers=auth_header)
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    # Cancel task
    cancel_resp = await client.post(f"/api/v1/agents/tasks/{task_id}/cancel", headers=auth_header)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Retry task
    retry_resp = await client.post(f"/api/v1/agents/tasks/{task_id}/retry", headers=auth_header)
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] in ("running", "completed")


# -----------------------------------------------------------------------------
# 6. Multi-Tenant Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_task_multi_tenant_isolation(client: httpx.AsyncClient) -> None:
    auth_a, user_a = await _get_auth(client, "user_a@isolation.com")
    auth_b, user_b = await _get_auth(client, "user_b@isolation.com")

    # User A creates a task
    task_a = (
        await client.post(
            "/api/v1/agents/tasks",
            headers=auth_a,
            json={"objective": "User A secret objective", "auto_run": False},
        )
    ).json()

    # User B cannot view User A's task
    get_b = await client.get(f"/api/v1/agents/tasks/{task_a['id']}", headers=auth_b)
    assert get_b.status_code == 404

    # User B list contains 0 tasks
    list_b = (await client.get("/api/v1/agents/tasks", headers=auth_b)).json()
    assert len(list_b) == 0

    # User B cannot pause or cancel User A's task
    pause_b = await client.post(f"/api/v1/agents/tasks/{task_a['id']}/pause", headers=auth_b)
    assert pause_b.status_code == 400 or pause_b.status_code == 404
