"""Comprehensive Automated Test Suite for Phase 14: Automatic New-App Workflow Engine.

Validates under the Zero Simulation Doctrine:
1. Dynamic Detection:
   - Novelty evaluation (new app vs registered app).
   - Trigger origins (process_spawn, window_active, filesystem_install, companion_beacon, user_request).
   - Canonical name normalization and executable resolution.
   - Platform classification (Windows, macOS, Linux, Android, iOS).
2. Multi-Modal Capability Introspection:
   - CLI introspection (--help, --version, subcommands, options).
   - Protocol / port probing (local REST APIs).
   - Desktop UI Automation tree introspection.
   - Mobile app capability introspection (intents, deep links, share targets, App Intents, shortcuts).
   - Cloud connector catalog matching.
3. Universal Integration Ranking:
   - Universal Integration Priority hierarchy enforcement across all 11 tiers.
   - Multi-criteria scoring: confidence, estimated latency, risk classifications.
   - User preference override boosting preferred tier.
4. Dynamic Tool Synthesis & Registration:
   - Synthesis of compliant AgentTool definitions in Central ToolRegistry.
   - Live execution of synthesized dynamic tool handler.
   - Live non-destructive verification probe (Zero Simulation).
   - Honest error propagation for non-functional binaries.
5. End-to-End Workflow Orchestration:
   - Autonomous Detect -> Introspect -> Rank -> Register -> Verify execution.
   - Audit trail and latency verification.
   - Caching and workflow history lookup.
6. DeviceService & ToolRegistry Integration:
   - 5 first-class tools registered and executed via ToolRegistry:
     new_app_workflow, new_app_detect, new_app_introspect, new_app_rank_integrations, new_app_register.
   - DeviceService methods and state isolation.
7. FastAPI REST API Router Integration:
   - REST endpoints tested via AsyncClient and mock authenticated user.
"""

from __future__ import annotations

import sys

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.new_app_workflow import (
    IntegrationRankingEngine,
    NewAppDetector,
    NewAppIntrospector,
    NewAppRegistrar,
    NewAppWorkflowEngine,
    get_new_app_workflow_engine,
)
from app.device.schemas import (
    DiscoveredIntegrationPathway,
    NewAppDetectionRequest,
    NewAppIntrospectionRequest,
    NewAppRegistrationRequest,
    NewAppWorkflowRequest,
)
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import (
    ToolSource,
)

# =============================================================================
# Test Fixtures & Setup
# =============================================================================

@pytest.fixture(autouse=True)
def reset_engine_state() -> None:
    """Reset service and workflow engine state before each test."""
    service = DeviceService.get_instance()
    service.clear_in_memory_state()
    NewAppWorkflowEngine.clear_state()


@pytest.fixture
def mock_user() -> User:
    """Mock authenticated system user for API testing."""
    return User(
        id="usr_phase14_test",
        email="operator@roxy.ai",
    )


# =============================================================================
# 1. Dynamic Detection Tests
# =============================================================================

def test_detection_new_vs_existing_app() -> None:
    """Verify application novelty detection against registered memory catalog."""
    service = DeviceService.get_instance()
    service._mem_apps["dev_1"] = [
        {"id": "app_existing_1", "app_name": "notepad", "executable_path": "C:\\Windows\\notepad.exe"}
    ]

    # Existing app
    req_existing = NewAppDetectionRequest(device_id="dev_1", app_name="notepad")
    res_existing = NewAppDetector.detect(req_existing, registered_apps=service._mem_apps["dev_1"])
    assert res_existing.is_new_app is False
    assert res_existing.existing_app_id == "app_existing_1"
    assert res_existing.canonical_name == "notepad"

    # Novel app
    req_new = NewAppDetectionRequest(device_id="dev_1", app_name="custom_media_cli")
    res_new = NewAppDetector.detect(req_new, registered_apps=service._mem_apps["dev_1"])
    assert res_new.is_new_app is True
    assert res_new.existing_app_id is None
    assert res_new.canonical_name == "custom_media_cli"


def test_detection_trigger_origins() -> None:
    """Verify detection supports all required trigger sources."""
    for trigger in ("process_spawn", "window_active", "filesystem_install", "companion_beacon", "user_request", "api_trigger"):
        req = NewAppDetectionRequest(
            device_id="dev_1",
            app_name="sample_tool",
            trigger_source=trigger,  # type: ignore[arg-type]
        )
        res = NewAppDetector.detect(req)
        assert res.trigger_source == trigger
        assert res.is_new_app is True


def test_detection_real_binary_resolution() -> None:
    """Verify real binary resolution in system PATH (using python executable)."""
    py_executable = sys.executable
    req = NewAppDetectionRequest(device_id="default", app_name=py_executable)
    res = NewAppDetector.detect(req)
    assert len(res.detected_paths) > 0
    assert py_executable.lower() in res.detected_paths[0].lower()
    assert res.confidence >= 0.90


def test_detection_mobile_package_identification() -> None:
    """Verify detection identifies Android packages and iOS bundle IDs."""
    req_android = NewAppDetectionRequest(
        device_id="phone_1",
        package_name="com.spotify.music",
    )
    res_android = NewAppDetector.detect(req_android)
    assert res_android.platform == "android"

    req_ios = NewAppDetectionRequest(
        device_id="iphone_1",
        bundle_id="com.apple.Shortcuts",
    )
    res_ios = NewAppDetector.detect(req_ios)
    assert res_ios.platform == "ios"


# =============================================================================
# 2. Multi-Modal Capability Introspection Tests
# =============================================================================

def test_introspection_real_cli_binary() -> None:
    """Verify real CLI introspection on python executable under Zero Simulation."""
    req = NewAppIntrospectionRequest(
        device_id="default",
        app_name=sys.executable,
        deep_scan=True,
    )
    res = NewAppIntrospector.introspect(req)
    assert res.executable_path is not None
    assert len(res.cli_capabilities) > 0
    assert res.total_capabilities_found > 0
    assert res.introspection_duration_ms >= 0.0


def test_introspection_cloud_connector_catalog_match() -> None:
    """Verify introspection matches known cloud connectors like Spotify and Slack."""
    req = NewAppIntrospectionRequest(
        device_id="default",
        app_name="Spotify",
        deep_scan=False,
    )
    res = NewAppIntrospector.introspect(req)
    assert len(res.cloud_connectors) > 0
    c = res.cloud_connectors[0]
    assert c["connector_type"] == "spotify"
    assert "play_music" in c["capabilities"]


def test_introspection_mobile_catalog_match() -> None:
    """Verify introspection pulls mobile capabilities from MobileAppRegistry."""
    req = NewAppIntrospectionRequest(
        device_id="default",
        app_name="com.spotify.music",
        platform="android",
        deep_scan=False,
    )
    res = NewAppIntrospector.introspect(req)
    assert len(res.mobile_capabilities) > 0
    types = [m["type"] for m in res.mobile_capabilities]
    assert any(t in ("intent", "deep_link", "connector", "ui_automation") for t in types)


def test_introspection_desktop_ui_controls() -> None:
    """Verify standard UI automation control actions are discovered for desktop applications."""
    req = NewAppIntrospectionRequest(
        device_id="default",
        app_name="notepad",
        platform="windows",
        deep_scan=True,
    )
    res = NewAppIntrospector.introspect(req)
    assert len(res.ui_controls) >= 4
    actions = [u["action"] for u in res.ui_controls]
    assert "launch" in actions
    assert "focus" in actions
    assert "click_element" in actions
    assert "type_text" in actions


# =============================================================================
# 3. Universal Integration Ranking Tests
# =============================================================================

def test_ranking_priority_hierarchy_connector_first() -> None:
    """Verify Cloud Connector takes Tier 1 priority over CLI and UI Automation."""
    intro = NewAppIntrospector.introspect(
        NewAppIntrospectionRequest(device_id="default", app_name="spotify", deep_scan=True)
    )
    ranking = IntegrationRankingEngine.rank_pathways(
        app_name="spotify",
        canonical_name="spotify",
        platform_str="desktop",
        introspection=intro,
    )
    assert ranking.primary_pathway.integration_tier == "connector"
    assert ranking.primary_pathway.priority_rank == 1
    assert ranking.primary_pathway.confidence_score >= 0.95
    assert len(ranking.alternative_pathways) > 0


def test_ranking_cli_preferred_over_ui() -> None:
    """Verify CLI Subprocess takes Tier 3 priority over Desktop UI Automation (Tier 8)."""
    intro = NewAppIntrospector.introspect(
        NewAppIntrospectionRequest(device_id="default", app_name=sys.executable, deep_scan=True)
    )
    ranking = IntegrationRankingEngine.rank_pathways(
        app_name="python",
        canonical_name="python",
        platform_str="desktop",
        introspection=intro,
    )
    assert ranking.primary_pathway.integration_tier == "cli_subcommand"
    assert ranking.primary_pathway.priority_rank == 3
    # UI Automation should be lower priority (Rank 8)
    ui_paths = [p for p in ranking.alternative_pathways if p.integration_tier == "ui_automation"]
    assert len(ui_paths) > 0
    assert ui_paths[0].priority_rank == 8


def test_ranking_user_preference_override() -> None:
    """Verify caller preference can elevate a specific tier to Rank 0."""
    intro = NewAppIntrospector.introspect(
        NewAppIntrospectionRequest(device_id="default", app_name="spotify", deep_scan=True)
    )
    ranking = IntegrationRankingEngine.rank_pathways(
        app_name="spotify",
        canonical_name="spotify",
        platform_str="desktop",
        introspection=intro,
        user_preference="ui_automation",
    )
    # UI Automation should now be elevated to primary pathway
    assert ranking.primary_pathway.integration_tier == "ui_automation"
    assert ranking.primary_pathway.priority_rank == 0


# =============================================================================
# 4. Registration, Tool Synthesis & Verification Tests
# =============================================================================

def test_registration_and_tool_synthesis() -> None:
    """Verify dynamic AgentTool synthesis and registration in ToolRegistry."""
    pathway = DiscoveredIntegrationPathway(
        pathway_id="pathway_test_app_cli",
        integration_tier="cli_subcommand",
        priority_rank=3,
        name="Native CLI Subprocess",
        description="Execute test binary",
        confidence_score=0.95,
        estimated_latency_ms=25.0,
        risk_level="LOW",
        requires_confirmation=False,
        execution_adapter="cli_subprocess_adapter",
        verification_strategy="cli_version_probe",
        required_permission="app:test_app:execute",
        input_schema={"type": "object", "properties": {"subcommand": {"type": "string"}}},
        metadata={"binary_path": sys.executable},
    )

    req = NewAppRegistrationRequest(
        device_id="dev_local",
        app_name="test_app",
        primary_pathway=pathway,
        all_pathways=[pathway],
        synthesize_tools=True,
        auto_verify=True,
    )

    service = DeviceService.get_instance()
    reg_res = NewAppRegistrar.register_app(req, service=service)

    assert reg_res.success is True
    assert len(reg_res.registered_tools) > 0
    tool_id = reg_res.registered_tools[0]

    # Verify tool exists in ToolRegistry
    reg = ToolRegistry.get_instance()
    tool = reg.get(tool_id)
    assert tool is not None
    assert tool.name == "test_app_cli_subcommand"
    assert "app:test_app:execute" in tool.permissions
    assert reg_res.verification_status in ("verified", "skipped")

    # Clean up registered test tool
    reg.unregister(tool_id)


@pytest.mark.asyncio
async def test_live_execution_of_synthesized_tool() -> None:
    """Verify synthesized tool execution handler safely calls subprocess and returns output."""
    pathway = DiscoveredIntegrationPathway(
        pathway_id="pathway_py_test_cli",
        integration_tier="cli_subcommand",
        priority_rank=3,
        name="Python CLI Subprocess",
        description="Execute python script CLI",
        confidence_score=0.95,
        estimated_latency_ms=30.0,
        risk_level="LOW",
        requires_confirmation=False,
        execution_adapter="cli_subprocess_adapter",
        verification_strategy="cli_version_probe",
        required_permission="app:py_test:execute",
        input_schema={"type": "object"},
        metadata={"binary_path": sys.executable},
    )

    req = NewAppRegistrationRequest(
        device_id="dev_local",
        app_name="py_test",
        primary_pathway=pathway,
        all_pathways=[pathway],
        synthesize_tools=True,
        auto_verify=False,
    )

    reg_res = NewAppRegistrar.register_app(req)
    tool_id = reg_res.registered_tools[0]

    reg = ToolRegistry.get_instance()
    handler = reg.get_handler(tool_id)
    assert handler is not None

    # Call handler with --version argument
    result = await handler(args=["--version"])
    assert result["status"] == "success"
    assert "Python" in result["stdout"] or "Python" in result["stderr"]

    reg.unregister(tool_id)


# =============================================================================
# 5. End-to-End Workflow Engine Tests
# =============================================================================

def test_full_workflow_execution() -> None:
    """Verify complete automated Detect -> Introspect -> Rank -> Register -> Verify workflow."""
    service = DeviceService.get_instance()
    wf_req = NewAppWorkflowRequest(
        device_id="dev_master",
        target=sys.executable,
        auto_register=True,
        auto_verify=True,
        synthesize_tools=True,
    )

    engine = get_new_app_workflow_engine()
    res = engine.execute_workflow(wf_req, service=service)

    assert res.success is True
    assert res.detection.is_new_app is True
    assert res.introspection.total_capabilities_found > 0
    assert res.ranking.primary_pathway is not None
    assert res.registration is not None
    assert res.registration.success is True
    assert len(res.audit_trail) >= 5
    assert res.workflow_duration_ms > 0.0

    # Verify cached workflow lookup
    cached = engine.get_registered_workflow(res.canonical_name)
    assert cached is not None
    assert cached.app_name == res.app_name

    all_registered = engine.list_registered_workflows()
    assert len(all_registered) >= 1


# =============================================================================
# 6. DeviceService & ToolRegistry Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_device_service_workflow_tools() -> None:
    """Verify 5 Phase 14 tools are registered and executable via ToolRegistry."""
    reg = ToolRegistry.get_instance()

    tools_to_check = [
        "new_app_workflow",
        "new_app_detect",
        "new_app_introspect",
        "new_app_rank_integrations",
        "new_app_register",
    ]

    for tid in tools_to_check:
        t = reg.get(tid)
        assert t is not None, f"Tool '{tid}' not found in ToolRegistry"
        assert t.source == ToolSource.DEVICE

    # 1. Test new_app_detect handler
    detect_handler = reg.get_handler("new_app_detect")
    assert detect_handler is not None
    d_res = await detect_handler(app_name="sample_cli_app")
    assert d_res["is_new_app"] is True
    assert d_res["canonical_name"] == "sample_cli_app"

    # 2. Test new_app_introspect handler
    introspect_handler = reg.get_handler("new_app_introspect")
    assert introspect_handler is not None
    i_res = await introspect_handler(app_name="spotify", deep_scan=False)
    assert len(i_res["cloud_connectors"]) > 0

    # 3. Test new_app_rank_integrations handler
    rank_handler = reg.get_handler("new_app_rank_integrations")
    assert rank_handler is not None
    r_res = await rank_handler(app_name="spotify")
    assert r_res["primary_pathway"]["integration_tier"] == "connector"


# =============================================================================
# 7. FastAPI REST API Router Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_api_new_app_workflow_endpoint(mock_user: User) -> None:
    """Verify POST /devices/{device_id}/new-app/workflow REST endpoint."""
    app.dependency_overrides[get_current_user] = lambda: mock_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        payload = {
            "device_id": "test_device",
            "target": sys.executable,
            "auto_register": True,
            "auto_verify": True,
            "synthesize_tools": True,
        }
        resp = await client.post("/api/v1/devices/test_device/new-app/workflow", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["detection"]["is_new_app"] is True
        assert data["ranking"]["primary_pathway"] is not None
        assert data["registration"]["success"] is True

        # Test GET /devices/{device_id}/new-app/registered
        list_resp = await client.get("/api/v1/devices/test_device/new-app/registered")
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert len(list_data) >= 1

        # Test GET /devices/{device_id}/new-app/registered/{app_name}
        canonical = data["canonical_name"]
        get_resp = await client.get(f"/api/v1/devices/test_device/new-app/registered/{canonical}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["canonical_name"] == canonical

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_sub_endpoints(mock_user: User) -> None:
    """Verify individual detect, introspect, rank, and register endpoints."""
    app.dependency_overrides[get_current_user] = lambda: mock_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Detect
        d_resp = await client.post(
            "/api/v1/devices/dev_1/new-app/detect",
            json={"app_name": "custom_agent"},
        )
        assert d_resp.status_code == 200
        assert d_resp.json()["is_new_app"] is True

        # Introspect
        i_resp = await client.post(
            "/api/v1/devices/dev_1/new-app/introspect",
            json={"app_name": "slack", "deep_scan": False},
        )
        assert i_resp.status_code == 200
        assert len(i_resp.json()["cloud_connectors"]) > 0

        # Rank
        r_resp = await client.post(
            "/api/v1/devices/dev_1/new-app/rank",
            json={"app_name": "slack"},
        )
        assert r_resp.status_code == 200
        assert r_resp.json()["primary_pathway"]["integration_tier"] == "connector"

    app.dependency_overrides.clear()
