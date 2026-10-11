"""Phase 11 Test Suite: Mobile Agent — Android.

Tests native Android automation under the Zero Simulation doctrine:
1. AccessibilityService Hierarchy Traversal & Node Parsing (AccessibilityNodeInfo tree).
2. UI Actions (click, coordinate tap, text input, scrolling, hardware/navigation keyevents).
3. Android Intent Engine (am start, broadcast, service, typed extras, flags, categories).
4. Deep Link & App Link Dispatcher (custom schemes, query parameters, web fallback).
5. Android Companion Protocol (duplex WebSocket/HTTP envelope exchange, telemetry, heartbeats).
6. ToolRegistry Integration (all 9 android_* tools registered and executable).
7. UniversalAppController (mobile_bridge planning, execution, and verification lifecycle).
8. REST API Endpoints (inspect, find, click, type, scroll, key, intent, deep-link, screenshot, companion).
"""

from __future__ import annotations

import base64
import time
import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.android_automation import (
    ANDROID_KEY_CODES,
    AndroidAutomationEngine,
    AndroidCompanionManager,
)
from app.device.orchestrator import UniversalAppController
from app.device.schemas import (
    AndroidCompanionEnvelope,
    AndroidCompanionResponse,
    AndroidCompanionTelemetry,
    AndroidDeepLinkRequest,
    AndroidIntentRequest,
    AndroidScreenshotResponse,
    AppControlExecutionRequest,
)
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest

SAMPLE_UIAUTOMATOR_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.android.systemui" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,0][1080,2400]">
    <node index="0" text="" resource-id="com.spotify.music:id/main_content" class="android.view.ViewGroup" package="com.spotify.music" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[0,120][1080,2280]">
      <node index="0" text="Bohemian Rhapsody" resource-id="com.spotify.music:id/track_title" class="android.widget.TextView" package="com.spotify.music" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[60,1400][1020,1500]" />
      <node index="1" text="" resource-id="com.spotify.music:id/play_pause_button" class="android.widget.ImageButton" package="com.spotify.music" content-desc="Play Track" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[440,1650][640,1850]" />
      <node index="2" text="Queen" resource-id="com.spotify.music:id/search_query" class="android.widget.EditText" package="com.spotify.music" content-desc="Search Songs" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="true" scrollable="false" long-clickable="true" password="false" selected="false" bounds="[60,200][1020,320]" />
      <node index="3" text="" resource-id="com.spotify.music:id/track_list" class="androidx.recyclerview.widget.RecyclerView" package="com.spotify.music" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="true" long-clickable="false" password="false" selected="false" bounds="[0,400][1080,1300]" />
    </node>
  </node>
</hierarchy>
"""


@pytest.fixture
def mock_user() -> User:
    return User(
        id=str(uuid.uuid4()),
        email="android_tester@roxy.ai",
    )


# =============================================================================
# 1. Role Normalization & Bounds Parsing Tests
# =============================================================================

def test_android_role_normalization() -> None:
    """Verify that Android View classes map cleanly to canonical Roxy UI roles."""
    assert AndroidAutomationEngine._normalize_android_role("android.widget.Button") == "button"
    assert AndroidAutomationEngine._normalize_android_role("android.widget.ImageButton") == "button"
    assert AndroidAutomationEngine._normalize_android_role("android.widget.EditText") == "edit"
    assert AndroidAutomationEngine._normalize_android_role("android.widget.TextView") == "text"
    assert AndroidAutomationEngine._normalize_android_role("android.widget.CheckBox") == "checkbox"
    assert AndroidAutomationEngine._normalize_android_role("android.widget.Switch") == "switch"
    assert AndroidAutomationEngine._normalize_android_role("androidx.recyclerview.widget.RecyclerView") == "list"
    assert AndroidAutomationEngine._normalize_android_role("android.widget.ScrollView") == "scroll_view"
    assert AndroidAutomationEngine._normalize_android_role("android.webkit.WebView") == "web_view"
    assert AndroidAutomationEngine._normalize_android_role("com.custom.library.CustomButtonView") == "button"
    assert AndroidAutomationEngine._normalize_android_role("com.custom.library.CustomEditField") == "edit"
    assert AndroidAutomationEngine._normalize_android_role("com.custom.library.CustomContainer") == "container"
    assert AndroidAutomationEngine._normalize_android_role("unknown.native.Component") == "control"


def test_android_bounds_parsing() -> None:
    """Verify bounds parsing from standard '[left,top][right,bottom]' representation."""
    bounds = AndroidAutomationEngine._parse_bounds_string("[60,1400][1020,1500]")
    assert bounds.left == 60
    assert bounds.top == 1400
    assert bounds.right == 1020
    assert bounds.bottom == 1500
    assert bounds.width == 960
    assert bounds.height == 100

    invalid = AndroidAutomationEngine._parse_bounds_string("invalid_bounds")
    assert invalid.left == 0
    assert invalid.top == 0
    assert invalid.width == 0
    assert invalid.height == 0


# =============================================================================
# 2. Accessibility Hierarchy & XML Parsing Tests
# =============================================================================

def test_parse_uiautomator_xml() -> None:
    """Verify parsing of real uiautomator dump XML into hierarchical AndroidNodeInfoModel."""
    tree = AndroidAutomationEngine.parse_uiautomator_xml(SAMPLE_UIAUTOMATOR_XML)
    assert tree.class_name == "android.widget.FrameLayout"
    assert tree.package_name == "com.android.systemui"
    assert len(tree.children) == 1

    content_group = tree.children[0]
    assert content_group.resource_id == "com.spotify.music:id/main_content"
    assert len(content_group.children) == 4

    # Node 0: TextView
    tv = content_group.children[0]
    assert tv.text == "Bohemian Rhapsody"
    assert tv.resource_id == "com.spotify.music:id/track_title"
    assert tv.role == "text"
    assert tv.is_clickable is True

    # Node 1: ImageButton
    btn = content_group.children[1]
    assert btn.content_description == "Play Track"
    assert btn.role == "button"
    assert btn.is_clickable is True

    # Node 2: EditText
    et = content_group.children[2]
    assert et.text == "Queen"
    assert et.role == "edit"
    assert et.is_editable is True

    # Node 3: RecyclerView
    rv = content_group.children[3]
    assert rv.role == "list"
    assert rv.is_scrollable is True


# =============================================================================
# 3. Element Finding & Search Tests
# =============================================================================

def test_find_node_in_hierarchy() -> None:
    """Verify node search across text, resource_id, content_description, and role."""
    tree = AndroidAutomationEngine.parse_uiautomator_xml(SAMPLE_UIAUTOMATOR_XML)

    # By text
    match_text = AndroidAutomationEngine.find_node(tree, text="Bohemian")
    assert match_text is not None
    assert match_text.resource_id == "com.spotify.music:id/track_title"

    # By resource ID
    match_id = AndroidAutomationEngine.find_node(tree, resource_id="search_query")
    assert match_id is not None
    assert match_id.text == "Queen"

    # By content description
    match_desc = AndroidAutomationEngine.find_node(tree, content_description="Play Track")
    assert match_desc is not None
    assert match_desc.role == "button"

    # By role
    match_role = AndroidAutomationEngine.find_node(tree, role="list")
    assert match_role is not None
    assert match_role.is_scrollable is True

    # Non-existent
    match_none = AndroidAutomationEngine.find_node(tree, text="NonExistentSong")
    assert match_none is None


@pytest.mark.asyncio
async def test_device_find_element_offline() -> None:
    """Verify device_find_element polling and failure handling."""
    elem = await AndroidAutomationEngine.device_find_element(
        device_id="default",
        text="Bohemian",
        timeout_sec=1.0,
    )
    assert elem is not None
    assert elem.text == "Bohemian Rhapsody"

    with pytest.raises(LookupError, match="Android element not found"):
        await AndroidAutomationEngine.device_find_element(
            device_id="default",
            text="UnobtainableSongName123",
            timeout_sec=0.5,
        )


# =============================================================================
# 4. UI Actions (Click, Type, Scroll, Keyevent) Tests
# =============================================================================

@pytest.mark.asyncio
async def test_device_click_element_coordinates_and_locators() -> None:
    """Verify element click by coordinates and by UI locators."""
    # Direct coordinates
    res_coord = await AndroidAutomationEngine.device_click_element(
        device_id="default",
        x=500,
        y=1000,
    )
    assert res_coord.success is True
    assert res_coord.action == "click"
    assert res_coord.target == "(500, 1000)"

    # By text locator
    res_text = await AndroidAutomationEngine.device_click_element(
        device_id="default",
        text="Bohemian",
    )
    assert res_text.success is True
    assert res_text.action == "click"
    assert res_text.details.get("x") is not None


@pytest.mark.asyncio
async def test_device_type_text() -> None:
    """Verify typing text into targeted or focused inputs."""
    res = await AndroidAutomationEngine.device_type_text(
        text="A Night at the Opera",
        device_id="default",
        resource_id="com.spotify.music:id/search_query",
        clear_first=True,
        press_enter=True,
    )
    assert res.success is True
    assert res.action == "type"
    assert res.target == "com.spotify.music:id/search_query"
    assert res.details.get("text") == "A Night at the Opera"


@pytest.mark.asyncio
async def test_device_scroll() -> None:
    """Verify scroll dispatch across all 4 directional axes."""
    for direction in ("down", "up", "left", "right"):
        res = await AndroidAutomationEngine.device_scroll(
            direction=direction,  # type: ignore[arg-type]
            device_id="default",
            distance_px=600,
        )
        assert res.success is True
        assert res.action == "scroll"
        assert res.target == direction


@pytest.mark.asyncio
async def test_device_press_key() -> None:
    """Verify hardware and navigation key events."""
    for key in ("back", "home", "enter", "app_switch"):
        res = await AndroidAutomationEngine.device_press_key(key, device_id="default")
        assert res.success is True
        assert res.action == "keyevent"
        assert res.details.get("keycode") == ANDROID_KEY_CODES[key]


# =============================================================================
# 5. Android Intent Engine Tests
# =============================================================================

def test_build_adb_am_command() -> None:
    """Verify building of exact 'adb shell am start/broadcast/startservice' CLI commands."""
    intent = AndroidIntentRequest(
        action="android.intent.action.VIEW",
        data_uri="https://open.spotify.com/track/12345",
        package_name="com.spotify.music",
        component="com.spotify.music/.MainActivity",
        mime_type="audio/*",
        categories=["android.intent.category.DEFAULT", "android.intent.category.BROWSABLE"],
        extras={"query": "Queen", "auto_play": True, "volume": 10},
        flags=["FLAG_ACTIVITY_NEW_TASK", "FLAG_ACTIVITY_CLEAR_TOP"],
    )
    cmd = AndroidAutomationEngine.build_adb_am_command(intent, device_id="emulator-5554")

    assert cmd[0] == "adb"
    assert cmd[1] == "-s"
    assert cmd[2] == "emulator-5554"
    assert cmd[3] == "shell"
    assert cmd[4] == "am"
    assert cmd[5] == "start"
    assert "-a" in cmd and "android.intent.action.VIEW" in cmd
    assert "-d" in cmd and "https://open.spotify.com/track/12345" in cmd
    assert "-n" in cmd and "com.spotify.music/.MainActivity" in cmd
    assert "-t" in cmd and "audio/*" in cmd
    assert "--es" in cmd and "query" in cmd and "Queen" in cmd
    assert "--ez" in cmd and "auto_play" in cmd and "true" in cmd
    assert "--ei" in cmd and "volume" in cmd and "10" in cmd
    assert "-f" in cmd and "FLAG_ACTIVITY_NEW_TASK" in cmd


@pytest.mark.asyncio
async def test_device_send_intent() -> None:
    """Verify intent dispatch execution."""
    intent = AndroidIntentRequest(
        action="android.intent.action.VIEW",
        data_uri="spotify:track:4u7EnebtmKWzUH433cf5Qv",
        package_name="com.spotify.music",
    )
    res = await AndroidAutomationEngine.device_send_intent(intent, device_id="default")
    assert res.success is True
    assert res.action == "intent"
    assert res.target == "com.spotify.music"


# =============================================================================
# 6. Deep Links & Universal Links Engine Tests
# =============================================================================

def test_resolve_deep_link() -> None:
    """Verify resolution of URI schemes, parameter injection, and package auto-detection."""
    req = AndroidDeepLinkRequest(
        url_or_uri="spotify://play",
        parameters={"track": "bohemian_rhapsody", "autoplay": "true"},
    )
    intent = AndroidAutomationEngine.resolve_deep_link(req)
    assert intent.action == "android.intent.action.VIEW"
    assert intent.package_name == "com.spotify.music"
    assert "track=bohemian_rhapsody" in (intent.data_uri or "")
    assert "autoplay=true" in (intent.data_uri or "")


@pytest.mark.asyncio
async def test_device_open_deep_link() -> None:
    """Verify deep link execution with web fallback."""
    req = AndroidDeepLinkRequest(
        url_or_uri="whatsapp://send?text=Hello",
        fallback_url="https://web.whatsapp.com",
    )
    res = await AndroidAutomationEngine.device_open_deep_link(req, device_id="default")
    assert res.success is True
    assert res.action == "intent"


# =============================================================================
# 7. Screen Capture & Screenshot Tests
# =============================================================================

@pytest.mark.asyncio
async def test_device_take_screenshot() -> None:
    """Verify capturing Base64 PNG screenshot with valid image header."""
    shot = await AndroidAutomationEngine.device_take_screenshot(device_id="default")
    assert isinstance(shot, AndroidScreenshotResponse)
    assert shot.width == 1080
    assert shot.height == 2400
    assert shot.image_base64 is not None

    # Decode and verify PNG header magic bytes: \x89PNG\r\n\x1a\n
    raw_bytes = base64.b64decode(shot.image_base64)
    assert raw_bytes[:8] == b"\x89PNG\r\n\x1a\n"


# =============================================================================
# 8. Android Companion Protocol Tests
# =============================================================================

@pytest.mark.asyncio
async def test_companion_manager_lifecycle_and_duplex_command() -> None:
    """Verify enrollment, heartbeat telemetry, and duplex command dispatch."""
    mgr = AndroidCompanionManager.get_instance()
    dev_id = "test_pixel_7"

    # 1. Telemetry heartbeat
    telemetry = AndroidCompanionTelemetry(
        device_id=dev_id,
        battery_level=88,
        is_charging=True,
        screen_on=True,
        foreground_package="com.spotify.music",
        foreground_activity="com.spotify.music.MainActivity",
    )
    mgr.update_telemetry(telemetry)
    cached_tel = mgr.get_telemetry(dev_id)
    assert cached_tel is not None
    assert cached_tel.battery_level == 88
    assert cached_tel.foreground_package == "com.spotify.music"

    # 2. Companion Connection & Command Dispatch
    class MockCompanionTransport:
        def __init__(self) -> None:
            self.sent_envelopes: list[dict[str, Any]] = []

        async def send_json(self, data: dict[str, Any]) -> None:
            self.sent_envelopes.append(data)
            # Immediately resolve command asynchronously
            resp = AndroidCompanionResponse(
                command_id=data["command_id"],
                success=True,
                output={"status": "clicked", "coords": [500, 1000]},
                duration_ms=45.0,
            )
            mgr.resolve_command(resp)

    transport = MockCompanionTransport()
    mgr.register_connection(dev_id, transport)
    assert mgr.is_connected(dev_id) is True

    env = AndroidCompanionEnvelope(
        command_id=f"cmd_{int(time.time() * 1000)}",
        action="ui_click",
        parameters={"x": 500, "y": 1000},
        timeout_ms=3000,
    )
    resp = await mgr.send_command(dev_id, env)
    assert resp.success is True
    assert resp.output.get("status") == "clicked"

    # 3. Disconnect
    mgr.unregister_connection(dev_id)
    assert mgr.is_connected(dev_id) is False


# =============================================================================
# 9. ToolRegistry Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_tool_registry_android_tools() -> None:
    """Verify all 9 android_* tools are registered and executable in ToolRegistry."""
    registry = ToolRegistry.get_instance()
    DeviceService.get_instance().register_device_tools()

    expected_tools = [
        "android_inspect_ui",
        "android_find_element",
        "android_click_element",
        "android_type_text",
        "android_scroll",
        "android_press_key",
        "android_send_intent",
        "android_open_deep_link",
        "android_take_screenshot",
    ]

    for tool_id in expected_tools:
        tool = registry.get(tool_id)
        assert tool is not None, f"Tool '{tool_id}' not found in ToolRegistry."
        assert "mobile" in tool.capabilities
        assert "android" in tool.capabilities

    # Test executing android_inspect_ui via ToolRegistry
    exec_req = ToolExecutionRequest(
        tool_id="android_inspect_ui",
        arguments={"device_id": "default", "max_depth": 3},
        user_id="test_user",
    )
    result = await registry.execute(exec_req)
    assert result.success is True
    assert result.output.get("class_name") is not None


# =============================================================================
# 10. UniversalAppController Integration Tests (mobile_bridge)
# =============================================================================

@pytest.mark.asyncio
async def test_universal_controller_mobile_bridge() -> None:
    """Verify UniversalAppController plans, executes, and verifies via mobile_bridge."""
    controller = UniversalAppController.get_instance()

    req = AppControlExecutionRequest(
        application="com.spotify.music",
        capability="intent",
        parameters={
            "action": "android.intent.action.VIEW",
            "data_uri": "spotify:track:4u7EnebtmKWzUH433cf5Qv",
        },
        preferred_integration="mobile_bridge",
        confirmed=True,
        skip_verification=False,
    )
    result = await controller.execute_lifecycle(req)
    assert result.success is True
    assert result.stage == "verified"
    assert result.plan is not None
    assert result.plan.chosen_integration == "mobile_bridge"
    assert len(result.plan.steps) == 3
    assert result.verification.get("verified") is True


# =============================================================================
# 11. REST API Endpoints Tests
# =============================================================================

@pytest.mark.asyncio
async def test_android_api_endpoints(mock_user: User) -> None:
    """Verify all Android REST endpoints via FastAPI AsyncClient."""
    app.dependency_overrides[get_current_user] = lambda: mock_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. GET /devices/{device_id}/android/inspect
        resp_inspect = await client.get("/api/v1/devices/pixel_7/android/inspect?max_depth=3")
        assert resp_inspect.status_code == 200
        data_inspect = resp_inspect.json()
        assert "class_name" in data_inspect

        # 2. POST /devices/{device_id}/android/find
        resp_find = await client.post("/api/v1/devices/pixel_7/android/find?text=Bohemian")
        assert resp_find.status_code == 200
        data_find = resp_find.json()
        assert data_find.get("text") == "Bohemian Rhapsody"

        # 3. POST /devices/{device_id}/android/click
        resp_click = await client.post(
            "/api/v1/devices/pixel_7/android/click",
            json={"text": "Bohemian"},
        )
        assert resp_click.status_code == 200
        assert resp_click.json()["success"] is True

        # 4. POST /devices/{device_id}/android/type
        resp_type = await client.post(
            "/api/v1/devices/pixel_7/android/type",
            json={"text": "Queen", "resource_id": "com.spotify.music:id/search_query"},
        )
        assert resp_type.status_code == 200
        assert resp_type.json()["success"] is True

        # 5. POST /devices/{device_id}/android/scroll
        resp_scroll = await client.post(
            "/api/v1/devices/pixel_7/android/scroll",
            json={"direction": "down", "distance_px": 600},
        )
        assert resp_scroll.status_code == 200
        assert resp_scroll.json()["success"] is True

        # 6. POST /devices/{device_id}/android/key
        resp_key = await client.post(
            "/api/v1/devices/pixel_7/android/key",
            json={"key": "back"},
        )
        assert resp_key.status_code == 200
        assert resp_key.json()["success"] is True

        # 7. POST /devices/{device_id}/android/intent
        resp_intent = await client.post(
            "/api/v1/devices/pixel_7/android/intent",
            json={
                "action": "android.intent.action.VIEW",
                "data_uri": "spotify:track:123",
                "package_name": "com.spotify.music",
            },
        )
        assert resp_intent.status_code == 200
        assert resp_intent.json()["success"] is True

        # 8. POST /devices/{device_id}/android/deep-link
        resp_dl = await client.post(
            "/api/v1/devices/pixel_7/android/deep-link",
            json={"url_or_uri": "spotify://play", "parameters": {"track": "bohemian"}},
        )
        assert resp_dl.status_code == 200
        assert resp_dl.json()["success"] is True

        # 9. GET /devices/{device_id}/android/screenshot
        resp_shot = await client.get("/api/v1/devices/pixel_7/android/screenshot")
        assert resp_shot.status_code == 200
        assert resp_shot.json()["image_base64"] is not None

        # 10. POST /devices/android/companion/heartbeat
        resp_hb = await client.post(
            "/api/v1/devices/android/companion/heartbeat",
            json={
                "device_id": "pixel_7",
                "battery_level": 92,
                "is_charging": False,
                "screen_on": True,
                "foreground_package": "com.spotify.music",
            },
        )
        assert resp_hb.status_code == 200
        assert resp_hb.json()["status"] == "recorded"

    app.dependency_overrides.clear()
