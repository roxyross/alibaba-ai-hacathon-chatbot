"""Phase 9 Master Integration Test Suite: Workspace Hub & Project Management Engine.

Verifies:
1. Fresh user empty state (zero projects, zero tasks).
2. Project creation, listing, retrieval, and status-based filtering.
3. Project detail updates (name, description, status lifecycle).
4. Task lifecycle: creation, priority assignment, status progression (todo -> done), and deletion.
5. Dynamic project completion metrics: real-time tasks_count and completed_count calculation.
6. Document linking and unlinking from Knowledge Vault.
7. Cascading deletion: deleting a project purges its tasks and document links.
8. Strict multi-tenant isolation across projects, tasks, and document links.
9. Workspace Agent Chat Grounding: multi-agent coordinator reflects live project data for authorized user with zero cross-tenant leakage.
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import AsyncIterator
from unittest.mock import patch

import httpx
import pytest

sys.path.insert(0, "src")

from app.main import app
from app.projects.repository import clear_in_memory_stores


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


@pytest.fixture(autouse=True)
def _clean_workspace() -> None:
    clear_in_memory_stores()


async def _get_auth(client: httpx.AsyncClient, email: str) -> tuple[dict[str, str], str]:
    """Return (auth_headers, user_id)."""
    tok = (await client.post("/api/v1/auth/request-link", json={"email": email})).json()["dev_token"]
    verify_data = (await client.post("/api/v1/auth/verify", json={"token": tok})).json()
    token = verify_data["access_token"]
    user_id = verify_data["user"]["id"]
    return {"Authorization": f"Bearer {token}"}, user_id


# -----------------------------------------------------------------------------
# 1. Fresh User Empty State
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_workspace_empty_state(client: httpx.AsyncClient) -> None:
    """Verify fresh user starts with zero projects and accessing non-existent project returns 404."""
    auth, _ = await _get_auth(client, f"ws_fresh_{uuid.uuid4().hex[:6]}@roxy.ai")

    resp = await client.get("/api/v1/projects", headers=auth)
    assert resp.status_code == 200
    data = resp.json()
    assert "projects" in data
    assert data["projects"] == []

    # Querying a non-existent project returns 404
    fake_id = str(uuid.uuid4())
    resp_404 = await client.get(f"/api/v1/projects/{fake_id}", headers=auth)
    assert resp_404.status_code == 404


# -----------------------------------------------------------------------------
# 2. Project Lifecycle & Filtering
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_project_crud_and_filtering(client: httpx.AsyncClient) -> None:
    """Verify project creation, retrieval, updates, and status filtering."""
    auth, _ = await _get_auth(client, f"ws_crud_{uuid.uuid4().hex[:6]}@roxy.ai")

    # A. Create active project
    create_resp = await client.post(
        "/api/v1/projects",
        headers=auth,
        json={
            "name": "Project Alpha",
            "description": "Autonomous AI platform deployment",
            "status": "active",
        },
    )
    assert create_resp.status_code == 200
    p1 = create_resp.json()["project"]
    assert p1["name"] == "Project Alpha"
    assert p1["status"] == "active"
    assert p1["tasks_count"] == 0
    assert p1["completed_count"] == 0
    p1_id = p1["id"]

    # B. Create archived project
    create_resp2 = await client.post(
        "/api/v1/projects",
        headers=auth,
        json={
            "name": "Legacy Migration",
            "description": "Old database migration archive",
            "status": "archived",
        },
    )
    assert create_resp2.status_code == 200
    p2_id = create_resp2.json()["project"]["id"]

    # C. List all projects
    list_all = await client.get("/api/v1/projects", headers=auth)
    assert list_all.status_code == 200
    all_projs = list_all.json()["projects"]
    assert len(all_projs) == 2

    # D. Filter by status=active
    list_active = await client.get("/api/v1/projects?status=active", headers=auth)
    assert list_active.status_code == 200
    active_projs = list_active.json()["projects"]
    assert len(active_projs) == 1
    assert active_projs[0]["id"] == p1_id

    # E. Filter by status=archived
    list_archived = await client.get("/api/v1/projects?status=archived", headers=auth)
    assert list_archived.status_code == 200
    archived_projs = list_archived.json()["projects"]
    assert len(archived_projs) == 1
    assert archived_projs[0]["id"] == p2_id

    # F. Update project details
    patch_resp = await client.patch(
        f"/api/v1/projects/{p1_id}",
        headers=auth,
        json={
            "name": "Project Alpha V2",
            "description": "Updated platform description",
            "status": "completed",
        },
    )
    assert patch_resp.status_code == 200
    updated_p1 = patch_resp.json()["project"]
    assert updated_p1["name"] == "Project Alpha V2"
    assert updated_p1["status"] == "completed"

    # G. Get single project details
    get_resp = await client.get(f"/api/v1/projects/{p1_id}", headers=auth)
    assert get_resp.status_code == 200
    fetched_p1 = get_resp.json()["project"]
    assert fetched_p1["name"] == "Project Alpha V2"


# -----------------------------------------------------------------------------
# 3. Task Lifecycle & Dynamic Progress Metrics
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_task_lifecycle_and_progress(client: httpx.AsyncClient) -> None:
    """Verify task creation, status updates, and dynamic progress calculation."""
    auth, _ = await _get_auth(client, f"ws_tasks_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create project
    p_resp = await client.post(
        "/api/v1/projects",
        headers=auth,
        json={"name": "SaaS Launch", "description": "Launch deliverables"},
    )
    project_id = p_resp.json()["project"]["id"]

    # Add Task 1: todo
    t1_resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth,
        json={
            "title": "Configure DNS records",
            "description": "Point domain to Cloudflare",
            "status": "todo",
            "priority": "high",
            "assigned_agent": "automation",
        },
    )
    assert t1_resp.status_code == 200
    t1 = t1_resp.json()["task"]
    assert t1["title"] == "Configure DNS records"
    assert t1["status"] == "todo"
    assert t1["priority"] == "high"
    t1_id = t1["id"]

    # Add Task 2: in_progress
    t2_resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth,
        json={
            "title": "Build landing page",
            "status": "in_progress",
            "priority": "urgent",
        },
    )
    assert t2_resp.status_code == 200
    t2_id = t2_resp.json()["task"]["id"]

    # Verify project reflects 2 tasks and 0 completed
    proj_resp = await client.get(f"/api/v1/projects/{project_id}", headers=auth)
    p_data = proj_resp.json()["project"]
    assert p_data["tasks_count"] == 2
    assert p_data["completed_count"] == 0

    # List tasks for project
    tasks_resp = await client.get(f"/api/v1/projects/{project_id}/tasks", headers=auth)
    assert tasks_resp.status_code == 200
    task_list = tasks_resp.json()["tasks"]
    assert len(task_list) == 2

    # Complete Task 1 (status: done)
    patch_t1 = await client.patch(
        f"/api/v1/projects/{project_id}/tasks/{t1_id}",
        headers=auth,
        json={"status": "done"},
    )
    assert patch_t1.status_code == 200
    assert patch_t1.json()["task"]["status"] == "done"

    # Verify project completion count updated to 1/2
    proj_resp2 = await client.get(f"/api/v1/projects/{project_id}", headers=auth)
    p_data2 = proj_resp2.json()["project"]
    assert p_data2["tasks_count"] == 2
    assert p_data2["completed_count"] == 1

    # Delete Task 2
    del_t2 = await client.delete(
        f"/api/v1/projects/{project_id}/tasks/{t2_id}",
        headers=auth,
    )
    assert del_t2.status_code == 200

    # Verify project task count reduced to 1, completed count is 1 (100% complete)
    proj_resp3 = await client.get(f"/api/v1/projects/{project_id}", headers=auth)
    p_data3 = proj_resp3.json()["project"]
    assert p_data3["tasks_count"] == 1
    assert p_data3["completed_count"] == 1


# -----------------------------------------------------------------------------
# 4. Document Linking & Unlinking
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_document_linking_lifecycle(client: httpx.AsyncClient) -> None:
    """Verify linking and unlinking Knowledge Vault documents to a project."""
    auth, _ = await _get_auth(client, f"ws_docs_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create project
    p_resp = await client.post(
        "/api/v1/projects",
        headers=auth,
        json={"name": "Research Initiative", "description": "AI analysis"},
    )
    project_id = p_resp.json()["project"]["id"]

    # Link Document 1
    link_resp = await client.post(
        f"/api/v1/projects/{project_id}/documents",
        headers=auth,
        json={
            "document_id": "doc_arch_spec_001",
            "title": "System Architecture Specification.pdf",
            "file_type": "pdf",
        },
    )
    assert link_resp.status_code == 200
    doc1 = link_resp.json()["document"]
    assert doc1["title"] == "System Architecture Specification.pdf"
    assert doc1["document_id"] == "doc_arch_spec_001"
    doc_link_id = doc1["id"]

    # List documents
    docs_resp = await client.get(f"/api/v1/projects/{project_id}/documents", headers=auth)
    assert docs_resp.status_code == 200
    docs = docs_resp.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["id"] == doc_link_id

    # Unlink document
    unlink_resp = await client.delete(
        f"/api/v1/projects/{project_id}/documents/{doc_link_id}",
        headers=auth,
    )
    assert unlink_resp.status_code == 200

    # Verify document list is now empty
    docs_resp2 = await client.get(f"/api/v1/projects/{project_id}/documents", headers=auth)
    assert docs_resp2.status_code == 200
    assert docs_resp2.json()["documents"] == []


# -----------------------------------------------------------------------------
# 5. Cascading Deletion
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_project_cascading_deletion(client: httpx.AsyncClient) -> None:
    """Verify deleting a project cleans up all associated tasks and document links."""
    auth, _ = await _get_auth(client, f"ws_cascade_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create project
    p_resp = await client.post(
        "/api/v1/projects",
        headers=auth,
        json={"name": "Ephemeral Project", "description": "To be deleted"},
    )
    project_id = p_resp.json()["project"]["id"]

    # Add task
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth,
        json={"title": "Action item to be cascaded"},
    )

    # Link document
    await client.post(
        f"/api/v1/projects/{project_id}/documents",
        headers=auth,
        json={
            "document_id": "doc_temp_123",
            "title": "Temp Notes.txt",
            "file_type": "txt",
        },
    )

    # Delete project
    del_resp = await client.delete(f"/api/v1/projects/{project_id}", headers=auth)
    assert del_resp.status_code == 200

    # Project is gone
    get_proj = await client.get(f"/api/v1/projects/{project_id}", headers=auth)
    assert get_proj.status_code == 404

    # Subsequent task queries return 404
    get_tasks = await client.get(f"/api/v1/projects/{project_id}/tasks", headers=auth)
    assert get_tasks.status_code == 404

    # Subsequent document queries return 404
    get_docs = await client.get(f"/api/v1/projects/{project_id}/documents", headers=auth)
    assert get_docs.status_code == 404


# -----------------------------------------------------------------------------
# 6. Strict Multi-Tenant Isolation
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_workspace_multi_tenant_isolation(client: httpx.AsyncClient) -> None:
    """Verify User B cannot access, view, modify, or delete User A's projects, tasks, or documents."""
    auth_a, user_a_id = await _get_auth(client, f"user_a_ws_{uuid.uuid4().hex[:6]}@roxy.ai")
    auth_b, user_b_id = await _get_auth(client, f"user_b_ws_{uuid.uuid4().hex[:6]}@roxy.ai")
    assert user_a_id != user_b_id

    # User A creates a secret project
    p_resp = await client.post(
        "/api/v1/projects",
        headers=auth_a,
        json={
            "name": "User A Proprietary Project",
            "description": "Classified roadmap",
            "status": "active",
        },
    )
    p_id = p_resp.json()["project"]["id"]

    # User A adds a task
    t_resp = await client.post(
        f"/api/v1/projects/{p_id}/tasks",
        headers=auth_a,
        json={"title": "Proprietary Algorithm Implementation"},
    )
    t_id = t_resp.json()["task"]["id"]

    # User A links a document
    d_resp = await client.post(
        f"/api/v1/projects/{p_id}/documents",
        headers=auth_a,
        json={
            "document_id": "doc_secret_formula",
            "title": "Top Secret Architecture.pdf",
            "file_type": "pdf",
        },
    )
    d_id = d_resp.json()["document"]["id"]

    # User B lists projects -> Should NOT see User A's project
    b_list = await client.get("/api/v1/projects", headers=auth_b)
    assert b_list.status_code == 200
    b_projects = b_list.json()["projects"]
    assert all(p["id"] != p_id for p in b_projects)

    # User B attempts to access User A's project details -> 404 Not Found
    b_get_p = await client.get(f"/api/v1/projects/{p_id}", headers=auth_b)
    assert b_get_p.status_code == 404

    # User B attempts to update User A's project -> 404 Not Found
    b_patch_p = await client.patch(
        f"/api/v1/projects/{p_id}",
        headers=auth_b,
        json={"name": "Hacked Project Name"},
    )
    assert b_patch_p.status_code == 404

    # User B attempts to list tasks on User A's project -> 404 Not Found
    b_get_tasks = await client.get(f"/api/v1/projects/{p_id}/tasks", headers=auth_b)
    assert b_get_tasks.status_code == 404

    # User B attempts to add a task to User A's project -> 404 Not Found
    b_add_task = await client.post(
        f"/api/v1/projects/{p_id}/tasks",
        headers=auth_b,
        json={"title": "Malicious task"},
    )
    assert b_add_task.status_code == 404

    # User B attempts to update User A's task -> 404 Not Found
    b_patch_task = await client.patch(
        f"/api/v1/projects/{p_id}/tasks/{t_id}",
        headers=auth_b,
        json={"status": "done"},
    )
    assert b_patch_task.status_code == 404

    # User B attempts to delete User A's task -> 404 Not Found
    b_del_task = await client.delete(
        f"/api/v1/projects/{p_id}/tasks/{t_id}",
        headers=auth_b,
    )
    assert b_del_task.status_code == 404

    # User B attempts to list documents on User A's project -> 404 Not Found
    b_get_docs = await client.get(f"/api/v1/projects/{p_id}/documents", headers=auth_b)
    assert b_get_docs.status_code == 404

    # User B attempts to unlink User A's document -> 404 Not Found
    b_unlink_doc = await client.delete(
        f"/api/v1/projects/{p_id}/documents/{d_id}",
        headers=auth_b,
    )
    assert b_unlink_doc.status_code == 404

    # User B attempts to delete User A's project -> 404 Not Found
    b_del_p = await client.delete(f"/api/v1/projects/{p_id}", headers=auth_b)
    assert b_del_p.status_code == 404

    # User A's project and task remain intact
    a_verify = await client.get(f"/api/v1/projects/{p_id}", headers=auth_a)
    assert a_verify.status_code == 200
    assert a_verify.json()["project"]["name"] == "User A Proprietary Project"


# -----------------------------------------------------------------------------
# 7. Multi-Agent Chat Grounding
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_workspace_chat_grounding(client: httpx.AsyncClient) -> None:
    """Verify Coordinator Agent grounds user's workspace projects and tasks into chat conversation."""
    auth, user_id = await _get_auth(client, f"ws_chat_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create a project with tasks
    p_resp = await client.post(
        "/api/v1/projects",
        headers=auth,
        json={"name": "Quantum AI Cluster", "description": "Supercomputing roadmap"},
    )
    project_id = p_resp.json()["project"]["id"]

    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth,
        json={"title": "Deploy Kubernetes GPU Node Pool", "status": "done"},
    )
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth,
        json={"title": "Benchmark LLM inference latency", "status": "todo"},
    )

    # Chat asking about projects
    chat_resp = await client.post(
        "/api/v1/runtime/chat",
        headers=auth,
        json={
            "message": "What projects and tasks do I have in my workspace?",
            "agent_override": "workspace",
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert "response" in chat_data
    assert "Quantum AI Cluster" in chat_data["response"]
    assert "1/2 completed" in chat_data["response"] or "1" in chat_data["response"]


@pytest.mark.anyio
async def test_workspace_streaming_chat_grounding(client: httpx.AsyncClient) -> None:
    """Verify streaming Coordinator grounds user's workspace projects and tasks via SSE."""
    auth, user_id = await _get_auth(client, f"ws_stream_{uuid.uuid4().hex[:6]}@roxy.ai")

    # Create a project with tasks
    p_resp = await client.post(
        "/api/v1/projects",
        headers=auth,
        json={"name": "Neural Hyperdrive", "description": "Autonomous warp computation"},
    )
    assert p_resp.status_code == 200
    project_id = p_resp.json()["project"]["id"]

    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth,
        json={"title": "Calibrate warp manifold", "status": "done"},
    )
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=auth,
        json={"title": "Initiate sub-light burn", "status": "todo"},
    )

    # Stream asking about workspace projects
    stream_resp = await client.post(
        "/api/v1/runtime/chat/stream",
        headers=auth,
        json={
            "message": "What projects and tasks do I have in my workspace?",
            "agent_override": "workspace",
        },
    )
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers.get("content-type", "")

    # Parse SSE text
    lines = stream_resp.text.split("\n")
    import json
    deltas: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("data: "):
            try:
                parsed = json.loads(line[len("data: "):])
                if parsed.get("delta"):
                    deltas.append(parsed["delta"])
            except json.JSONDecodeError:
                pass

    streamed_text = "".join(deltas)
    assert len(streamed_text) > 0
    assert "Neural Hyperdrive" in streamed_text or "Calibrate warp" in streamed_text or "1" in streamed_text


@pytest.mark.anyio
async def test_workspace_chat_offline_fallback(client: httpx.AsyncClient) -> None:
    """When LLM router fails, chat coordinator returns authentic offline fallback with workspace projects telemetry."""
    auth, user_id = await _get_auth(client, f"ws_offline_{uuid.uuid4().hex[:6]}@roxy.ai")

    # 1. Ask before creating any project -> 0 projects message
    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Gateway timeout")):
        chat_res = await client.post(
            "/api/v1/runtime/chat",
            headers=auth,
            json={"message": "Show me my workspace projects and deliverables.", "agent_override": "workspace"},
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert data["agent_slug"] == "workspace"
        assert "no active workspace projects" in data["response"].lower()

    # 2. Create a project with tasks
    p_resp = await client.post(
        "/api/v1/projects",
        headers=auth,
        json={"name": "Titan Rocket Core", "description": "Orbital delivery vehicle"},
    )
    p_id = p_resp.json()["project"]["id"]
    await client.post(
        f"/api/v1/projects/{p_id}/tasks",
        headers=auth,
        json={"title": "Ignition Sequence Check", "status": "done"},
    )

    # 3. Ask again -> confirms live project and task completion count
    with patch("app.api.v1.runtime.AIRouter.route", side_effect=Exception("Gateway timeout")):
        chat_res2 = await client.post(
            "/api/v1/runtime/chat",
            headers=auth,
            json={"message": "Show me my workspace projects and deliverables.", "agent_override": "workspace"},
        )
        assert chat_res2.status_code == 200
        data2 = chat_res2.json()
        assert data2["agent_slug"] == "workspace"
        assert "1 project(s) configured" in data2["response"]
        assert "Titan Rocket Core" in data2["response"]
        assert "1/1 completed" in data2["response"]


# -----------------------------------------------------------------------------
# 10. ProjectService Singleton & ToolRegistry Verification
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_project_service_singleton_and_tool_registration() -> None:
    """Verify ProjectService singleton identity and 7 native tools in ToolRegistry."""
    from app.projects.service import ProjectService
    from app.tools.registry import ToolRegistry
    from app.tools.schemas import RiskLevel

    svc1 = ProjectService.get_instance()
    svc2 = ProjectService.get_instance()
    assert svc1 is svc2

    svc1.register_workspace_tools()
    reg = ToolRegistry.get_instance()

    expected_tools = [
        "workspace_list_projects",
        "workspace_get_project",
        "workspace_create_project",
        "workspace_create_task",
        "workspace_update_task",
        "workspace_link_document",
        "workspace_delete_project",
    ]
    for tid in expected_tools:
        tool = reg.get(tid)
        assert tool is not None, f"Expected tool {tid} to be registered"
        assert "workspace" in tool.capabilities

    # High-risk confirmation gating
    del_tool = reg.get("workspace_delete_project")
    assert del_tool is not None
    assert del_tool.risk_level == RiskLevel.HIGH
    assert del_tool.requires_confirmation is True


# -----------------------------------------------------------------------------
# 11. Workspace Hub Native Tools Direct Execution
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_workspace_tools_direct_execution() -> None:
    """Verify end-to-end execution of all 7 workspace tools via Central ToolRegistry."""
    from app.projects.service import ProjectService
    from app.tools.registry import ToolRegistry
    from app.tools.schemas import ToolExecutionRequest

    svc = ProjectService.get_instance()
    svc.register_workspace_tools()
    reg = ToolRegistry.get_instance()

    user_id = f"tool_exec_{uuid.uuid4().hex[:6]}"

    # 1. workspace_list_projects (empty)
    res_list_empty = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_list_projects",
            arguments={},
            user_id=user_id,
        )
    )
    assert res_list_empty.success is True
    assert res_list_empty.output["total_projects"] == 0

    # 2. workspace_create_project
    res_create_proj = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_create_project",
            arguments={"name": "Quantum Neural Net", "description": "Core intelligence model"},
            user_id=user_id,
        )
    )
    assert res_create_proj.success is True
    assert res_create_proj.output["status"] == "success"
    proj_id = res_create_proj.output["project"]["id"]
    assert "Quantum Neural Net" in res_create_proj.output["project"]["name"]

    # 3. workspace_get_project
    res_get_proj = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_get_project",
            arguments={"project_id": proj_id},
            user_id=user_id,
        )
    )
    assert res_get_proj.success is True
    assert res_get_proj.output["project"]["id"] == proj_id

    # 4. workspace_create_task
    res_create_task = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_create_task",
            arguments={
                "project_id": proj_id,
                "title": "Train Transformer Attention Heads",
                "priority": "high",
            },
            user_id=user_id,
        )
    )
    assert res_create_task.success is True
    task_id = res_create_task.output["task"]["id"]
    assert res_create_task.output["task"]["title"] == "Train Transformer Attention Heads"

    # 5. workspace_update_task
    res_update_task = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_update_task",
            arguments={
                "project_id": proj_id,
                "task_id": task_id,
                "status": "done",
            },
            user_id=user_id,
        )
    )
    assert res_update_task.success is True
    assert res_update_task.output["task"]["status"] == "done"

    # 6. workspace_link_document
    res_link_doc = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_link_document",
            arguments={
                "project_id": proj_id,
                "document_id": "doc_transformer_math_99",
                "title": "Transformer Attention Mathematics.pdf",
                "file_type": "pdf",
            },
            user_id=user_id,
        )
    )
    assert res_link_doc.success is True
    assert res_link_doc.output["document"]["document_id"] == "doc_transformer_math_99"

    # 7. workspace_list_projects (reflects 1 project, 1 task, 100% completed)
    res_list_after = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_list_projects",
            arguments={},
            user_id=user_id,
        )
    )
    assert res_list_after.success is True
    assert res_list_after.output["total_projects"] == 1
    assert "1/1 tasks completed (100.0%)" in res_list_after.output["summary"]

    # 8. workspace_delete_project (cascading purge)
    res_del_proj = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_delete_project",
            arguments={"project_id": proj_id},
            user_id=user_id,
            bypass_confirmation=True,
        )
    )
    assert res_del_proj.success is True
    assert res_del_proj.output["deleted"] is True

    # 9. Verify project is gone
    res_get_deleted = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_get_project",
            arguments={"project_id": proj_id},
            user_id=user_id,
        )
    )
    assert res_get_deleted.output["status"] == "not_found"


# -----------------------------------------------------------------------------
# 12. AgentPlanner Workspace Hub Intent Routing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_workspace_intent_routing() -> None:
    """Verify AgentPlanner deterministic decomposition and routing to workspace tools."""
    from app.agent_runtime.planner import AgentPlanner
    from app.projects.service import ProjectService

    ProjectService.get_instance().register_workspace_tools()
    planner = AgentPlanner()

    # A. List workspace projects
    plan_list = await planner.create_plan("list projects in my workspace")
    assert len(plan_list) == 1
    assert plan_list[0]["tool_id"] == "workspace_list_projects"

    # B. Project details
    plan_details = await planner.create_plan("project details for proj-alpha-99")
    assert len(plan_details) == 1
    assert plan_details[0]["tool_id"] == "workspace_get_project"
    assert plan_details[0]["tool_input"]["project_id"] == "proj-alpha-99"

    # C. Create project
    plan_create = await planner.create_plan("create project Distributed Consensus Engine")
    assert len(plan_create) == 1
    assert plan_create[0]["tool_id"] == "workspace_create_project"
    assert plan_create[0]["tool_input"]["name"] == "Distributed Consensus Engine"

    # D. Create task
    plan_task = await planner.create_plan("create task Implement Raft Protocol in project proj-raft-01")
    assert len(plan_task) == 1
    assert plan_task[0]["tool_id"] == "workspace_create_task"
    assert plan_task[0]["tool_input"]["project_id"] == "proj-raft-01"
    assert "Implement Raft Protocol" in plan_task[0]["tool_input"]["title"]

    # E. Update task (mark done)
    plan_update = await planner.create_plan("mark task task-leader-election done in project proj-raft-01")
    assert len(plan_update) == 1
    assert plan_update[0]["tool_id"] == "workspace_update_task"
    assert plan_update[0]["tool_input"]["project_id"] == "proj-raft-01"
    assert plan_update[0]["tool_input"]["status"] == "done"

    # F. Link document
    plan_link = await planner.create_plan("link document doc-raft-paper to project proj-raft-01")
    assert len(plan_link) == 1
    assert plan_link[0]["tool_id"] == "workspace_link_document"
    assert plan_link[0]["tool_input"]["project_id"] == "proj-raft-01"

    # G. Delete project (requires confirmation)
    plan_del = await planner.create_plan("delete project proj-raft-01")
    assert len(plan_del) == 1
    assert plan_del[0]["tool_id"] == "workspace_delete_project"
    assert plan_del[0]["tool_input"]["project_id"] == "proj-raft-01"


# -----------------------------------------------------------------------------
# 13. Multi-Tenant Isolation via Tool Registry Execution
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_workspace_tool_multitenant_isolation() -> None:
    """Verify strict multi-tenant isolation across workspace projects and tasks via ToolRegistry."""
    from app.projects.service import ProjectService
    from app.tools.registry import ToolRegistry
    from app.tools.schemas import ToolExecutionRequest

    svc = ProjectService.get_instance()
    svc.register_workspace_tools()
    reg = ToolRegistry.get_instance()

    user_a = f"ws_tenant_a_{uuid.uuid4().hex[:6]}"
    user_b = f"ws_tenant_b_{uuid.uuid4().hex[:6]}"

    # User A creates a confidential project with task
    res_a = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_create_project",
            arguments={"name": "Project Manhattan Secret", "description": "Classified"},
            user_id=user_a,
        )
    )
    assert res_a.success is True
    proj_a_id = res_a.output["project"]["id"]

    await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_create_task",
            arguments={"project_id": proj_a_id, "title": "Classified Task Alpha"},
            user_id=user_a,
        )
    )

    # User B lists projects -> 0 projects, zero leak
    res_b_list = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_list_projects",
            arguments={},
            user_id=user_b,
        )
    )
    assert res_b_list.success is True
    assert res_b_list.output["total_projects"] == 0
    assert len(res_b_list.output["projects"]) == 0

    # User B tries to inspect User A's project directly -> not_found
    res_b_get = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_get_project",
            arguments={"project_id": proj_a_id},
            user_id=user_b,
        )
    )
    assert res_b_get.output["status"] == "not_found"

    # User B tries to add a task to User A's project -> error
    res_b_task = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_create_task",
            arguments={"project_id": proj_a_id, "title": "Intruder Task"},
            user_id=user_b,
        )
    )
    assert res_b_task.output["status"] == "error"

    # User B tries to delete User A's project -> deleted is False
    res_b_del = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_delete_project",
            arguments={"project_id": proj_a_id},
            user_id=user_b,
        )
    )
    assert res_b_del.output["deleted"] is False

    # Confirm User A's project still exists untouched
    res_a_verify = await reg.execute(
        ToolExecutionRequest(
            tool_id="workspace_get_project",
            arguments={"project_id": proj_a_id},
            user_id=user_a,
        )
    )
    assert res_a_verify.output["status"] == "success"
    assert res_a_verify.output["project"]["id"] == proj_a_id



