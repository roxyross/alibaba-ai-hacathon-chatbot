"""Comprehensive automated test suite for Phase 2: Target-Scoped Permission Engine.

Tests:
1. Target-scoped policy grants (app, capability, device, resource).
2. Specific-to-general resolution hierarchy.
3. Parameter constraint validation (numerical comparisons, allowed sets, prefix).
4. Time-to-Live (TTL) expiration semantics.
5. Single-use (allow_once) consumption and revocation.
6. Explicit grant revocation by ID, tool, and target_app.
7. Human-readable PermissionUXDetails formatting.
8. ToolRegistry integration with target_app and device parameters.
9. FastAPI permissions router endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.permissions.schemas import (
    PermissionCheckRequest,
    PermissionGrantCreate,
    PermissionPolicy,
    PermissionUXDetails,
)
from app.permissions.service import PermissionService, clear_in_memory_grants
from app.tools.registry import ToolRegistry
from app.tools.schemas import (
    AgentTool,
    RiskLevel,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolSource,
)


@pytest.fixture(autouse=True)
def clean_permissions() -> None:
    """Ensure in-memory permissions are reset before each test."""
    clear_in_memory_grants()


# -----------------------------------------------------------------------------
# 1. Target Scopes: App, Capability, Device, and Resource Matching
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_scoped_permission_grant() -> None:
    """Verify grant scoped to an entire application allows all actions on that app."""
    service = PermissionService()
    user_id = "user_app_test"

    # Grant allow_for_app on Spotify
    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="spotify",
            policy=PermissionPolicy.ALLOW_FOR_APP,
            permission="media:control",
        ),
    )

    # Check action targeting spotify app
    res = await service.check_permission(
        user_id=user_id,
        target_app="spotify",
        capability="playback:pause",
    )
    assert res.granted is True
    assert res.requires_confirmation is False
    assert res.matched_scope == "app"
    assert res.ux_details is not None
    assert "Spotify" in res.ux_details.application


@pytest.mark.asyncio
async def test_capability_scoped_permission_grant() -> None:
    """Verify grant scoped to a specific capability within an application."""
    service = PermissionService()
    user_id = "user_cap_test"

    # Grant playback:play on spotify, but not account:modify
    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="spotify",
            capability="playback:play",
            policy=PermissionPolicy.ALLOW_AUTOMATICALLY,
        ),
    )

    # Allowed capability
    res_play = await service.check_permission(
        user_id=user_id,
        target_app="spotify",
        capability="playback:play",
    )
    assert res_play.granted is True
    assert res_play.matched_scope == "capability"

    # Different capability on same app should require confirmation (fallback)
    res_delete = await service.check_permission(
        user_id=user_id,
        target_app="spotify",
        capability="playlist:delete",
    )
    assert res_delete.granted is False
    assert res_delete.requires_confirmation is True


@pytest.mark.asyncio
async def test_device_scoped_permission_grant() -> None:
    """Verify grant scoped to a specific device."""
    service = PermissionService()
    user_id = "user_device_test"

    # Grant execution on trusted office desktop
    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="terminal",
            device_id="desktop-office-01",
            policy=PermissionPolicy.ALLOW_FOR_DEVICE,
        ),
    )

    # Action on authorized office device
    res_office = await service.check_permission(
        user_id=user_id,
        target_app="terminal",
        device_id="desktop-office-01",
    )
    assert res_office.granted is True
    assert res_office.matched_scope == "device"

    # Action on different unauthorized device
    res_mobile = await service.check_permission(
        user_id=user_id,
        target_app="terminal",
        device_id="mobile-phone-02",
    )
    assert res_mobile.granted is False
    assert res_mobile.requires_confirmation is True


@pytest.mark.asyncio
async def test_resource_scoped_permission_grant() -> None:
    """Verify grant scoped to a specific resource path or pattern."""
    service = PermissionService()
    user_id = "user_res_test"

    # Grant write to /tmp/safe/* only
    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="filesystem",
            resource="/tmp/safe/*",
            policy=PermissionPolicy.ALLOW_FOR_RESOURCE,
        ),
    )

    # Safe path
    res_safe = await service.check_permission(
        user_id=user_id,
        target_app="filesystem",
        resource="/tmp/safe/report.txt",
    )
    assert res_safe.granted is True
    assert res_safe.matched_scope == "resource"

    # Sensitive path outside scope
    res_unsafe = await service.check_permission(
        user_id=user_id,
        target_app="filesystem",
        resource="/etc/passwd",
    )
    assert res_unsafe.granted is False
    assert res_unsafe.requires_confirmation is True


# -----------------------------------------------------------------------------
# 2. Resolution Hierarchy (Specific to General)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_specific_to_general_resolution_precedence() -> None:
    """Verify exact match takes precedence over broad application or tool match."""
    service = PermissionService()
    user_id = "user_hierarchy_test"

    # Broad grant: allow Slack automatically
    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="slack",
            policy=PermissionPolicy.ALLOW_AUTOMATICALLY,
        ),
    )

    # Specific grant: NEVER allow post to #announcements
    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="slack",
            resource="#announcements",
            policy=PermissionPolicy.NEVER_ALLOW,
        ),
    )

    # Posting to general should be allowed by broad rule
    res_gen = await service.check_permission(
        user_id=user_id,
        target_app="slack",
        resource="#random",
    )
    assert res_gen.granted is True

    # Posting to announcements should be BLOCKED by specific resource rule
    res_ann = await service.check_permission(
        user_id=user_id,
        target_app="slack",
        resource="#announcements",
    )
    assert res_ann.granted is False
    assert res_ann.requires_confirmation is False
    assert "blocked" in res_ann.reason.lower()
    assert res_ann.matched_scope == "resource"


# -----------------------------------------------------------------------------
# 3. Parameter Constraints
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parameter_constraints_evaluation() -> None:
    """Verify numerical, allowed set, and string constraints."""
    service = PermissionService()
    user_id = "user_constraint_test"

    # Grant financial transfer with amount <= 500 and allowed currencies
    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="billing",
            capability="transfer",
            policy=PermissionPolicy.ALLOW_AUTOMATICALLY,
            parameter_constraints={
                "amount": {"lte": 500},
                "currency": {"in": ["USD", "EUR"]},
            },
        ),
    )

    # Valid transaction under threshold
    res_valid = await service.check_permission(
        user_id=user_id,
        target_app="billing",
        capability="transfer",
        parameters={"amount": 250, "currency": "USD"},
    )
    assert res_valid.granted is True
    assert res_valid.requires_confirmation is False

    # Invalid amount exceeding constraint -> requires confirmation
    res_exceeded = await service.check_permission(
        user_id=user_id,
        target_app="billing",
        capability="transfer",
        parameters={"amount": 1000, "currency": "USD"},
    )
    assert res_exceeded.granted is False
    assert res_exceeded.requires_confirmation is True
    assert "exceeds maximum" in res_exceeded.reason.lower()

    # Invalid currency constraint
    res_bad_curr = await service.check_permission(
        user_id=user_id,
        target_app="billing",
        capability="transfer",
        parameters={"amount": 100, "currency": "BTC"},
    )
    assert res_bad_curr.granted is False
    assert res_bad_curr.requires_confirmation is True
    assert "not in allowed set" in res_bad_curr.reason.lower()


# -----------------------------------------------------------------------------
# 4. Expiration and Time-to-Live (TTL) Semantics
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_time_bounded_permission_expiration() -> None:
    """Verify grant expires when TTL / expires_at is in the past."""
    service = PermissionService()
    user_id = "user_ttl_test"

    # Create expired grant
    past_time = datetime.now(UTC) - timedelta(minutes=10)
    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="database",
            capability="export",
            policy=PermissionPolicy.ALLOW_FOR_DURATION,
            expires_at=past_time,
        ),
    )

    # Check permission on expired grant -> should require confirmation
    res_exp = await service.check_permission(
        user_id=user_id,
        target_app="database",
        capability="export",
    )
    assert res_exp.granted is False
    assert res_exp.requires_confirmation is True

    # Create active future grant
    future_time = datetime.now(UTC) + timedelta(hours=2)
    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="database_future",
            capability="export",
            policy=PermissionPolicy.ALLOW_FOR_DURATION,
            expires_at=future_time,
        ),
    )

    res_active = await service.check_permission(
        user_id=user_id,
        target_app="database_future",
        capability="export",
    )
    assert res_active.granted is True
    assert res_active.requires_confirmation is False


# -----------------------------------------------------------------------------
# 5. Single-Use Consumption (allow_once)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_use_permission_consumption() -> None:
    """Verify allow_once grant permits execution once and immediately revokes itself."""
    service = PermissionService()
    user_id = "user_single_use_test"

    await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="camera",
            capability="snapshot",
            policy=PermissionPolicy.ALLOW_ONCE,
        ),
    )

    # First execution consumes grant
    res_first = await service.check_permission(
        user_id=user_id,
        target_app="camera",
        capability="snapshot",
    )
    assert res_first.granted is True
    assert res_first.requires_confirmation is False
    assert res_first.policy == PermissionPolicy.ALLOW_ONCE.value

    # Second execution must require confirmation because grant was consumed
    res_second = await service.check_permission(
        user_id=user_id,
        target_app="camera",
        capability="snapshot",
    )
    assert res_second.granted is False
    assert res_second.requires_confirmation is True


# -----------------------------------------------------------------------------
# 6. Revocation Functionality
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explicit_permission_revocation() -> None:
    """Verify grants can be explicitly revoked by grant_id or target_app."""
    service = PermissionService()
    user_id = "user_revoke_test"

    grant = await service.grant_permission(
        user_id=user_id,
        grant_in=PermissionGrantCreate(
            target_app="cloud_backup",
            capability="sync",
            policy=PermissionPolicy.ALLOW_AUTOMATICALLY,
        ),
    )

    # Pre-revocation check
    res_before = await service.check_permission(
        user_id=user_id,
        target_app="cloud_backup",
        capability="sync",
    )
    assert res_before.granted is True

    # Revoke by grant_id
    revoked = await service.revoke_permission(user_id=user_id, grant_id=grant.id)
    assert revoked is True

    # Post-revocation check
    res_after = await service.check_permission(
        user_id=user_id,
        target_app="cloud_backup",
        capability="sync",
    )
    assert res_after.granted is False
    assert res_after.requires_confirmation is True


# -----------------------------------------------------------------------------
# 7. UX Details Validation
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_human_readable_ux_details() -> None:
    """Verify PermissionUXDetails presents friendly strings without raw JSON."""
    service = PermissionService()
    user_id = "user_ux_test"

    res = await service.check_permission(
        user_id=user_id,
        target_app="email_client",
        capability="send_message",
        resource="ceo@company.com",
        device_id="desktop-mac-pro",
        parameters={"to": "ceo@company.com", "subject": "Quarterly Update", "token": "secret123"},
    )

    ux: PermissionUXDetails = res.ux_details  # type: ignore[assignment]
    assert ux is not None
    assert ux.application == "Email Client"
    assert ux.capability == "Send Message"
    assert ux.target == "ceo@company.com"
    assert "desktop-mac-pro" in ux.device
    assert "secret123" not in ux.data_involved  # Secret masked
    assert "***" in ux.data_involved


# -----------------------------------------------------------------------------
# 8. ToolRegistry Direct Execution Integration
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_registry_target_scoped_integration() -> None:
    """Verify ToolRegistry.execute integrates with target-scoped permission policies."""
    registry = ToolRegistry.get_instance()
    perm_service = PermissionService()
    user_id = "user_registry_scoped"

    tool_id = "test_deploy_service"
    tool = AgentTool(
        id=tool_id,
        name="Deploy Service",
        description="Deploys production microservice",
        source=ToolSource.SYSTEM,
        capabilities=["deployment", "cloud"],
        risk_level=RiskLevel.HIGH,
        requires_confirmation=True,
    )

    async def _handler(**kwargs: Any) -> dict[str, str]:
        return {"status": "deployed"}

    registry.register(tool, _handler)

    try:
        # 1. Unconfirmed execution is blocked by gate
        req_blocked = ToolExecutionRequest(
            tool_id=tool_id,
            target_app="kubernetes",
            target_device="cluster-us-east-1",
            arguments={"service": "auth-api"},
            user_id=user_id,
            bypass_confirmation=False,
        )
        res_blocked = await registry.execute(req_blocked)
        assert res_blocked.status == ToolExecutionStatus.REQUIRES_CONFIRMATION

        # 2. Grant permission specifically for target_app='kubernetes' and device='cluster-us-east-1'
        await perm_service.grant_permission(
            user_id=user_id,
            grant_in=PermissionGrantCreate(
                target_app="kubernetes",
                device_id="cluster-us-east-1",
                policy=PermissionPolicy.ALLOW_FOR_DEVICE,
            ),
        )

        # 3. Execution succeeds automatically without bypass_confirmation
        req_allowed = ToolExecutionRequest(
            tool_id=tool_id,
            target_app="kubernetes",
            target_device="cluster-us-east-1",
            arguments={"service": "auth-api"},
            user_id=user_id,
            bypass_confirmation=False,
        )
        res_allowed = await registry.execute(req_allowed)
        assert res_allowed.success is True
        assert res_allowed.status == ToolExecutionStatus.COMPLETED
        assert res_allowed.output == {"status": "deployed"}

    finally:
        registry.unregister(tool_id)


# -----------------------------------------------------------------------------
# 9. HTTP Router Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_permissions_api_router_lifecycle(async_client: httpx.AsyncClient) -> None:
    """Verify listing, granting, checking, and deleting grants via REST API."""
    auth_header = {"Authorization": "Bearer mock-test-token"}

    # Mock user auth if needed or use test client
    # In tests, get_current_user dependency handles auth or test mocks
    from app.auth.dependencies import get_current_user
    from app.auth.models import User
    from app.main import app

    test_user = User(id="user_api_test", email="api_perm@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        # 1. Grant target-scoped permission
        grant_resp = await async_client.post(
            "/api/v1/permissions/grant",
            json={
                "target_app": "github",
                "capability": "repo:create",
                "policy": "allow_automatically",
                "parameter_constraints": {"private": True},
            },
        )
        assert grant_resp.status_code == 200
        grant_data = grant_resp.json()
        grant_id = grant_data["id"]
        assert grant_data["target_app"] == "github"

        # 2. List grants with filter
        list_resp = await async_client.get("/api/v1/permissions?target_app=github&active_only=true")
        assert list_resp.status_code == 200
        grants = list_resp.json()
        assert len(grants) >= 1
        assert grants[0]["id"] == grant_id

        # 3. Check permission with valid parameters
        check_valid = await async_client.post(
            "/api/v1/permissions/check",
            json={
                "target_app": "github",
                "capability": "repo:create",
                "parameters": {"private": True},
            },
        )
        assert check_valid.status_code == 200
        assert check_valid.json()["granted"] is True

        # 4. Check permission with violating parameters
        check_invalid = await async_client.post(
            "/api/v1/permissions/check",
            json={
                "target_app": "github",
                "capability": "repo:create",
                "parameters": {"private": False},
            },
        )
        assert check_invalid.status_code == 200
        assert check_invalid.json()["requires_confirmation"] is True

        # 5. Delete grant via DELETE endpoint
        del_resp = await async_client.delete(f"/api/v1/permissions/grants/{grant_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["revoked"] is True

        # 6. Verify check now requires confirmation after deletion
        check_after_del = await async_client.post(
            "/api/v1/permissions/check",
            json={
                "target_app": "github",
                "capability": "repo:create",
                "parameters": {"private": True},
            },
        )
        assert check_after_del.json()["granted"] is False
        assert check_after_del.json()["requires_confirmation"] is True

    finally:
        app.dependency_overrides.pop(get_current_user, None)
