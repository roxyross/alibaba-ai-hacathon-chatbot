"""Integration tests for Phase 4: Open Work Agent & Task Workspace (Cowork Layer).

Verifies:
1. Multi-Artifact Canvas Lifecycle (Markdown, Code, Mermaid, SVG).
2. Live Version History, Revisions & Automated Unified Diff Tracking.
3. Human-in-the-Loop Iterative AI Refinement Loop (agent attribution, diff tracking).
4. Direct Version Revert and Multi-Version Diff Review endpoints.
5. Automated Diagram Generator (Mermaid & SVG Architecture Visualizers).
6. Multi-Tenant Strict Isolation (Anti-IDOR on access, mutations, refinements, reverts, deletes).
7. CoworkService Singleton and Central ToolRegistry Registration of all 7 Tools.
8. Direct Tool Execution via ToolRegistry with ToolExecutionRequest.
9. Confirmation Gating on High-Risk cowork_delete_artifact (RiskLevel.HIGH, requires_confirmation=True).
10. AgentPlanner Deterministic Decomposition & Intent Routing for Cowork Workspace queries.
11. Clean Cascade Artifact Deletion and idempotency checks.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

from app.artifacts.generators import (
    compute_unified_diff,
    generate_markdown_doc,
    generate_mermaid_diagram,
    generate_svg_diagram,
)
from app.artifacts.repository import clear_in_memory_stores
from app.artifacts.schemas import ArtifactStatus, ArtifactType
from app.artifacts.service import CoworkService
from app.auth.service import MagicLinkService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import RiskLevel, ToolExecutionRequest, ToolSource


async def _create_second_user_client() -> AsyncClient:
    """Helper to mint a second authenticated client for tenant isolation testing."""
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )
    service = MagicLinkService()
    test_email = "cowork_tenant_b@example.com"
    await service.request_link(test_email)
    user_id = next(
        u.id for email, u in service._mem_users.items() if email == test_email
    )
    token_value = next(
        t for t, row in service._mem_tokens.items() if row.user_id == user_id
    )
    result = await service.verify(token_value)
    if result is None:
        raise RuntimeError("Failed to verify magic-link token for second user")
    _user, jwt, _ttl = result
    client.headers["Authorization"] = f"Bearer {jwt}"
    return client


@pytest.fixture(autouse=True)
def _clean_cowork_stores() -> None:
    """Ensure in-memory artifact stores are clean before each test."""
    clear_in_memory_stores()
    CoworkService.get_instance().register_cowork_tools()


# -----------------------------------------------------------------------------
# 1. Generators Unit Verification
# -----------------------------------------------------------------------------

def test_unified_diff_generator() -> None:
    """Verify compute_unified_diff outputs accurate additions and deletions."""
    old_text = "Line 1\nLine 2\nLine 3\n"
    new_text = "Line 1\nLine 2 Modified\nLine 3\nLine 4 Added\n"
    diff_str, additions, deletions = compute_unified_diff(old_text, new_text, filename="doc.md")

    assert "Line 2 Modified" in diff_str
    assert "Line 4 Added" in diff_str
    assert additions >= 2
    assert deletions >= 1


def test_markdown_and_diagram_generators() -> None:
    """Verify structured Markdown, Mermaid, and SVG generators."""
    # Markdown
    md = generate_markdown_doc(
        title="Engineering Design Doc",
        summary="Architecture summary for the Cowork layer.",
        sections=[{"title": "Components", "content": "1. Client\n2. Gateway"}],
    )
    assert "# Engineering Design Doc" in md
    assert "> **Executive Summary**" in md
    assert "## Components" in md

    # Mermaid
    mermaid_flow = generate_mermaid_diagram(title="Test Architecture", diagram_type="flowchart")
    assert "flowchart TD" in mermaid_flow
    assert "Diagram: Test Architecture" in mermaid_flow

    mermaid_seq = generate_mermaid_diagram(title="User Auth Flow", diagram_type="sequence")
    assert "sequenceDiagram" in mermaid_seq

    # SVG
    svg_out = generate_svg_diagram(title="Microservice Architecture Preview")
    assert "<svg" in svg_out
    assert "</svg>" in svg_out
    assert "Microservice Architecture Preview" in svg_out


# -----------------------------------------------------------------------------
# 2. Empty State & Listing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_artifacts_empty_state_and_listing(authed_client: AsyncClient) -> None:
    """Verify empty list initially and pagination/filtering options."""
    res = await authed_client.get("/api/v1/workspace/artifacts")
    assert res.status_code == 200
    assert res.json() == []

    # Create 3 artifacts
    for i in range(3):
        create_res = await authed_client.post(
            "/api/v1/workspace/artifacts",
            json={
                "title": f"Doc {i}",
                "content": f"Content {i}",
                "artifact_type": "markdown",
            },
        )
        assert create_res.status_code == 201

    list_res = await authed_client.get("/api/v1/workspace/artifacts?limit=2&offset=0")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 2

    # Check offset
    list_res_offset = await authed_client.get("/api/v1/workspace/artifacts?limit=2&offset=2")
    assert list_res_offset.status_code == 200
    assert len(list_res_offset.json()) == 1


# -----------------------------------------------------------------------------
# 3. Artifact Creation across Types & Initial Snapshot
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_artifact_creation_multitype(authed_client: AsyncClient) -> None:
    """Create artifacts across Markdown, Code, Mermaid, and SVG types."""
    types_to_test = [
        (ArtifactType.MARKDOWN, "# Hello World\nTesting markdown.", "markdown"),
        (ArtifactType.CODE, "def add(a, b):\n    return a + b\n", "python"),
        (ArtifactType.MERMAID, "flowchart TD\n    A --> B\n", "mermaid"),
        (ArtifactType.SVG, "<svg viewBox='0 0 100 100'><circle cx='50' cy='50' r='40'/></svg>", "svg"),
    ]

    for a_type, content, expected_lang in types_to_test:
        res = await authed_client.post(
            "/api/v1/workspace/artifacts",
            json={
                "title": f"Artifact {a_type}",
                "artifact_type": a_type.value,
                "content": content,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["id"].startswith("art-")
        assert data["artifact_type"] == a_type.value
        assert data["language"] == expected_lang
        assert data["current_version"] == 1
        assert data["status"] == ArtifactStatus.DRAFT.value
        assert len(data["versions"]) == 1

        v1 = data["versions"][0]
        assert v1["version_number"] == 1
        assert v1["content"] == content
        assert v1["diff_from_previous"] is None
        assert v1["created_by"] == "user"


# -----------------------------------------------------------------------------
# 4. Artifact Mutation, Version History & Automated Diff
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_artifact_mutation_and_version_diff(authed_client: AsyncClient) -> None:
    """Verify that updating artifact content creates version 2 with unified diff."""
    # 1. Create v1
    v1_content = "# System Overview\n\nInitial draft of the system."
    create_res = await authed_client.post(
        "/api/v1/workspace/artifacts",
        json={
            "title": "Architecture Overview",
            "content": v1_content,
            "artifact_type": "markdown",
        },
    )
    assert create_res.status_code == 201
    art_id = create_res.json()["id"]

    # 2. Update content -> should create v2
    v2_content = "# System Overview\n\nInitial draft of the system.\n\n## Added Section\nNew details."
    patch_res = await authed_client.patch(
        f"/api/v1/workspace/artifacts/{art_id}",
        json={
            "content": v2_content,
            "change_summary": "Added Section 2",
        },
    )
    assert patch_res.status_code == 200
    updated_data = patch_res.json()
    assert updated_data["current_version"] == 2
    assert len(updated_data["versions"]) == 2

    v2 = updated_data["versions"][1]
    assert v2["version_number"] == 2
    assert v2["content"] == v2_content
    assert v2["change_summary"] == "Added Section 2"
    assert v2["diff_from_previous"] is not None
    assert "+## Added Section" in v2["diff_from_previous"]

    # 3. Update title only -> version count stays at 2
    patch_title_res = await authed_client.patch(
        f"/api/v1/workspace/artifacts/{art_id}",
        json={
            "title": "Architecture Overview - Final",
        },
    )
    assert patch_title_res.status_code == 200
    title_data = patch_title_res.json()
    assert title_data["title"] == "Architecture Overview - Final"
    assert title_data["current_version"] == 2
    assert len(title_data["versions"]) == 2


# -----------------------------------------------------------------------------
# 5. Human-in-the-Loop Iterative AI Refinement Loop
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_human_in_the_loop_ai_refinement(authed_client: AsyncClient) -> None:
    """Verify refining artifact via human critique/feedback creates an agent-attributed revision."""
    # 1. Create initial draft
    create_res = await authed_client.post(
        "/api/v1/workspace/artifacts",
        json={
            "title": "API Specification",
            "content": "# API Spec\n\nBasic endpoints defined.",
            "artifact_type": "markdown",
        },
    )
    art_id = create_res.json()["id"]

    # 2. Human requests refinement: 'add section Error Handling'
    refine_res = await authed_client.post(
        f"/api/v1/workspace/artifacts/{art_id}/refine",
        json={
            "instruction": "add section Error Handling and Resilience",
            "target_aspect": "structure",
        },
    )
    assert refine_res.status_code == 200
    refined_data = refine_res.json()
    assert refined_data["current_version"] == 2
    assert "Error Handling" in refined_data["content"]

    v2 = refined_data["versions"][1]
    assert v2["created_by"] == "agent"
    assert v2["diff_from_previous"] is not None
    assert "+## Error Handling And Resilience" in v2["diff_from_previous"] or "Error Handling" in v2["diff_from_previous"]


# -----------------------------------------------------------------------------
# 6. Multi-Version Diff Review and Version Revert
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_version_diff_review_and_revert(authed_client: AsyncClient) -> None:
    """Test direct diff review between historical versions and reverting to v1."""
    # 1. Create v1
    v1_text = "Version One Content\n"
    c_res = await authed_client.post(
        "/api/v1/workspace/artifacts",
        json={"title": "Version Track Doc", "content": v1_text},
    )
    art_id = c_res.json()["id"]

    # 2. Create v2
    v2_text = "Version One Content\nVersion Two Content Added\n"
    await authed_client.patch(
        f"/api/v1/workspace/artifacts/{art_id}",
        json={"content": v2_text},
    )

    # 3. Create v3
    v3_text = "Version One Content\nVersion Two Content Modified\nVersion Three Added\n"
    await authed_client.patch(
        f"/api/v1/workspace/artifacts/{art_id}",
        json={"content": v3_text},
    )

    # 4. Review diff between v1 and v3
    diff_res = await authed_client.get(
        f"/api/v1/workspace/artifacts/{art_id}/diff?from_version=1&to_version=3"
    )
    assert diff_res.status_code == 200
    diff_data = diff_res.json()
    assert diff_data["artifact_id"] == art_id
    assert diff_data["from_version"] == 1
    assert diff_data["to_version"] == 3
    assert diff_data["additions"] >= 2
    assert "Version Three Added" in diff_data["unified_diff"]

    # 5. Revert back to v1
    revert_res = await authed_client.post(
        f"/api/v1/workspace/artifacts/{art_id}/revert",
        json={"version_number": 1},
    )
    assert revert_res.status_code == 200
    revert_data = revert_res.json()
    assert revert_data["current_version"] == 4
    assert revert_data["content"] == v1_text
    assert len(revert_data["versions"]) == 4
    assert "Reverted to revision v1" in revert_data["versions"][3]["change_summary"]


# -----------------------------------------------------------------------------
# 7. Diagram Generator Endpoint (Mermaid & SVG)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_diagram_generator_endpoints(authed_client: AsyncClient) -> None:
    """Verify generating diagrams via POST /diagram endpoint."""
    # A. Mermaid Diagram
    mermaid_res = await authed_client.post(
        "/api/v1/workspace/artifacts/diagram",
        json={
            "diagram_type": "mermaid",
            "specification": "flowchart",
            "title": "Data Ingestion Pipeline",
            "description": "ETL flow for incoming telemetry",
        },
    )
    assert mermaid_res.status_code == 201
    m_data = mermaid_res.json()
    assert m_data["artifact_type"] == "mermaid"
    assert "flowchart TD" in m_data["content"]

    # B. SVG Architecture Preview
    svg_res = await authed_client.post(
        "/api/v1/workspace/artifacts/diagram",
        json={
            "diagram_type": "svg",
            "title": "Cloud Infrastructure Topography",
        },
    )
    assert svg_res.status_code == 201
    svg_data = svg_res.json()
    assert svg_data["artifact_type"] == "svg"
    assert "<svg" in svg_data["content"]
    assert "Cloud Infrastructure Topography" in svg_data["content"]


# -----------------------------------------------------------------------------
# 8. Multi-Tenant Strict Isolation (Anti-IDOR)
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_multitenant_isolation(authed_client: AsyncClient) -> None:
    """Verify that User B cannot read, mutate, refine, revert or delete User A's artifacts."""
    # User A creates artifact
    res_a = await authed_client.post(
        "/api/v1/workspace/artifacts",
        json={"title": "Private User A Doc", "content": "Sensitive Secret Data"},
    )
    art_id = res_a.json()["id"]

    # User B client
    client_b = await _create_second_user_client()
    try:
        # 1. User B tries GET -> 404
        get_b = await client_b.get(f"/api/v1/workspace/artifacts/{art_id}")
        assert get_b.status_code == 404

        # 2. User B tries PATCH -> 404
        patch_b = await client_b.patch(
            f"/api/v1/workspace/artifacts/{art_id}",
            json={"content": "Malicious Overwrite"},
        )
        assert patch_b.status_code == 404

        # 3. User B tries REFINE -> 404
        refine_b = await client_b.post(
            f"/api/v1/workspace/artifacts/{art_id}/refine",
            json={"instruction": "tamper with content"},
        )
        assert refine_b.status_code == 404

        # 4. User B tries REVERT -> 404
        revert_b = await client_b.post(
            f"/api/v1/workspace/artifacts/{art_id}/revert",
            json={"version_number": 1},
        )
        assert revert_b.status_code == 404

        # 5. User B tries DELETE -> 404
        del_b = await client_b.delete(f"/api/v1/workspace/artifacts/{art_id}")
        assert del_b.status_code == 404

        # Verify User A's artifact is completely untouched
        get_a = await authed_client.get(f"/api/v1/workspace/artifacts/{art_id}")
        assert get_a.status_code == 200
        assert get_a.json()["content"] == "Sensitive Secret Data"
    finally:
        await client_b.aclose()


# -----------------------------------------------------------------------------
# 9. ToolRegistry Registration & CoworkService Singleton
# -----------------------------------------------------------------------------

def test_cowork_service_and_tool_registry() -> None:
    """Verify CoworkService singleton identity and registration of 7 native tools."""
    service1 = CoworkService.get_instance()
    service2 = CoworkService.get_instance()
    assert service1 is service2

    service1.register_cowork_tools()
    registry = ToolRegistry.get_instance()

    expected_tools = [
        "cowork_create_artifact",
        "cowork_update_artifact",
        "cowork_refine_artifact",
        "cowork_list_artifacts",
        "cowork_get_artifact",
        "cowork_render_diagram",
        "cowork_delete_artifact",
    ]

    for tool_name in expected_tools:
        tool = registry.get(tool_name)
        assert tool is not None, f"Expected {tool_name} to be registered in ToolRegistry"
        assert tool.source == ToolSource.SYSTEM

    # cowork_delete_artifact confirmation gating verification
    del_tool = registry.get("cowork_delete_artifact")
    assert del_tool is not None
    assert del_tool.risk_level == RiskLevel.HIGH
    assert del_tool.requires_confirmation is True


# -----------------------------------------------------------------------------
# 10. Direct Tool Execution via ToolRegistry
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tool_registry_direct_execution() -> None:
    """Execute cowork tools directly via ToolRegistry.execute()."""
    registry = ToolRegistry.get_instance()
    user_id = "test-agent-user-001"

    # 1. Create artifact via tool
    req_create = ToolExecutionRequest(
        tool_id="cowork_create_artifact",
        arguments={
            "title": "Autonomous Agent Workspace Notes",
            "content": "# Agent Notes\n\nAutonomous execution initialized.",
            "artifact_type": "markdown",
            "user_id": user_id,
        },
        user_id=user_id,
    )
    res_create = await registry.execute(req_create)
    assert res_create.success is True
    assert res_create.output is not None
    art_id = res_create.output["artifact"]["id"]

    # 2. Refine artifact via tool
    req_refine = ToolExecutionRequest(
        tool_id="cowork_refine_artifact",
        arguments={
            "artifact_id": art_id,
            "instruction": "add section Error Handling and Observability",
            "user_id": user_id,
        },
        user_id=user_id,
    )
    res_refine = await registry.execute(req_refine)
    assert res_refine.success is True
    assert res_refine.output["artifact"]["current_version"] == 2

    # 3. List artifacts via tool
    req_list = ToolExecutionRequest(
        tool_id="cowork_list_artifacts",
        arguments={"user_id": user_id},
        user_id=user_id,
    )
    res_list = await registry.execute(req_list)
    assert res_list.success is True
    assert res_list.output["count"] >= 1


# -----------------------------------------------------------------------------
# 11. AgentPlanner Cowork Intent Routing
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_planner_cowork_intent_routing() -> None:
    """Verify AgentPlanner deterministic decomposition and routing to cowork tools."""
    from app.agent_runtime.planner import AgentPlanner

    CoworkService.get_instance().register_cowork_tools()
    planner = AgentPlanner()

    # A. Create artifact
    plan_create = await planner.create_plan("create artifact Product Launch Roadmap")
    assert len(plan_create) == 1
    assert plan_create[0]["tool_id"] == "cowork_create_artifact"
    assert "Product Launch Roadmap" in plan_create[0]["tool_input"]["title"]

    # B. Refine artifact
    plan_refine = await planner.create_plan("refine artifact art-12345 with strict typing and test coverage")
    assert len(plan_refine) == 1
    assert plan_refine[0]["tool_id"] == "cowork_refine_artifact"
    assert plan_refine[0]["tool_input"]["artifact_id"] == "art-12345"

    # C. Render diagram
    plan_diagram = await planner.create_plan("render mermaid diagram Microservice Gateway")
    assert len(plan_diagram) == 1
    assert plan_diagram[0]["tool_id"] == "cowork_render_diagram"
    assert "Microservice Gateway" in plan_diagram[0]["tool_input"]["title"]

    # D. List artifacts
    plan_list = await planner.create_plan("list artifacts in my workspace")
    assert len(plan_list) == 1
    assert plan_list[0]["tool_id"] == "cowork_list_artifacts"

    # E. Get artifact details
    plan_get = await planner.create_plan("view artifact art-12345")
    assert len(plan_get) == 1
    assert plan_get[0]["tool_id"] == "cowork_get_artifact"
    assert plan_get[0]["tool_input"]["artifact_id"] == "art-12345"

    # F. Delete artifact (destructive - confirmation gated)
    plan_del = await planner.create_plan("delete artifact art-12345")
    assert len(plan_del) == 1
    assert plan_del[0]["tool_id"] == "cowork_delete_artifact"
    assert plan_del[0]["tool_input"]["artifact_id"] == "art-12345"


# -----------------------------------------------------------------------------
# 12. Artifact Deletion Lifecycle & Idempotency
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_artifact_deletion_lifecycle(authed_client: AsyncClient) -> None:
    """Verify permanent deletion cascade and subsequent 404 responses."""
    # Create artifact
    c_res = await authed_client.post(
        "/api/v1/workspace/artifacts",
        json={"title": "Temporary Note", "content": "Ephemeral"},
    )
    art_id = c_res.json()["id"]

    # Delete
    del_res = await authed_client.delete(f"/api/v1/workspace/artifacts/{art_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # Subsequent GET -> 404
    get_res = await authed_client.get(f"/api/v1/workspace/artifacts/{art_id}")
    assert get_res.status_code == 404

    # Subsequent DELETE -> 404
    del_again_res = await authed_client.delete(f"/api/v1/workspace/artifacts/{art_id}")
    assert del_again_res.status_code == 404
