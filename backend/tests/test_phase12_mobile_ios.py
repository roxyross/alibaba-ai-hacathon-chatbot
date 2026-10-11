"""Phase 12 Test Suite: Mobile Agent — iOS.

Tests native iOS mobile automation under the Zero Simulation doctrine:
1. Universal Links Engine (HTTP/HTTPS URL validation, query parameter injection, web fallback).
2. Native Custom URL Schemes (spotify://, maps://, shortcuts://, facetime://, tel: format & dispatch).
3. Apple Shortcuts & x-callback-url (shortcuts://run-shortcut and x-callback URL construction).
4. iOS 16+ App Intents Engine (bundle ID & intent validation, parameter delivery).
5. Share Sheet (UIActivityViewController) Protocol (payload item formatting, activity targeting).
6. iOS Companion Protocol (duplex WebSocket/HTTP envelope exchange, telemetry, heartbeats).
7. Honest Unsupported UI Automation (inspect, click, type return unsupported_on_this_platform with alternatives).
8. ToolRegistry Integration (all 9 ios_* tools registered and executable).
9. IntegrationResolver & UniversalAppController Lifecycle (mobile_bridge iOS planning, execution, verification).
10. REST API Endpoints (universal-link, url-scheme, shortcut, app-intent, share-sheet, telemetry, inspect, click, type).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.integration_resolver import IntegrationResolver
from app.device.ios_automation import (
    IOS_KNOWN_APPS,
    IOSAutomationEngine,
    IOSCompanionManager,
)
from app.device.orchestrator import UniversalAppController
from app.device.schemas import (
    AppControlExecutionRequest,
    IntegrationResolutionRequest,
    IOSActionResponse,
    IOSAppIntentRequest,
    IOSCompanionEnvelope,
    IOSCompanionResponse,
    IOSShareSheetRequest,
    IOSShortcutRequest,
    IOSTelemetry,
    IOSUniversalLinkRequest,
    IOSURLSchemeRequest,
)
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest


@pytest.fixture
def mock_user() -> User:
    return User(
        id=str(uuid.uuid4()),
        email="ios_tester@roxy.ai",
    )


# =============================================================================
# 1. Known Catalog & URL Scheme Formatting Tests
# =============================================================================

def test_ios_scheme_catalog_presence() -> None:
    """Verify that known Apple system and popular iOS apps are cataloged."""
    assert "shortcuts" in IOS_KNOWN_APPS
    assert IOS_KNOWN_APPS["shortcuts"]["bundle_id"] == "com.apple.shortcuts"
    assert "spotify" in IOS_KNOWN_APPS
    assert IOS_KNOWN_APPS["spotify"]["bundle_id"] == "com.spotify.client"
    assert "maps" in IOS_KNOWN_APPS
    assert "youtube" in IOS_KNOWN_APPS
    assert "facetime" in IOS_KNOWN_APPS
    assert "phone" in IOS_KNOWN_APPS
    assert "slack" in IOS_KNOWN_APPS
    assert "whatsapp" in IOS_KNOWN_APPS


def test_ios_url_scheme_formatting() -> None:
    """Verify URI formatting for hierarchical and opaque iOS schemes."""
    # 1. Standard hierarchical scheme
    req1 = IOSURLSchemeRequest(
        scheme="spotify",
        host="track",
        path="4cOdK2wGLETKBW3PvgPWqT",
        parameters={"si": "abc123xyz"},
    )
    uri1 = IOSAutomationEngine.format_url_scheme_uri(req1)
    assert uri1 == "spotify://track/4cOdK2wGLETKBW3PvgPWqT?si=abc123xyz"

    # 2. Opaque telephone scheme (tel:)
    req2 = IOSURLSchemeRequest(
        scheme="tel",
        host="18005550199",
    )
    uri2 = IOSAutomationEngine.format_url_scheme_uri(req2)
    assert uri2 == "tel:18005550199"

    # 3. Opaque mailto scheme with parameters
    req3 = IOSURLSchemeRequest(
        scheme="mailto",
        host="support@apple.com",
        parameters={"subject": "Inquiry", "body": "Hello"},
    )
    uri3 = IOSAutomationEngine.format_url_scheme_uri(req3)
    assert uri3.startswith("mailto:support@apple.com?")
    assert "subject=Inquiry" in uri3
    assert "body=Hello" in uri3

    # 4. Raw URI override
    req4 = IOSURLSchemeRequest(
        scheme="facetime",
        raw_uri="facetime-audio://user@example.com",
    )
    uri4 = IOSAutomationEngine.format_url_scheme_uri(req4)
    assert uri4 == "facetime-audio://user@example.com"


@pytest.mark.asyncio
async def test_device_open_url_scheme() -> None:
    """Verify executing custom URL scheme dispatch."""
    req = IOSURLSchemeRequest(
        scheme="maps",
        parameters={"q": "San Francisco", "t": "m"},
    )
    res = await IOSAutomationEngine.device_open_url_scheme(req, device_id="default")
    assert res.success is True
    assert res.action == "open_url_scheme"
    assert res.status == "completed"
    assert "maps://?" in (res.target or "")
    assert "San+Francisco" in (res.target or "")


# =============================================================================
# 2. Universal Links Engine Tests
# =============================================================================

@pytest.mark.asyncio
async def test_universal_link_validation_and_param_injection() -> None:
    """Verify Universal Link validation, parameter injection, and error rejection."""
    # 1. Invalid non-HTTP scheme
    invalid_req = IOSUniversalLinkRequest(url="ftp://invalid.com/file")
    inv_res = await IOSAutomationEngine.device_open_universal_link(invalid_req, device_id="default")
    assert inv_res.success is False
    assert inv_res.status == "failed"
    assert "Invalid Universal Link" in (inv_res.error or "")

    # 2. Valid HTTPS Universal Link with parameter injection
    valid_req = IOSUniversalLinkRequest(
        url="https://open.spotify.com/album/4LH4d3cOWNNXdCoolFd4Buffer",
        bundle_id="com.spotify.client",
        fallback_url="https://spotify.com",
        parameters={"si": "session_tok", "context": "home"},
    )
    val_res = await IOSAutomationEngine.device_open_universal_link(valid_req, device_id="default")
    assert val_res.success is True
    assert val_res.action == "open_universal_link"
    assert val_res.status == "completed"
    assert "si=session_tok" in (val_res.target or "")
    assert val_res.details.get("bundle_id") == "com.spotify.client"


# =============================================================================
# 3. Apple Shortcuts & x-callback-url Tests
# =============================================================================

def test_shortcut_url_formatting() -> None:
    """Verify Apple Shortcut URL construction for text, clipboard, and x-callback-url."""
    # 1. Standard run-shortcut
    req1 = IOSShortcutRequest(
        shortcut_name="Calculate Tip",
        input_type="text",
        input_value="150.00",
    )
    url1 = IOSAutomationEngine.format_shortcut_url(req1)
    assert url1.startswith("shortcuts://run-shortcut?")
    assert "name=Calculate+Tip" in url1
    assert "input=text" in url1
    assert "text=150.00" in url1

    # 2. x-callback-url protocol
    req2 = IOSShortcutRequest(
        shortcut_name="Log Expense",
        input_type="text",
        input_value="Lunch: $25",
        use_x_callback=True,
        x_success_url="roxy://shortcut-done",
        x_error_url="roxy://shortcut-failed",
    )
    url2 = IOSAutomationEngine.format_shortcut_url(req2)
    assert url2.startswith("shortcuts://x-callback-url/run-shortcut?")
    assert "name=Log+Expense" in url2
    assert "x-success=roxy%3A%2F%2Fshortcut-done" in url2
    assert "x-error=roxy%3A%2F%2Fshortcut-failed" in url2


@pytest.mark.asyncio
async def test_device_run_shortcut_empty_name() -> None:
    """Verify that attempting to run a shortcut with an empty name fails gracefully."""
    req = IOSShortcutRequest(shortcut_name="   ")
    res = await IOSAutomationEngine.device_run_shortcut(req, device_id="default")
    assert res.success is False
    assert "cannot be empty" in (res.error or "")


@pytest.mark.asyncio
async def test_device_run_shortcut_execution() -> None:
    """Verify successful dispatch of an Apple Shortcut."""
    req = IOSShortcutRequest(
        shortcut_name="Play Podcast",
        input_type="text",
        input_value="Tech Daily",
    )
    res = await IOSAutomationEngine.device_run_shortcut(req, device_id="default")
    assert res.success is True
    assert res.action == "run_shortcut"
    assert res.target == "Play Podcast"
    assert res.status == "completed"


# =============================================================================
# 4. iOS 16+ App Intents Engine Tests
# =============================================================================

@pytest.mark.asyncio
async def test_app_intent_validation_and_dispatch() -> None:
    """Verify App Intent schema validation and dispatch payload."""
    # 1. Missing bundle_id rejection
    inv_req = IOSAppIntentRequest(bundle_id="", intent_name="PlayMediaIntent")
    inv_res = await IOSAutomationEngine.device_dispatch_app_intent(inv_req, device_id="default")
    assert inv_res.success is False
    assert "Both bundle_id and intent_name are required" in (inv_res.error or "")

    # 2. Valid App Intent dispatch
    val_req = IOSAppIntentRequest(
        bundle_id="com.spotify.client",
        intent_name="PlayMediaIntent",
        parameters={"mediaItemTitle": "Bohemian Rhapsody", "playbackRepeatMode": "all"},
        suggested_invocation_phrase="Play Queen on Spotify",
    )
    val_res = await IOSAutomationEngine.device_dispatch_app_intent(val_req, device_id="default")
    assert val_res.success is True
    assert val_res.action == "dispatch_app_intent"
    assert val_res.target == "com.spotify.client:PlayMediaIntent"
    assert val_res.details.get("parameters", {}).get("mediaItemTitle") == "Bohemian Rhapsody"


# =============================================================================
# 5. Share Sheet (UIActivityViewController) Tests
# =============================================================================

@pytest.mark.asyncio
async def test_share_sheet_payload_handling() -> None:
    """Verify Share Sheet payload validation and payload assembly."""
    # 1. Empty payload rejection
    empty_req = IOSShareSheetRequest()
    empty_res = await IOSAutomationEngine.device_share_sheet(empty_req, device_id="default")
    assert empty_res.success is False
    assert "requires at least one" in (empty_res.error or "")

    # 2. Valid rich share payload
    rich_req = IOSShareSheetRequest(
        text="Check out this article!",
        url="https://roxy.ai/blog/universal-agent",
        mime_type="text/plain",
        target_activity="com.apple.UIKit.activity.AirDrop",
    )
    rich_res = await IOSAutomationEngine.device_share_sheet(rich_req, device_id="default")
    assert rich_res.success is True
    assert rich_res.action == "present_share_sheet"
    assert rich_res.target == "com.apple.UIKit.activity.AirDrop"
    assert rich_res.details.get("payload", {}).get("text") == "Check out this article!"


# =============================================================================
# 6. iOS Companion Protocol & Duplex Command Dispatch Tests
# =============================================================================

@pytest.mark.asyncio
async def test_ios_companion_manager_lifecycle() -> None:
    """Verify enrollment, heartbeat telemetry, and duplex command dispatch for iOS."""
    mgr = IOSCompanionManager.get_instance()
    dev_id = "test_iphone_15_pro"

    # 1. Heartbeat telemetry
    telemetry = IOSTelemetry(
        device_id=dev_id,
        device_name="Alex's iPhone",
        model="iPhone 15 Pro",
        system_version="17.5.1",
        battery_level=92,
        battery_state="charging",
        shortcuts_installed=["Play Music", "Open Notes", "Send WhatsApp"],
    )
    mgr.update_telemetry(telemetry)
    cached = mgr.get_telemetry(dev_id)
    assert cached is not None
    assert cached.battery_level == 92
    assert cached.battery_state == "charging"
    assert "Play Music" in cached.shortcuts_installed

    # 2. Duplex command dispatch over mock connection
    class MockIOSCompanionTransport:
        def __init__(self) -> None:
            self.envelopes: list[dict[str, Any]] = []

        async def send_json(self, data: dict[str, Any]) -> None:
            self.envelopes.append(data)
            # Immediately simulate companion completing the command
            resp = IOSCompanionResponse(
                command_id=data["command_id"],
                success=True,
                status="completed",
                output={"opened": True, "target": data.get("parameters", {}).get("url")},
                duration_ms=32.0,
            )
            mgr.resolve_command(resp)

    transport = MockIOSCompanionTransport()
    mgr.register_connection(dev_id, transport)
    assert mgr.is_connected(dev_id) is True

    envelope = IOSCompanionEnvelope(
        command_id=f"cmd_test_{int(time.time() * 1000)}",
        action="open_universal_link",
        parameters={"url": "https://open.spotify.com/track/123"},
        timeout_ms=3000,
    )
    resp = await mgr.send_command(dev_id, envelope)
    assert resp.success is True
    assert resp.output.get("opened") is True

    # 3. Disconnect
    mgr.unregister_connection(dev_id)
    assert mgr.is_connected(dev_id) is False


# =============================================================================
# 7. Zero Simulation Doctrine: Honest Unsupported UI Automation Tests
# =============================================================================

def test_ios_honest_unsupported_inspect_ui() -> None:
    """Verify that arbitrary third-party UI inspection returns unsupported_on_this_platform."""
    res = IOSAutomationEngine.device_inspect_ui(device_id="default", bundle_id="com.spotify.client")
    assert isinstance(res, IOSActionResponse)
    assert res.success is False
    assert res.status == "unsupported_on_this_platform"
    assert "not permitted by iOS platform security architecture" in (res.error or "")
    assert len(res.supported_alternatives) > 0
    assert any("Shortcuts" in alt for alt in res.supported_alternatives)
    assert any("Universal Links" in alt for alt in res.supported_alternatives)


def test_ios_honest_unsupported_click_element() -> None:
    """Verify that arbitrary coordinate touch injection returns unsupported_on_this_platform."""
    res = IOSAutomationEngine.device_click_element(device_id="default", x=300, y=700, name="Play Button")
    assert isinstance(res, IOSActionResponse)
    assert res.success is False
    assert res.status == "unsupported_on_this_platform"
    assert "operating system sandbox" in (res.error or "")
    assert len(res.supported_alternatives) > 0


def test_ios_honest_unsupported_type_text() -> None:
    """Verify that arbitrary keystroke injection returns unsupported_on_this_platform."""
    res = IOSAutomationEngine.device_type_text(text="Hello iOS", device_id="default")
    assert isinstance(res, IOSActionResponse)
    assert res.success is False
    assert res.status == "unsupported_on_this_platform"
    assert "Keystroke injection into background third-party iOS applications is forbidden" in (res.error or "")
    assert len(res.supported_alternatives) > 0


# =============================================================================
# 8. ToolRegistry Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_tool_registry_ios_tools() -> None:
    """Verify all 9 ios_* tools are registered in ToolRegistry and executable."""
    registry = ToolRegistry.get_instance()
    DeviceService.get_instance().register_device_tools()

    expected_tools = [
        "ios_open_universal_link",
        "ios_open_url_scheme",
        "ios_run_shortcut",
        "ios_dispatch_app_intent",
        "ios_share_sheet",
        "ios_get_telemetry",
        "ios_inspect_ui",
        "ios_click_element",
        "ios_type_text",
    ]

    for tool_id in expected_tools:
        tool = registry.get(tool_id)
        assert tool is not None, f"Tool '{tool_id}' not found in ToolRegistry."
        assert "mobile" in tool.capabilities
        assert "ios" in tool.capabilities

    # Test executing ios_open_url_scheme through ToolRegistry
    exec_req = ToolExecutionRequest(
        tool_id="ios_open_url_scheme",
        arguments={"scheme": "shortcuts", "host": "run-shortcut", "parameters": {"name": "Test"}},
        user_id="default",
        target_device="default",
    )
    exec_res = await registry.execute(exec_req)
    assert exec_res.success is True
    assert exec_res.output is not None

    # Test executing ios_inspect_ui through ToolRegistry (returns honest unsupported response)
    insp_req = ToolExecutionRequest(
        tool_id="ios_inspect_ui",
        arguments={"bundle_id": "com.apple.shortcuts"},
        user_id="default",
        target_device="default",
    )
    insp_res = await registry.execute(insp_req)
    assert insp_res.output is not None
    assert isinstance(insp_res.output, dict)
    assert insp_res.output.get("status") == "unsupported_on_this_platform"


# =============================================================================
# 9. IntegrationResolver Evaluation Tests
# =============================================================================

def test_integration_resolver_ios() -> None:
    """Verify IntegrationResolver properly resolves iOS requests to mobile_bridge."""
    req = IntegrationResolver.resolve(
        IntegrationResolutionRequest(
            application="com.spotify.client",
            requested_capability="shortcut",
            device={"os_platform": "ios", "device_type": "mobile", "device_id": "iphone_01"},
        )
    )
    assert req.success is True
    assert req.chosen_integration == "mobile_bridge"
    assert req.verification_method == "ios_shortcut_probe"

    # Universal link capability
    req_link = IntegrationResolver.resolve(
        IntegrationResolutionRequest(
            application="https://open.spotify.com/track/123",
            requested_capability="universal_link",
            device={"os_platform": "ios", "device_type": "mobile"},
        )
    )
    assert req_link.success is True
    assert req_link.chosen_integration in ("mobile_bridge", "browser_automation")


# =============================================================================
# 10. UniversalAppController Lifecycle Tests (Phase 9 Integration)
# =============================================================================

@pytest.mark.asyncio
async def test_universal_app_controller_ios_lifecycle() -> None:
    """Verify end-to-end plan, execute, verify cycle for iOS via UniversalAppController."""
    controller = UniversalAppController.get_instance()

    req = AppControlExecutionRequest(
        application="com.spotify.client",
        capability="shortcut",
        parameters={"shortcut_name": "Play Spotify", "platform": "ios"},
        device_id="ios_device_1",
        preferred_integration="mobile_bridge",
        confirmed=True,
        skip_verification=False,
    )
    result = await controller.execute_lifecycle(req)
    assert result.success is True
    assert result.stage == "verified"
    assert result.plan is not None
    assert any("iOS" in s.name for s in result.plan.steps)
    assert result.verification.get("verified") is True


# =============================================================================
# 11. REST API Endpoint Tests
# =============================================================================

@pytest.mark.asyncio
async def test_ios_rest_endpoints(mock_user: User) -> None:
    """Verify all iOS REST API endpoints respond with structured schemas."""
    app.dependency_overrides[get_current_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Universal Link
        r_ul = await client.post(
            "/api/v1/devices/test_dev/ios/universal-link",
            json={"url": "https://open.spotify.com/track/456", "bundle_id": "com.spotify.client"},
        )
        assert r_ul.status_code == 200
        data_ul = r_ul.json()
        assert data_ul["success"] is True
        assert data_ul["action"] == "open_universal_link"

        # 2. URL Scheme
        r_sc = await client.post(
            "/api/v1/devices/test_dev/ios/url-scheme",
            json={"scheme": "spotify", "host": "album", "path": "test_id"},
        )
        assert r_sc.status_code == 200
        data_sc = r_sc.json()
        assert data_sc["success"] is True
        assert data_sc["action"] == "open_url_scheme"

        # 3. Shortcut
        r_short = await client.post(
            "/api/v1/devices/test_dev/ios/shortcut",
            json={"shortcut_name": "Calculate Total", "input_value": "100"},
        )
        assert r_short.status_code == 200
        data_short = r_short.json()
        assert data_short["success"] is True
        assert data_short["target"] == "Calculate Total"

        # 4. App Intent
        r_intent = await client.post(
            "/api/v1/devices/test_dev/ios/app-intent",
            json={"bundle_id": "com.spotify.client", "intent_name": "PlayMediaIntent", "parameters": {"title": "Song"}},
        )
        assert r_intent.status_code == 200
        data_intent = r_intent.json()
        assert data_intent["success"] is True

        # 5. Share Sheet
        r_share = await client.post(
            "/api/v1/devices/test_dev/ios/share-sheet",
            json={"text": "Check this out!", "url": "https://roxy.ai"},
        )
        assert r_share.status_code == 200
        data_share = r_share.json()
        assert data_share["success"] is True

        # 6. Telemetry GET & POST
        r_tel_post = await client.post(
            "/api/v1/devices/test_dev/ios/telemetry",
            json={"device_id": "test_dev", "battery_level": 95, "system_version": "17.5"},
        )
        assert r_tel_post.status_code == 200

        r_tel_get = await client.get("/api/v1/devices/test_dev/ios/telemetry")
        assert r_tel_get.status_code == 200
        data_tel = r_tel_get.json()
        assert data_tel["battery_level"] == 95

        # 7. Honest Unsupported Endpoints (inspect, click, type)
        r_insp = await client.get("/api/v1/devices/test_dev/ios/inspect")
        assert r_insp.status_code == 200
        data_insp = r_insp.json()
        assert data_insp["status"] == "unsupported_on_this_platform"
        assert len(data_insp["supported_alternatives"]) > 0

        r_click = await client.post(
            "/api/v1/devices/test_dev/ios/click",
            json={"name": "Button", "x": 100, "y": 200},
        )
        assert r_click.status_code == 200
        data_click = r_click.json()
        assert data_click["status"] == "unsupported_on_this_platform"

        r_type = await client.post(
            "/api/v1/devices/test_dev/ios/type",
            json={"text": "Type something"},
        )
        assert r_type.status_code == 200
        data_type = r_type.json()
        assert data_type["status"] == "unsupported_on_this_platform"

    app.dependency_overrides.clear()
