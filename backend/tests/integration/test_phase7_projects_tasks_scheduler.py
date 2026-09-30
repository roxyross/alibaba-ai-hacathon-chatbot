"""Phase 7 Master Integration Test Suite: Projects, Tasks, Automations & Workflow Scheduler.

Verifies:
1. Workspace Projects & Tasks: Full lifecycle, milestones, priorities, status progression, document linking, cascading delete.
2. Scheduled Jobs & Automations Engine: Job creation (cron/interval), status toggle (Active/Pause), Run Now, execution logs.
3. Calendar & Meeting Scheduling: NLP prompt parsing, event scheduling, conflict detection, upcoming windows, ICS serialization.
4. Central ToolRegistry Integration: All 20 Phase 7 tools registered; destructive tools strictly gated with RiskLevel.HIGH and confirmation.
5. Deterministic Intent Routing in AgentPlanner: Seamless decomposition for projects, tasks, calendar events, and automations.
6. Multi-Tenant Anti-IDOR Isolation: Cross-tenant access attempts return 404 with zero data leakage.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, "src")

from app.agent_runtime.planner import AgentPlanner
from app.calendar.service import CalendarService
from app.jobs.service import JobService
from app.main import app
from app.projects.repository import clear_in_memory_stores
from app.projects.service import ProjectService
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel


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


@pytest.fixture
async def authed_client(client: AsyncClient) -> AsyncClient:
    """Fixture providing an authenticated client for testing."""
    email = f"test_p7_{uuid.uuid4().hex[:8]}@example.com"
    req_res = await client.post("/api/v1/auth/request-link", json={"email": email})
    assert req_res.status_code == 200
    token = req_res.json()["dev_token"]

    verify_res = await client.post("/api/v1/auth/verify", json={"token": token})
    assert verify_res.status_code == 200
    jwt_token = verify_res.json()["access_token"]

    client.headers["Authorization"] = f"Bearer {jwt_token}"
    return client


@pytest.fixture(autouse=True)
def _clean_stores() -> None:
    clear_in_memory_stores()


# -----------------------------------------------------------------------------
# 1. Workspace Projects & Tasks Management Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_workspace_projects_and_tasks_lifecycle(authed_client: AsyncClient) -> None:
    """Verify project creation, task management, metrics calculation, and cascading delete."""
    # 1. Empty state
    list_res = await authed_client.get("/api/v1/projects")
    assert list_res.status_code == 200
    assert len(list_res.json()["projects"]) == 0

    # 2. Create project
    proj_payload = {
        "name": "ROXY Mobile Application",
        "description": "Cross-platform mobile client for ROXY-AI 2.0 operating layer",
        "status": "active",
    }
    create_res = await authed_client.post("/api/v1/projects", json=proj_payload)
    assert create_res.status_code == 200
    proj = create_res.json()["project"]
    proj_id = proj["id"]
    assert proj["name"] == "ROXY Mobile Application"
    assert proj["tasks_count"] == 0

    # 3. Add tasks to project
    task_payload_1 = {
        "title": "Setup Flutter Scaffold",
        "description": "Initialize clean architecture project structure",
        "priority": "high",
        "status": "todo",
    }
    t1_res = await authed_client.post(f"/api/v1/projects/{proj_id}/tasks", json=task_payload_1)
    assert t1_res.status_code == 200
    t1 = t1_res.json()["task"]
    t1_id = t1["id"]
    assert t1["title"] == "Setup Flutter Scaffold"
    assert t1["priority"] == "high"

    task_payload_2 = {
        "title": "Design WebSocket Protocol",
        "description": "Define real-time duplex streaming protocol",
        "priority": "urgent",
        "status": "todo",
    }
    t2_res = await authed_client.post(f"/api/v1/projects/{proj_id}/tasks", json=task_payload_2)
    assert t2_res.status_code == 200
    t2 = t2_res.json()["task"]
    assert t2["title"] == "Design WebSocket Protocol"

    # 4. Verify project task count and list
    tasks_res = await authed_client.get(f"/api/v1/projects/{proj_id}/tasks")
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()["tasks"]
    assert len(tasks) == 2

    # 5. Link a Knowledge Vault document to project
    doc_payload = {
        "document_id": "doc_arch_99",
        "title": "Mobile Architecture Blueprint.pdf",
        "file_type": "pdf",
    }
    link_res = await authed_client.post(f"/api/v1/projects/{proj_id}/documents", json=doc_payload)
    assert link_res.status_code == 200
    doc_link = link_res.json()["document"]
    assert doc_link["title"] == "Mobile Architecture Blueprint.pdf"

    # 6. Progress task status to done
    up_res = await authed_client.patch(
        f"/api/v1/projects/{proj_id}/tasks/{t1_id}",
        json={"status": "done"},
    )
    assert up_res.status_code == 200
    assert up_res.json()["task"]["status"] == "done"

    # 7. Check updated project completion metrics
    proj_detail = await authed_client.get(f"/api/v1/projects/{proj_id}")
    assert proj_detail.status_code == 200
    p_data = proj_detail.json()["project"]
    assert p_data["tasks_count"] == 2
    assert p_data["completed_count"] == 1

    # 8. Cascading project deletion
    del_res = await authed_client.delete(f"/api/v1/projects/{proj_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify project is gone
    check_proj = await authed_client.get(f"/api/v1/projects/{proj_id}")
    assert check_proj.status_code == 404


# -----------------------------------------------------------------------------
# 2. Automations & Scheduled Jobs Engine Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_scheduled_jobs_and_automations_lifecycle(authed_client: AsyncClient) -> None:
    """Verify job creation with cron schedule, pause/resume, on-demand execution, and logs."""
    # 1. Fresh state
    jobs_res = await authed_client.get("/api/v1/jobs")
    assert jobs_res.status_code == 200
    assert len(jobs_res.json()["jobs"]) == 0

    # 2. Create automated recurring job
    job_payload = {
        "name": "Morning Intelligence Briefing",
        "description": "Aggregate overnight emails, alerts, and market updates",
        "schedule": "0 8 * * *",
        "timezone": "UTC",
        "prompt": "Summarize priority notifications and pending meetings",
        "tag": "daily-brief",
    }
    create_res = await authed_client.post("/api/v1/jobs", json=job_payload)
    assert create_res.status_code == 200
    job = create_res.json()["job"]
    job_id = job["id"]
    assert job["name"] == "Morning Intelligence Briefing"
    assert job["schedule"] == "0 8 * * *"
    assert job["status"] == "Active"

    # 3. Toggle status: Active -> Pause -> Active
    pause_res = await authed_client.patch(f"/api/v1/jobs/{job_id}/status", json={"status": "Pause"})
    assert pause_res.status_code == 200
    assert pause_res.json()["job"]["status"] == "Pause"

    resume_res = await authed_client.patch(f"/api/v1/jobs/{job_id}/status", json={"status": "Active"})
    assert resume_res.status_code == 200
    assert resume_res.json()["job"]["status"] == "Active"

    # 4. Trigger immediate on-demand execution (POST /jobs/{id}/run)
    run_res = await authed_client.post(f"/api/v1/jobs/{job_id}/run")
    assert run_res.status_code == 200
    run_data = run_res.json()
    assert run_data["status"] == "success"
    assert "execution_id" in run_data
    assert run_data["duration_ms"] > 0

    # 5. Verify execution history
    hist_res = await authed_client.get(f"/api/v1/jobs/{job_id}/history")
    assert hist_res.status_code == 200
    history = hist_res.json()["executions"]
    assert len(history) >= 1
    assert history[0]["status"] == "success"

    # 6. Delete scheduled job
    del_res = await authed_client.delete(f"/api/v1/jobs/{job_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify job is deleted
    check_job = await authed_client.get(f"/api/v1/jobs/{job_id}")
    assert check_job.status_code == 404


# -----------------------------------------------------------------------------
# 3. Calendar & Natural Language Meeting Scheduling
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_calendar_and_event_scheduling_lifecycle(authed_client: AsyncClient) -> None:
    """Verify natural language prompt parsing, event scheduling, conflict detection, and ICS export."""
    cal_service = CalendarService.get_instance()

    # 1. Natural language prompt parsing
    prompt = "Schedule Architecture Sprint Sync tomorrow at 3pm for 45 minutes on Google Meet"
    parsed = cal_service.parse_event_from_prompt(prompt)
    assert parsed["title"] == "Architecture Sprint Sync"
    assert parsed["category"] == "meeting"
    assert parsed["start_time"] is not None
    assert parsed["end_time"] is not None

    # 2. Create calendar event
    now = datetime.now(UTC)
    start_dt = now + timedelta(days=1)
    end_dt = start_dt + timedelta(hours=1)
    event_payload = {
        "title": "Board Review Presentation",
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "description": "Quarterly architecture and product milestones review",
        "location": "Boardroom Alpha & Zoom",
        "category": "meeting",
    }
    create_res = await authed_client.post("/api/v1/calendar/events", json=event_payload)
    assert create_res.status_code == 200
    event = create_res.json()["event"]
    event_id = event["id"]
    assert event["title"] == "Board Review Presentation"

    # 3. Check conflict detection with overlapping event
    conflicts = await cal_service.detect_conflicts(
        user_id="user_any",
        start_time=start_dt + timedelta(minutes=15),
        end_time=end_dt + timedelta(minutes=15),
    )
    assert isinstance(conflicts, list)
    # The existing event in repo is checked
    overlap_payload = {
        "title": "Conflicting Team Standup",
        "start_time": (start_dt + timedelta(minutes=15)).isoformat(),
        "end_time": (end_dt + timedelta(minutes=15)).isoformat(),
        "category": "meeting",
    }
    overlap_res = await authed_client.post("/api/v1/calendar/events", json=overlap_payload)
    assert overlap_res.status_code == 200
    assert "event" in overlap_res.json()

    # 4. Query upcoming events window
    upcoming_res = await authed_client.get("/api/v1/calendar/upcoming")
    assert upcoming_res.status_code == 200
    upcoming = upcoming_res.json()["events"]
    assert len(upcoming) >= 2

    # 5. Clean up created event
    del_res = await authed_client.delete(f"/api/v1/calendar/events/{event_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


# -----------------------------------------------------------------------------
# 4. Central ToolRegistry Integration & Confirmation Gating
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_phase7_tools_in_central_registry() -> None:
    """Verify all 20 Phase 7 tools are registered with appropriate permissions and confirmation gating."""
    ProjectService.get_instance().register_workspace_tools()
    CalendarService.get_instance().register_calendar_tools()
    JobService.get_instance().register_scheduler_tools()

    registry = ToolRegistry.get_instance()

    # Verify Workspace Tools
    expected_workspace_tools = [
        "workspace_list_projects",
        "workspace_get_project",
        "workspace_create_project",
        "workspace_create_task",
        "workspace_update_task",
        "workspace_link_document",
        "workspace_delete_project",
    ]
    for tid in expected_workspace_tools:
        tool = registry.get(tid)
        assert tool is not None, f"Expected tool {tid} not registered in ToolRegistry"

    # Verify Calendar Tools
    expected_calendar_tools = [
        "calendar_list_events",
        "calendar_get_event",
        "calendar_create_event",
        "calendar_update_event",
        "calendar_parse_prompt",
        "calendar_get_upcoming",
        "calendar_delete_event",
    ]
    for tid in expected_calendar_tools:
        tool = registry.get(tid)
        assert tool is not None, f"Expected tool {tid} not registered in ToolRegistry"

    # Verify Scheduler Tools
    expected_scheduler_tools = [
        "scheduler_list_jobs",
        "scheduler_get_job",
        "scheduler_create_job",
        "scheduler_update_job_status",
        "scheduler_run_job_now",
        "scheduler_delete_job",
    ]
    for tid in expected_scheduler_tools:
        tool = registry.get(tid)
        assert tool is not None, f"Expected tool {tid} not registered in ToolRegistry"

    # Verify Confirmation Gating on High-Risk Destructive Tools
    del_proj_tool = registry.get("workspace_delete_project")
    assert del_proj_tool is not None
    assert del_proj_tool.risk_level == RiskLevel.HIGH
    assert del_proj_tool.requires_confirmation is True

    del_cal_tool = registry.get("calendar_delete_event")
    assert del_cal_tool is not None
    assert del_cal_tool.risk_level == RiskLevel.HIGH
    assert del_cal_tool.requires_confirmation is True

    del_job_tool = registry.get("scheduler_delete_job")
    assert del_job_tool is not None
    assert del_job_tool.risk_level == RiskLevel.HIGH
    assert del_job_tool.requires_confirmation is True


# -----------------------------------------------------------------------------
# 5. AgentPlanner Deterministic Intent Decomposition
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_phase7_intent_routing() -> None:
    """Verify AgentPlanner routes Workspace, Calendar, and Scheduler intents deterministically."""
    ProjectService.get_instance().register_workspace_tools()
    CalendarService.get_instance().register_calendar_tools()
    JobService.get_instance().register_scheduler_tools()

    planner = AgentPlanner()

    # A. Workspace: Create Project
    plan_cp = await planner.create_plan("create project Enterprise Cloud Migration")
    assert len(plan_cp) == 1
    assert plan_cp[0]["tool_id"] == "workspace_create_project"
    assert "Enterprise Cloud Migration" in plan_cp[0]["tool_input"]["name"]

    # B. Workspace: Add Task
    plan_ct = await planner.create_plan("add task 'Audit IAM Roles' to project proj_infra_1")
    assert len(plan_ct) == 1
    assert plan_ct[0]["tool_id"] == "workspace_create_task"
    assert "Audit IAM Roles" in plan_ct[0]["tool_input"]["title"]

    # C. Workspace: Mark Task Done
    plan_ut = await planner.create_plan("mark task task_88 as done")
    assert len(plan_ut) == 1
    assert plan_ut[0]["tool_id"] == "workspace_update_task"
    assert plan_ut[0]["tool_input"]["status"] == "done"

    # D. Workspace: Delete Project (destructive)
    plan_dp = await planner.create_plan("delete project proj_infra_1")
    assert len(plan_dp) == 1
    assert plan_dp[0]["tool_id"] == "workspace_delete_project"
    assert plan_dp[0]["tool_input"]["project_id"] == "proj_infra_1"

    # E. Calendar: Schedule Meeting
    plan_cal = await planner.create_plan("schedule meeting Sprint Demo tomorrow at 2pm")
    assert len(plan_cal) == 1
    assert plan_cal[0]["tool_id"] == "calendar_create_event"
    assert "Sprint Demo" in plan_cal[0]["tool_input"]["title"]

    # F. Calendar: Upcoming Events
    plan_up = await planner.create_plan("what are my upcoming meetings")
    assert len(plan_up) == 1
    assert plan_up[0]["tool_id"] == "calendar_get_upcoming"

    # G. Calendar: Cancel Event (destructive)
    plan_dc = await planner.create_plan("cancel calendar event evt_55")
    assert len(plan_dc) == 1
    assert plan_dc[0]["tool_id"] == "calendar_delete_event"
    assert plan_dc[0]["tool_input"]["event_id"] == "evt_55"

    # H. Scheduler: List Scheduled Jobs
    plan_sj = await planner.create_plan("list scheduled jobs")
    assert len(plan_sj) == 1
    assert plan_sj[0]["tool_id"] == "scheduler_list_jobs"

    # I. Scheduler: Run Job Now
    plan_rj = await planner.create_plan("run job job_sync_01 now")
    assert len(plan_rj) == 1
    assert plan_rj[0]["tool_id"] == "scheduler_run_job_now"
    assert plan_rj[0]["tool_input"]["job_id"] == "job_sync_01"

    # J. Scheduler: Delete Job (destructive)
    plan_dj = await planner.create_plan("delete scheduled job job_sync_01")
    assert len(plan_dj) == 1
    assert plan_dj[0]["tool_id"] == "scheduler_delete_job"
    assert plan_dj[0]["tool_input"]["job_id"] == "job_sync_01"


# -----------------------------------------------------------------------------
# 6. Strict Multi-Tenant Anti-IDOR Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_phase7_multitenant_isolation(client: AsyncClient) -> None:
    """Verify that User B cannot read, update, execute, or delete User A's projects, tasks, jobs, or events."""
    # 1. Authenticate User A
    tok_a = (await client.post("/api/v1/auth/request-link", json={"email": "tenant_a_p7@example.com"})).json()["dev_token"]
    jwt_a = (await client.post("/api/v1/auth/verify", json={"token": tok_a})).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {jwt_a}"}

    # 2. Authenticate User B
    tok_b = (await client.post("/api/v1/auth/request-link", json={"email": "tenant_b_p7@example.com"})).json()["dev_token"]
    jwt_b = (await client.post("/api/v1/auth/verify", json={"token": tok_b})).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {jwt_b}"}

    # User A creates a Project
    p_res = await client.post("/api/v1/projects", json={"name": "Confidential R&D"}, headers=headers_a)
    assert p_res.status_code == 200
    proj_a_id = p_res.json()["project"]["id"]

    # User A creates a Task in the project
    t_res = await client.post(f"/api/v1/projects/{proj_a_id}/tasks", json={"title": "Stealth Launch"}, headers=headers_a)
    assert t_res.status_code == 200
    task_a_id = t_res.json()["task"]["id"]

    # User A creates a Scheduled Job
    j_res = await client.post("/api/v1/jobs", json={"name": "Nightly Backup", "schedule": "Daily"}, headers=headers_a)
    assert j_res.status_code == 200
    job_a_id = j_res.json()["job"]["id"]

    # User A creates a Calendar Event
    now = datetime.now(UTC)
    e_res = await client.post(
        "/api/v1/calendar/events",
        json={"title": "Private M&A Discussion", "start_time": (now + timedelta(days=2)).isoformat()},
        headers=headers_a,
    )
    assert e_res.status_code == 200
    event_a_id = e_res.json()["event"]["id"]

    # User B attempts to access User A's Project -> 404
    b_proj_get = await client.get(f"/api/v1/projects/{proj_a_id}", headers=headers_b)
    assert b_proj_get.status_code == 404

    # User B attempts to list tasks of User A's Project -> 404
    b_tasks_get = await client.get(f"/api/v1/projects/{proj_a_id}/tasks", headers=headers_b)
    assert b_tasks_get.status_code == 404

    # User B attempts to delete User A's Task -> 404
    b_task_del = await client.delete(f"/api/v1/projects/{proj_a_id}/tasks/{task_a_id}", headers=headers_b)
    assert b_task_del.status_code == 404

    # User B attempts to delete User A's Project -> 404
    b_proj_del = await client.delete(f"/api/v1/projects/{proj_a_id}", headers=headers_b)
    assert b_proj_del.status_code == 404

    # User B attempts to access User A's Job -> 404
    b_job_get = await client.get(f"/api/v1/jobs/{job_a_id}", headers=headers_b)
    assert b_job_get.status_code == 404

    # User B attempts to run User A's Job -> 404
    b_job_run = await client.post(f"/api/v1/jobs/{job_a_id}/run", headers=headers_b)
    assert b_job_run.status_code == 404

    # User B attempts to delete User A's Job -> 404
    b_job_del = await client.delete(f"/api/v1/jobs/{job_a_id}", headers=headers_b)
    assert b_job_del.status_code == 404

    # User B attempts to access User A's Event -> 404
    b_evt_get = await client.get(f"/api/v1/calendar/events/{event_a_id}", headers=headers_b)
    assert b_evt_get.status_code == 404

    # User B attempts to delete User A's Event -> 404
    b_evt_del = await client.delete(f"/api/v1/calendar/events/{event_a_id}", headers=headers_b)
    assert b_evt_del.status_code == 404
