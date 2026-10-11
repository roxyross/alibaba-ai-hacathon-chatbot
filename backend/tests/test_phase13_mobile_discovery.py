"""Phase 13 Test Suite: Mobile App Discovery + Capability Resolution.

Validates:
1. MobileAppRegistry & Authoritative Catalogs (Android & iOS built-ins).
2. Authoritative metadata for every app: package/bundle identifier, name, version,
   supported intents, deep links, share targets, app intents, known integrations,
   permissions, and automation capabilities.
3. MobileCapabilityRegistry dynamic capability synthesis, schema generation,
   risk classifications, and Zero Simulation Doctrine boundary enforcement on iOS.
4. Device discovery workflows (ADB inspection, Companion protocol, and hybrid fallbacks).
5. MobileIntegrationResolver following the Universal Integration Priority:
   Cloud Connector -> App Intent / Shortcut -> Universal Link / Custom Scheme -> Explicit Intent -> Share Sheet -> UI Automation.
6. IntegrationResolver Tier 6 (mobile_bridge) integration with MobileIntegrationResolver.
7. Central ToolRegistry tool execution for all 4 mobile tools.
8. REST API endpoints (discover, apps, app detail, capabilities, resolve).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.integration_resolver import IntegrationResolver
from app.device.mobile_registry import (
    ANDROID_KNOWN_APPS,
    IOS_KNOWN_APPS_CATALOG,
    MobileAppRegistry,
    MobileCapabilityRegistry,
    MobileIntegrationResolver,
)
from app.device.schemas import (
    IntegrationResolutionRequest,
    MobileAppDiscoveryRequest,
    MobileCapabilityResolutionRequest,
)
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest


@pytest.fixture
def mock_user() -> User:
    return User(
        id=str(uuid.uuid4()),
        email="mobile_tester@roxy.ai",
    )


@pytest.fixture
def clean_registry() -> tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]:
    cap_reg = MobileCapabilityRegistry()
    app_reg = MobileAppRegistry(cap_reg)
    resolver = MobileIntegrationResolver(app_reg, cap_reg)
    return app_reg, cap_reg, resolver


# =============================================================================
# 1. Authoritative Mobile Catalogs & Metadata Integrity
# =============================================================================

def test_authoritative_android_catalog_completeness() -> None:
    """Validate that the built-in Android catalog contains rich, valid metadata."""
    assert len(ANDROID_KNOWN_APPS) >= 12
    for pkg, meta in ANDROID_KNOWN_APPS.items():
        assert "." in pkg, f"Package name {pkg} must be in dot notation"
        assert "name" in meta and meta["name"]
        assert "category" in meta
        assert "version" in meta
        assert isinstance(meta.get("supported_intents"), list)
        assert isinstance(meta.get("deep_links"), list)
        assert isinstance(meta.get("share_targets"), list)
        assert isinstance(meta.get("app_intents"), list)
        assert isinstance(meta.get("known_integrations"), list)
        assert isinstance(meta.get("permissions"), list)


def test_authoritative_ios_catalog_completeness() -> None:
    """Validate that the built-in iOS catalog contains rich, valid metadata."""
    assert len(IOS_KNOWN_APPS_CATALOG) >= 12
    for bundle, meta in IOS_KNOWN_APPS_CATALOG.items():
        assert "." in bundle, f"Bundle ID {bundle} must be in reverse domain notation"
        assert "name" in meta and meta["name"]
        assert "category" in meta
        assert "version" in meta
        assert isinstance(meta.get("supported_intents"), list)
        assert isinstance(meta.get("deep_links"), list)
        assert isinstance(meta.get("share_targets"), list)
        assert isinstance(meta.get("app_intents"), list)
        assert isinstance(meta.get("known_integrations"), list)
        assert isinstance(meta.get("permissions"), list)


def test_mobile_app_model_metadata_verification(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test that MobileAppRegistry instantiates models with all Phase 13 required fields."""
    app_reg, _, _ = clean_registry

    # Check Android Spotify
    spotify = app_reg.get_app("com.spotify.music", platform="android")
    assert spotify is not None
    assert spotify.name == "Spotify"
    assert spotify.platform == "android"
    assert "android.media.action.MEDIA_PLAY_FROM_SEARCH" in spotify.supported_intents
    assert "spotify:" in spotify.deep_links
    assert "text/plain" in spotify.share_targets
    assert "actions.intent.PLAY_MUSIC" in spotify.app_intents
    assert "connector" in spotify.known_integrations
    assert "android.permission.INTERNET" in spotify.permissions
    assert len(spotify.automation_capabilities) > 0

    # Check iOS Spotify
    ios_spotify = app_reg.get_app("com.spotify.client", platform="ios")
    assert ios_spotify is not None
    assert ios_spotify.name == "Spotify"
    assert ios_spotify.platform == "ios"
    assert "spotify:" in ios_spotify.deep_links
    assert "https://open.spotify.com" in ios_spotify.deep_links
    assert "PlayMusicIntent" in ios_spotify.app_intents
    assert "connector" in ios_spotify.known_integrations
    assert len(ios_spotify.automation_capabilities) > 0


# =============================================================================
# 2. Capability Synthesis & Zero Simulation Boundary
# =============================================================================

def test_capability_synthesis_android(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test synthesis of Android capabilities (intents, deep links, share, UI)."""
    app_reg, _, _ = clean_registry
    whatsapp = app_reg.get_app("com.whatsapp", platform="android")
    assert whatsapp is not None

    cap_types = {c.capability_type for c in whatsapp.automation_capabilities}
    assert "intent" in cap_types
    assert "url_scheme" in cap_types or "deep_link" in cap_types
    assert "share_sheet" in cap_types
    assert "ui_automation" in cap_types

    # Verify UI automation capability uses real android_ui adapter
    ui_cap = next(c for c in whatsapp.automation_capabilities if c.capability_type == "ui_automation")
    assert ui_cap.execution_adapter == "android_ui"
    assert ui_cap.verification_strategy == "mobile_ui_dump_match"
    assert ui_cap.confidence == 0.85


def test_capability_synthesis_ios_zero_simulation(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test synthesis of iOS capabilities and strict Zero Simulation enforcement."""
    app_reg, _, _ = clean_registry
    slack = app_reg.get_app("com.tinyspeck.chatlyio", platform="ios")
    assert slack is not None

    cap_types = {c.capability_type for c in slack.automation_capabilities}
    assert "connector" in cap_types
    assert "app_intent" in cap_types
    assert "shortcut" in cap_types
    assert "url_scheme" in cap_types or "universal_link" in cap_types

    # Verify UI automation is declared unsupported on iOS
    ui_cap = next(c for c in slack.automation_capabilities if c.capability_type == "ui_automation")
    assert ui_cap.execution_adapter == "unsupported"
    assert ui_cap.confidence == 0.0
    assert "iOS security sandbox" in ui_cap.description
    assert ui_cap.parameters.get("status") == "unsupported_on_this_platform"


# =============================================================================
# 3. Mobile App Discovery (ADB, Companion, and Fallback)
# =============================================================================

def test_device_discovery_companion_protocol(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test app discovery populated via an enrolled Companion protocol payload."""
    app_reg, _, _ = clean_registry
    req = MobileAppDiscoveryRequest(
        device_id="iphone_companion_01",
        platform="ios",
        companion_catalog=[
            {
                "bundle_id": "com.spotify.client",
                "name": "Spotify",
                "version": "8.9.22",
                "category": "media",
            },
            {
                "bundle_id": "com.custom.internalapp",
                "name": "Acme Internal",
                "version": "2.1.0",
                "category": "productivity",
                "deep_links": ["acme://open"],
            },
        ],
    )

    res = app_reg.discover_device_apps(req)
    assert res.total_apps == 2
    assert res.scan_source == "companion_protocol"

    # Verify Acme custom app was registered with synthesized capabilities
    acme = app_reg.get_app("com.custom.internalapp", platform="ios", device_id="iphone_companion_01")
    assert acme is not None
    assert acme.name == "Acme Internal"
    assert len(acme.automation_capabilities) > 0


def test_device_discovery_adb_subsystem_mock(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test Android ADB subprocess package list discovery."""
    app_reg, _, _ = clean_registry

    mock_adb_output = (
        "package:com.spotify.music\n"
        "package:com.whatsapp\n"
        "package:com.thirdparty.customapp\n"
    )

    with (
        patch("shutil.which", return_value="C:\\Android\\platform-tools\\adb.exe"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_adb_output)
        req = MobileAppDiscoveryRequest(
            device_id="emulator-5554",
            platform="android",
        )
        res = app_reg.discover_device_apps(req)
        assert res.scan_source == "adb_subsystem"
        assert res.total_apps == 3
        pkg_names = {a.package_or_bundle_id for a in res.apps}
        assert "com.spotify.music" in pkg_names
        assert "com.thirdparty.customapp" in pkg_names


def test_device_discovery_known_catalog_fallback(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test discovery fallback to authoritative catalog when device has no active bridge."""
    app_reg, _, _ = clean_registry
    req = MobileAppDiscoveryRequest(
        device_id="unconnected_device_99",
        platform="android",
        include_system_apps=False,
    )
    res = app_reg.discover_device_apps(req)
    assert res.scan_source == "known_catalog"
    assert res.total_apps >= 8
    # Ensure system apps excluded
    for a in res.apps:
        assert not a.is_system_app


# =============================================================================
# 4. Mobile Integration Resolver (Priority Hierarchy & Zero Simulation)
# =============================================================================

def test_resolve_priority_1_cloud_connector(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test that Cloud Connector is prioritized for apps that support it (e.g. Spotify)."""
    _, _, resolver = clean_registry
    req = MobileCapabilityResolutionRequest(
        package_or_bundle_id="com.spotify.music",
        requested_capability="play_music",
        platform="android",
    )
    res = resolver.resolve_capability(req)
    assert res.success is True
    assert res.integration_type == "connector"
    assert res.confidence == 0.98
    assert res.execution_adapter == "cloud_connector"
    assert "spotify_play_track" in res.resolved_parameters.get("tool_name", "")


def test_resolve_priority_2_ios_app_intent(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test resolution of iOS 16+ App Intents."""
    _, _, resolver = clean_registry
    req = MobileCapabilityResolutionRequest(
        package_or_bundle_id="net.whatsapp.WhatsApp",
        requested_capability="intent_send_message",
        platform="ios",
    )
    res = resolver.resolve_capability(req)
    assert res.success is True
    assert res.integration_type == "app_intent"
    assert res.confidence == 0.95
    assert res.execution_adapter == "ios_app_intent"
    assert res.verification_strategy == "ios_app_intent_probe"


def test_resolve_priority_3_deep_link(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test resolution of Universal Links and Custom Schemes."""
    _, _, resolver = clean_registry
    req = MobileCapabilityResolutionRequest(
        package_or_bundle_id="com.atebits.Tweetie2",
        requested_capability="open_link",
        platform="ios",
    )
    res = resolver.resolve_capability(req)
    assert res.success is True
    assert res.integration_type in ("universal_link", "url_scheme")
    assert res.confidence == 0.92
    assert res.execution_adapter in ("ios_universal_link", "ios_url_scheme")


def test_resolve_priority_4_android_intent(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test resolution of explicit Android Intent."""
    _, _, resolver = clean_registry
    req = MobileCapabilityResolutionRequest(
        package_or_bundle_id="com.google.android.dialer",
        requested_capability="dial",
        platform="android",
    )
    res = resolver.resolve_capability(req)
    assert res.success is True
    assert res.integration_type == "intent"
    assert res.confidence == 0.90
    assert res.execution_adapter == "android_intent"
    assert res.verification_strategy == "mobile_intent_and_ui_hierarchy"


def test_resolve_priority_5_share_sheet(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test resolution of Share Sheet capability."""
    _, _, resolver = clean_registry
    req = MobileCapabilityResolutionRequest(
        package_or_bundle_id="com.apple.mobilemail",
        requested_capability="share_file",
        platform="ios",
    )
    res = resolver.resolve_capability(req)
    assert res.success is True
    assert res.integration_type == "share_sheet"
    assert res.execution_adapter == "ios_share_sheet"
    assert res.verification_strategy == "ios_share_sheet_probe"


def test_resolve_android_ui_automation(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test resolution of Android UI Automation for interactive actions."""
    _, _, resolver = clean_registry
    req = MobileCapabilityResolutionRequest(
        package_or_bundle_id="com.google.android.calculator",
        requested_capability="click_button",
        platform="android",
    )
    res = resolver.resolve_capability(req)
    assert res.success is True
    assert res.integration_type == "ui_automation"
    assert res.execution_adapter == "android_ui"
    assert res.verification_strategy == "mobile_ui_dump_match"


def test_resolve_ios_ui_automation_honest_unsupported(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test that iOS UI touch automation returns honest unsupported under Zero Simulation."""
    _, _, resolver = clean_registry
    req = MobileCapabilityResolutionRequest(
        package_or_bundle_id="com.apple.mobilenotes",
        requested_capability="click_screen",
        platform="ios",
    )
    res = resolver.resolve_capability(req)
    assert res.success is False
    assert res.integration_type == "unsupported_on_this_platform"
    assert res.confidence == 0.0
    assert res.execution_adapter == "unsupported"
    assert "iOS platform sandbox security" in (res.remediation_guidance or "")
    assert len(res.alternatives) > 0


def test_resolve_unknown_application(clean_registry: tuple[MobileAppRegistry, MobileCapabilityRegistry, MobileIntegrationResolver]) -> None:
    """Test handling of completely unknown application."""
    _, _, resolver = clean_registry
    req = MobileCapabilityResolutionRequest(
        package_or_bundle_id="com.totally.nonexistent.app",
        requested_capability="open",
        platform="android",
    )
    res = resolver.resolve_capability(req)
    assert res.success is False
    assert "was not discovered on the device" in (res.remediation_guidance or "")


# =============================================================================
# 5. IntegrationResolver (Tier 6) Cross-System Integration
# =============================================================================

def test_integration_resolver_tier6_enhancement() -> None:
    """Verify that IntegrationResolver._evaluate_mobile_bridge enriches mobile candidates."""
    req = IntegrationResolutionRequest(
        application="com.spotify.music",
        requested_capability="play_music",
        device={"os_platform": "android", "device_id": "pixel_8"},
        preferred_integration="mobile_bridge",
    )
    res = IntegrationResolver.resolve(req)
    assert res.success is True
    assert res.chosen_integration == "mobile_bridge"
    assert res.confidence >= 0.85
    chosen_candidate = next(c for c in res.candidates if c.integration == "mobile_bridge")
    assert chosen_candidate.parameters.get("package_or_bundle_id") == "com.spotify.music"


# =============================================================================
# 6. ToolRegistry Tool Execution
# =============================================================================

@pytest.mark.asyncio
async def test_tool_registry_mobile_tools() -> None:
    """Validate registration and direct execution of all 4 mobile tools via ToolRegistry."""
    # Ensure DeviceService has initialized tools
    DeviceService.get_instance().register_device_tools()
    registry = ToolRegistry.get_instance()

    # 1. mobile_discover_apps
    disc_req = ToolExecutionRequest(
        user_id="default",
        tool_id="mobile_discover_apps",
        arguments={"device_id": "tool_test_device", "platform": "android"},
        client_context={"role": "admin"},
    )
    disc_res = await registry.execute(disc_req)
    assert disc_res.success is True
    assert disc_res.output is not None
    assert disc_res.output.get("total_apps", 0) > 0

    # 2. mobile_list_apps
    list_req = ToolExecutionRequest(
        user_id="default",
        tool_id="mobile_list_apps",
        arguments={"platform": "ios"},
        client_context={"role": "admin"},
    )
    list_res = await registry.execute(list_req)
    assert list_res.success is True
    assert list_res.output.get("total", 0) > 0

    # 3. mobile_get_app
    get_req = ToolExecutionRequest(
        user_id="default",
        tool_id="mobile_get_app",
        arguments={"package_or_bundle": "com.apple.Maps", "platform": "ios"},
        client_context={"role": "admin"},
    )
    get_res = await registry.execute(get_req)
    assert get_res.success is True
    assert get_res.output.get("found") is True
    assert get_res.output.get("app", {}).get("name") == "Apple Maps"

    # 4. mobile_resolve_capability
    res_req = ToolExecutionRequest(
        user_id="default",
        tool_id="mobile_resolve_capability",
        arguments={"package_or_bundle_id": "com.whatsapp", "requested_capability": "send_message", "platform": "android"},
        client_context={"role": "admin"},
    )
    res_result = await registry.execute(res_req)
    assert res_result.success is True
    assert res_result.output.get("success") is True
    assert res_result.output.get("integration_type") in ("intent", "app_intent", "deep_link", "connector")



# =============================================================================
# 7. REST API Endpoints Verification
# =============================================================================

@pytest.mark.asyncio
async def test_rest_api_mobile_discovery_endpoints(mock_user: User) -> None:
    """Validate FastAPI REST endpoints for mobile app discovery and resolution."""
    app.dependency_overrides[get_current_user] = lambda: mock_user
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. POST /devices/{id}/mobile/discover
        disc_resp = await client.post(
            "/api/v1/devices/rest_test_phone/mobile/discover",
            json={"device_id": "rest_test_phone", "platform": "android", "force_refresh": False},
        )
        assert disc_resp.status_code == 200
        disc_json = disc_resp.json()
        assert disc_json["total_apps"] > 0
        assert disc_json["platform"] == "android"

        # 2. GET /devices/{id}/mobile/apps
        list_resp = await client.get("/api/v1/devices/rest_test_phone/mobile/apps?platform=android")
        assert list_resp.status_code == 200
        apps_json = list_resp.json()
        assert len(apps_json) > 0

        # 3. GET /devices/{id}/mobile/apps/{package}
        app_resp = await client.get("/api/v1/devices/rest_test_phone/mobile/apps/com.spotify.music?platform=android")
        assert app_resp.status_code == 200
        app_json = app_resp.json()
        assert app_json["name"] == "Spotify"
        assert len(app_json["automation_capabilities"]) > 0

        # 4. GET /devices/{id}/mobile/apps/{package}/capabilities
        caps_resp = await client.get("/api/v1/devices/rest_test_phone/mobile/apps/com.spotify.music/capabilities?platform=android")
        assert caps_resp.status_code == 200
        caps_json = caps_resp.json()
        assert caps_json["total_capabilities"] > 0
        assert len(caps_json["capabilities"]) > 0

        # 5. POST /devices/{id}/mobile/resolve
        resolve_resp = await client.post(
            "/api/v1/devices/rest_test_phone/mobile/resolve",
            json={
                "package_or_bundle_id": "com.spotify.music",
                "requested_capability": "play_music",
                "platform": "android",
            },
        )
        assert resolve_resp.status_code == 200
        res_json = resolve_resp.json()
        assert res_json["success"] is True
        assert res_json["integration_type"] == "connector"

    app.dependency_overrides.clear()
