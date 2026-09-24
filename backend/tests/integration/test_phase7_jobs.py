"""Phase 7 Master Integration Test Suite: Autonomous Background Jobs & Scheduler Engine.

Verifies:
1. Fresh user empty state: zero scheduled jobs.
2. Job creation with natural language and 5-field CRON expressions.
3. Job status toggle lifecycle (Active -> Pause -> Active).
4. On-demand manual execution (POST /jobs/{id}/run) and execution history recording.
5. Strict multi-tenant isolation (User B cannot view, modify, run, or delete User A's jobs).
6. Job deletion and cleanup.
7. Automation Agent chat grounding (reflects live configured jobs for User A, prevents leakage to User B).
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from unittest.mock import patch

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
async def test_fresh_user_jobs_empty(client: httpx.AsyncClient) -> None:
    """A newly registered user has zero scheduled jobs."""
    uid = uuid.uuid4().hex[:8]
    headers, _ = await _get_auth(client, f"jobs_fresh_{uid}@example.com")

    res = await client.get("/api/v1/jobs", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "jobs" in data
    assert data["jobs"] == []


@pytest.mark.asyncio
async def test_create_and_list_jobs(client: httpx.AsyncClient) -> None:
    """User can create scheduled jobs with natural language and CRON schedules."""
    uid = uuid.uuid4().hex[:8]
    headers, user_id = await _get_auth(client, f"jobs_create_{uid}@example.com")

    # 1. Create job with natural language schedule
    job1_payload = {
        "name": "Daily Market Intelligence Briefing",
        "description": "Scrape tech news and generate sentiment digest every morning",
        "schedule": "Every day at 08:00 AM",
        "timezone": "Asia/Karachi",
        "prompt": "Summarize top tech news and sentiment",
    }
    create_res1 = await client.post("/api/v1/jobs", headers=headers, json=job1_payload)
    assert create_res1.status_code in (200, 201)
    job1 = create_res1.json()["job"]
    assert job1["name"] == "Daily Market Intelligence Briefing"
    assert job1["status"] == "Active"
    assert job1["timezone"] == "Asia/Karachi"
    assert job1["next_run"] is not None

    # 2. Create job with 5-field CRON expression
    job2_payload = {
        "name": "Weekday End-of-Day Database Vacuum",
        "description": "Run background vacuum and index health check",
        "schedule": "0 18 * * 1-5",
        "timezone": "UTC",
    }
    create_res2 = await client.post("/api/v1/jobs", headers=headers, json=job2_payload)
    assert create_res2.status_code in (200, 201)
    job2 = create_res2.json()["job"]
    assert job2["name"] == "Weekday End-of-Day Database Vacuum"
    assert job2["schedule"] == "0 18 * * 1-5"
    assert job2["next_run"] is not None

    # 3. List all jobs for user
    list_res = await client.get("/api/v1/jobs", headers=headers)
    assert list_res.status_code == 200
    jobs = list_res.json()["jobs"]
    assert len(jobs) == 2
    job_ids = [j["id"] for j in jobs]
    assert job1["id"] in job_ids
    assert job2["id"] in job_ids


@pytest.mark.asyncio
async def test_job_status_lifecycle(client: httpx.AsyncClient) -> None:
    """User can toggle job status between Active and Pause."""
    uid = uuid.uuid4().hex[:8]
    headers, _ = await _get_auth(client, f"jobs_lifecycle_{uid}@example.com")

    # Create active job
    create_res = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "name": "Cloud Cost Optimization Sentinel",
            "schedule": "Daily",
            "timezone": "UTC",
        },
    )
    job_id = create_res.json()["job"]["id"]

    # Pause job
    pause_res = await client.patch(
        f"/api/v1/jobs/{job_id}/status",
        headers=headers,
        json={"status": "Pause"},
    )
    assert pause_res.status_code == 200
    paused_job = pause_res.json()["job"]
    assert paused_job["status"] == "Pause"

    # Resume job to Active
    resume_res = await client.patch(
        f"/api/v1/jobs/{job_id}/status",
        headers=headers,
        json={"status": "Active"},
    )
    assert resume_res.status_code == 200
    resumed_job = resume_res.json()["job"]
    assert resumed_job["status"] == "Active"
    assert resumed_job["next_run"] is not None


@pytest.mark.asyncio
async def test_job_run_now_and_execution_history(client: httpx.AsyncClient) -> None:
    """User can immediately trigger a job on-demand and inspect execution logs."""
    uid = uuid.uuid4().hex[:8]
    headers, _ = await _get_auth(client, f"jobs_exec_{uid}@example.com")

    # Create job
    create_res = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "name": "Immediate Sync Task",
            "description": "Test job for immediate manual execution",
            "schedule": "Every Monday at 9am",
            "timezone": "UTC",
        },
    )
    job_id = create_res.json()["job"]["id"]

    # 1. Trigger manual run
    run_res = await client.post(f"/api/v1/jobs/{job_id}/run", headers=headers)
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["status"] == "success"
    assert "execution" in run_data
    execution = run_data["execution"]
    assert execution["job_id"] == job_id
    assert execution["status"] == "success"
    assert execution["triggered_by"] == "manual"
    assert execution["duration_ms"] >= 0

    # 2. Fetch execution history
    hist_res = await client.get(f"/api/v1/jobs/{job_id}/history", headers=headers)
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    assert "executions" in hist_data
    assert len(hist_data["executions"]) >= 1
    first_run = hist_data["executions"][0]
    assert first_run["id"] == execution["id"]
    assert first_run["status"] == "success"


@pytest.mark.asyncio
async def test_job_deletion(client: httpx.AsyncClient) -> None:
    """User can delete a scheduled task and it is removed from listings."""
    uid = uuid.uuid4().hex[:8]
    headers, _ = await _get_auth(client, f"jobs_delete_{uid}@example.com")

    # Create job
    create_res = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "name": "Temporary Health Sentinel",
            "schedule": "Hourly",
        },
    )
    job_id = create_res.json()["job"]["id"]

    # Verify exists
    assert (await client.get(f"/api/v1/jobs/{job_id}", headers=headers)).status_code == 200

    # Delete job
    del_res = await client.delete(f"/api/v1/jobs/{job_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify 404 on get and not in list
    assert (await client.get(f"/api/v1/jobs/{job_id}", headers=headers)).status_code == 404
    all_jobs = (await client.get("/api/v1/jobs", headers=headers)).json()["jobs"]
    assert not any(j["id"] == job_id for j in all_jobs)


@pytest.mark.asyncio
async def test_strict_multitenant_isolation(client: httpx.AsyncClient) -> None:
    """User B cannot access, view, modify, run, or delete User A's scheduled jobs."""
    uid = uuid.uuid4().hex[:8]
    headers_a, user_a_id = await _get_auth(client, f"tenant_a_{uid}@example.com")
    headers_b, user_b_id = await _get_auth(client, f"tenant_b_{uid}@example.com")

    # User A creates a job
    create_res = await client.post(
        "/api/v1/jobs",
        headers=headers_a,
        json={
            "name": "User A Private Core ETL",
            "schedule": "Daily",
            "timezone": "UTC",
        },
    )
    job_a_id = create_res.json()["job"]["id"]

    # User B list jobs -> does NOT contain User A's job
    jobs_b = (await client.get("/api/v1/jobs", headers=headers_b)).json()["jobs"]
    assert not any(j["id"] == job_a_id for j in jobs_b)

    # User B attempts to get User A's job -> 404
    assert (await client.get(f"/api/v1/jobs/{job_a_id}", headers=headers_b)).status_code == 404

    # User B attempts to change status of User A's job -> 404
    assert (
        await client.patch(
            f"/api/v1/jobs/{job_a_id}/status",
            headers=headers_b,
            json={"status": "Pause"},
        )
    ).status_code == 404

    # User B attempts to run User A's job -> 404
    assert (await client.post(f"/api/v1/jobs/{job_a_id}/run", headers=headers_b)).status_code == 404

    # User B attempts to view User A's job history -> 404
    assert (await client.get(f"/api/v1/jobs/{job_a_id}/history", headers=headers_b)).status_code == 404

    # User B attempts to delete User A's job -> 404
    assert (await client.delete(f"/api/v1/jobs/{job_a_id}", headers=headers_b)).status_code == 404

    # Verify User A's job is still intact
    res_a = await client.get(f"/api/v1/jobs/{job_a_id}", headers=headers_a)
    assert res_a.status_code == 200
    assert res_a.json()["job"]["name"] == "User A Private Core ETL"


@pytest.mark.asyncio
async def test_automation_agent_chat_grounding(client: httpx.AsyncClient) -> None:
    """Automation Agent chat responses reflect live user jobs without cross-tenant leaks."""
    uid = uuid.uuid4().hex[:8]
    headers_a, _ = await _get_auth(client, f"chat_auto_a_{uid}@example.com")
    headers_b, _ = await _get_auth(client, f"chat_auto_b_{uid}@example.com")

    # User A schedules a unique task
    unique_task_name = f"Confidential Alpha Ingestion Pipeline {uid}"
    await client.post(
        "/api/v1/jobs",
        headers=headers_a,
        json={
            "name": unique_task_name,
            "schedule": "0 9 * * *",
            "timezone": "UTC",
        },
    )

    # User A asks the automation agent about scheduled tasks
    chat_payload = {
        "message": "What scheduled jobs do I currently have running?",
        "agent_override": "automation",
    }
    res_a = await client.post("/api/v1/runtime/chat", headers=headers_a, json=chat_payload)
    assert res_a.status_code == 200
    resp_text_a = res_a.json()["response"]

    # Must mention User A's unique job name
    assert unique_task_name in resp_text_a

    # User B asks the exact same question
    res_b = await client.post("/api/v1/runtime/chat", headers=headers_b, json=chat_payload)
    assert res_b.status_code == 200
    resp_text_b = res_b.json()["response"]

    # User B must NOT see User A's unique job name
    assert unique_task_name not in resp_text_b


@pytest.mark.asyncio
async def test_automation_agent_chat_offline_fallback(client: httpx.AsyncClient) -> None:
    """When LLM router fails, chat coordinator returns authentic offline fallback with scheduled jobs telemetry."""
    uid = uuid.uuid4().hex[:8]
    headers, _ = await _get_auth(client, f"chat_auto_offline_{uid}@example.com")

    # 1. Ask before creating any job -> 0 scheduled jobs message
    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Gateway timeout")):
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={"message": "Show me my scheduled jobs and recurring tasks.", "agent_override": "automation"},
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert data["agent_slug"] == "automation"
        assert "no scheduled automated jobs" in data["response"].lower()

    # 2. Create a job
    await client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "name": f"Nightly Cloud Snapshot Backup {uid}",
            "schedule": "0 2 * * *",
            "timezone": "UTC",
        },
    )

    # 3. Ask again -> returns live job count and job name
    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Gateway timeout")):
        chat_res2 = await client.post(
            "/api/v1/runtime/chat",
            headers=headers,
            json={"message": "Show me my scheduled jobs and recurring tasks.", "agent_override": "automation"},
        )
        assert chat_res2.status_code == 200
        data2 = chat_res2.json()
        assert data2["agent_slug"] == "automation"
        assert "1 automated job(s) configured" in data2["response"]
        assert f"Nightly Cloud Snapshot Backup {uid}" in data2["response"]


@pytest.mark.asyncio
async def test_automation_agent_chat_stream_grounding(client: httpx.AsyncClient) -> None:
    """Verify streaming chat runtime grounds scheduled jobs and automation state."""
    uid = uuid.uuid4().hex[:8]
    headers, _ = await _get_auth(client, f"chat_auto_stream_{uid}@example.com")

    # 1. Ask via stream before creating any job -> 0 jobs message
    resp_empty = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "Show me my scheduled jobs and recurring tasks.", "agent_override": "automation", "provider": "offline"},
        headers=headers,
    )
    assert resp_empty.status_code == 200
    empty_stream = resp_empty.text
    assert "data:" in empty_stream
    assert "no scheduled automated jobs" in empty_stream.lower()

    # 2. Create a scheduled job
    job_name = f"Weekend Security Audit Cron {uid}"
    create_res = await client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "name": job_name,
            "schedule": "0 4 * * 6",
            "timezone": "UTC",
        },
    )
    assert create_res.status_code in (200, 201)

    # 3. Ask via stream again -> confirms active automated job
    resp_one = await client.post(
        "/api/v1/runtime/chat/stream",
        json={"message": "Show me my scheduled jobs and recurring tasks.", "agent_override": "automation", "provider": "offline"},
        headers=headers,
    )
    assert resp_one.status_code == 200
    one_stream = resp_one.text
    assert "data:" in one_stream
    assert "1 automated job(s) configured" in one_stream
    assert job_name in one_stream
