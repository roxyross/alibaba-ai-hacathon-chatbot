"""Comprehensive automated test suite for Phase 4: Local Application Discovery Engine.

Tests:
1. Intelligent categorization engine across software archetypes.
2. Capability derivation and supported action mapping.
3. Multi-platform native and preset app scanning.
4. Real-time active process correlation with PID and resource metrics.
5. Deduplication and metadata normalization.
6. Service-level scanning and database upsert idempotency.
7. Advanced search, categorization filters, and pagination.
8. Single app metadata lookup.
9. Remote daemon catalog synchronization.
10. FastAPI REST API endpoints for app discovery and catalog search.
"""

from __future__ import annotations

import platform
import uuid
from typing import Any

import httpx
import pytest

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.daemon import RoxyDeviceAgent, get_hardware_fingerprint
from app.device.scanner import (
    CATEGORIES,
    DeepAppScanner,
    categorize_app,
    correlate_running_processes,
    deduplicate_and_enrich_apps,
    get_curated_preset_apps,
    infer_capabilities,
    infer_supported_actions,
)
from app.device.service import DeviceService
from app.main import app


@pytest.fixture(autouse=True)
def clean_device_state() -> None:
    """Ensure in-memory device and app state is reset before each test."""
    service = DeviceService.get_instance()
    service.clear_in_memory_state()


# -----------------------------------------------------------------------------
# 1. Intelligent Categorization Engine
# -----------------------------------------------------------------------------

def test_categorize_app_archetypes() -> None:
    """Verify categorization engine accurately maps diverse software to canonical categories."""
    test_cases = [
        # Browsers
        ("Google Chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe", "browser"),
        ("Mozilla Firefox", "/usr/bin/firefox", "browser"),
        ("Microsoft Edge", "msedge.exe", "browser"),
        ("Brave Browser", "/Applications/Brave Browser.app", "browser"),
        # Development
        ("Visual Studio Code", "Code.exe", "development"),
        ("Windows Terminal", "wt.exe", "development"),
        ("PyCharm Community Edition", "pycharm64.exe", "development"),
        ("Docker Desktop", "Docker Desktop.exe", "development"),
        # Productivity
        ("Microsoft Word", "WINWORD.EXE", "productivity"),
        ("Notion", "Notion.exe", "productivity"),
        ("Obsidian", "Obsidian.exe", "productivity"),
        # Communication
        ("Slack", "slack.exe", "communication"),
        ("Discord", "Discord.exe", "communication"),
        ("Zoom Workplace", "Zoom.exe", "communication"),
        # Media
        ("Spotify", "Spotify.exe", "media"),
        ("VLC media player", "vlc.exe", "media"),
        ("Adobe Photoshop", "Photoshop.exe", "media"),
        # Gaming & Design
        ("Steam", "Steam.exe", "gaming"),
        ("Figma", "Figma.exe", "design"),
        # Security & System
        ("Bitwarden", "Bitwarden.exe", "security"),
        ("Task Manager", "taskmgr.exe", "system"),
    ]

    for name, path, expected_cat in test_cases:
        actual_cat = categorize_app(name, path)
        assert actual_cat == expected_cat, f"Expected '{name}' to be '{expected_cat}', got '{actual_cat}'"


# -----------------------------------------------------------------------------
# 2. Automated Capability and Supported Actions Derivation
# -----------------------------------------------------------------------------

def test_infer_capabilities_and_actions() -> None:
    """Verify domain-specific capabilities and verbs are derived from category and app identity."""
    # Media Player
    media_caps = infer_capabilities("media", "Spotify")
    media_actions = infer_supported_actions("media", "Spotify")
    assert "audio_playback" in media_caps
    assert "media_transport_controls" in media_caps
    assert "play" in media_actions
    assert "pause" in media_actions
    assert "next_track" in media_actions

    # Web Browser
    browser_caps = infer_capabilities("browser", "Google Chrome")
    browser_actions = infer_supported_actions("browser", "Google Chrome")
    assert "web_browsing" in browser_caps
    assert "tab_navigation" in browser_caps
    assert "open_url" in browser_actions
    assert "reload" in browser_actions

    # Development Tool
    dev_caps = infer_capabilities("development", "Visual Studio Code")
    dev_actions = infer_supported_actions("development", "Visual Studio Code")
    assert "code_editing" in dev_caps
    assert "terminal_execution" in dev_caps
    assert "open_directory" in dev_actions


# -----------------------------------------------------------------------------
# 3. Deep System Scanner Execution
# -----------------------------------------------------------------------------

def test_deep_app_scanner_execution() -> None:
    """Verify DeepAppScanner returns complete, enriched, and valid application items."""
    apps = DeepAppScanner.scan_system(include_system_apps=False)
    assert len(apps) >= 10

    for a in apps:
        assert "name" in a and a["name"]
        assert "executable_path" in a and a["executable_path"]
        assert a["category"] in CATEGORIES
        assert isinstance(a["capabilities"], list) and len(a["capabilities"]) >= 1
        assert isinstance(a["supported_actions"], list) and len(a["supported_actions"]) >= 1
        assert "is_running" in a
        assert isinstance(a["is_running"], bool)


# -----------------------------------------------------------------------------
# 4. Real-Time Active Process Correlation
# -----------------------------------------------------------------------------

def test_correlate_running_processes() -> None:
    """Verify running processes are correctly correlated with active PIDs and metrics."""
    test_apps = [
        {"name": "Python Interpreter", "executable_path": "python.exe"},
        {"name": "Imaginary App XYZ", "executable_path": r"C:\fake\path\nonexistent_app_123.exe"},
    ]

    correlated = correlate_running_processes(test_apps)
    # The active Python test runner itself is executing, so python must be matched as running
    python_app = next((a for a in correlated if "python" in a["name"].lower()), None)
    assert python_app is not None
    assert python_app["is_running"] is True
    assert python_app["process_id"] is not None
    assert python_app["process_id"] > 0

    fake_app = next(a for a in correlated if "nonexistent" in a["executable_path"])
    assert fake_app["is_running"] is False
    assert fake_app["process_id"] is None


# -----------------------------------------------------------------------------
# 5. Deduplication and Normalization
# -----------------------------------------------------------------------------

def test_deduplicate_and_enrich_apps() -> None:
    """Verify canonical name normalization and merging of redundant entries."""
    raw_list = [
        {
            "name": "Google Chrome (64-bit)",
            "executable_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "version": "128.0",
            "publisher": "Google LLC",
            "is_running": False,
        },
        {
            "name": "Google Chrome",
            "executable_path": "chrome.exe",
            "version": "128.0.1",
            "is_running": True,
            "process_id": 4321,
        },
    ]

    deduped = deduplicate_and_enrich_apps(raw_list)
    assert len(deduped) == 1
    item = deduped[0]
    assert item["name"] == "Google Chrome"
    assert item["category"] == "browser"
    assert item["publisher"] == "Google LLC"
    assert item["is_running"] is True
    assert item["process_id"] == 4321


# -----------------------------------------------------------------------------
# 6. Service-Level Scanning & Database Upsert Idempotency
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_scan_installed_apps_idempotency() -> None:
    """Verify scan_installed_apps creates and updates records without duplicating."""
    service = DeviceService.get_instance()
    user_id = "user_scan_test"
    device_id = "device_scan_node"

    # First scan
    first_scan = await service.scan_installed_apps(user_id=user_id, device_id=device_id)
    assert len(first_scan) >= 10
    initial_count = len(first_scan)

    # Second scan with force_refresh
    second_scan = await service.scan_installed_apps(user_id=user_id, device_id=device_id, force_refresh=True)
    assert len(second_scan) == initial_count

    # App list should match the same count (not double)
    apps = await service.list_apps(user_id=user_id, device_id=device_id, limit=500)
    assert len(apps) == initial_count


# -----------------------------------------------------------------------------
# 7. Advanced Search, Filtering, and Pagination
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_list_apps_filtering_and_search() -> None:
    """Verify list_apps supports category filters, running status, and text search."""
    service = DeviceService.get_instance()
    user_id = "user_filter_test"
    device_id = "device_filter_node"

    await service.scan_installed_apps(user_id=user_id, device_id=device_id)

    # 1. Filter by category
    browsers = await service.list_apps(user_id=user_id, device_id=device_id, category="browser")
    assert len(browsers) >= 1
    assert all(b["category"] == "browser" for b in browsers)

    dev_apps = await service.list_apps(user_id=user_id, device_id=device_id, category="development")
    assert len(dev_apps) >= 1
    assert all(d["category"] == "development" for d in dev_apps)

    # 2. Text Search
    search_res = await service.list_apps(user_id=user_id, device_id=device_id, search="code")
    assert len(search_res) >= 1
    assert any("code" in a["app_name"].lower() for a in search_res)

    # 3. Pagination
    page_1 = await service.list_apps(user_id=user_id, device_id=device_id, limit=3, offset=0)
    page_2 = await service.list_apps(user_id=user_id, device_id=device_id, limit=3, offset=3)
    assert len(page_1) == 3
    assert len(page_2) <= 3
    assert page_1[0]["id"] != page_2[0]["id"]


# -----------------------------------------------------------------------------
# 8. Single App Metadata Details Lookup
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_get_app_details() -> None:
    """Verify retrieval of detailed metadata and capabilities for a specific app."""
    service = DeviceService.get_instance()
    user_id = "user_detail_test"
    device_id = "device_detail_node"

    apps = await service.scan_installed_apps(user_id=user_id, device_id=device_id)
    first_app = apps[0]

    # Query by app_id
    detail_by_id = await service.get_app_details(user_id=user_id, device_id=device_id, app_id_or_name=first_app["id"])
    assert detail_by_id is not None
    assert detail_by_id["app_name"] == first_app["app_name"]
    assert "capabilities" in detail_by_id
    assert "supported_actions" in detail_by_id

    # Query by exact app name
    detail_by_name = await service.get_app_details(user_id=user_id, device_id=device_id, app_id_or_name=first_app["app_name"])
    assert detail_by_name is not None
    assert detail_by_name["id"] == first_app["id"]

    # Nonexistent lookup
    assert await service.get_app_details(user_id=user_id, device_id=device_id, app_id_or_name="GhostAppDoesNotExist") is None


# -----------------------------------------------------------------------------
# 9. Remote Daemon Catalog Synchronization
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daemon_catalog_sync() -> None:
    """Verify bulk sync of apps reported from a standalone agent daemon."""
    service = DeviceService.get_instance()
    user_id = "user_daemon_sync_test"
    device_id = "device_remote_worker"

    daemon_reported_apps = [
        {
            "name": "Custom Engineering CAD",
            "executable_path": "/opt/cad/cad.bin",
            "category": "design",
            "version": "4.2",
            "publisher": "AutoCAD Systems",
            "capabilities": ["3d_modeling", "mesh_export"],
            "supported_actions": ["launch", "close", "render"],
        },
        {
            "name": "Internal DB Terminal",
            "executable_path": "/usr/local/bin/dbterm",
            "category": "development",
            "version": "1.0",
            "capabilities": ["sql_execution", "tunneling"],
            "supported_actions": ["launch", "close"],
        },
    ]

    synced_count = await service.sync_device_apps(
        user_id=user_id,
        device_id=device_id,
        apps=daemon_reported_apps,
    )
    assert synced_count == 2

    stored = await service.list_apps(user_id=user_id, device_id=device_id)
    assert len(stored) == 2
    cad_app = next(a for a in stored if a["app_name"] == "Custom Engineering CAD")
    assert cad_app["category"] == "design"
    assert "3d_modeling" in cad_app["capabilities"]
    assert "render" in cad_app["supported_actions"]


# -----------------------------------------------------------------------------
# 10. FastAPI REST API Endpoints Integration
# -----------------------------------------------------------------------------

@pytest.mark.anyio
async def test_app_discovery_api_router_lifecycle(async_client: httpx.AsyncClient) -> None:
    """Verify scanning, listing, searching, single lookup, and daemon sync via REST API."""
    test_user = User(id="user_api_discovery", email="discovery_api@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user

    service = DeviceService.get_instance()

    try:
        # 1. Enroll a test device to obtain credentials
        tok = await service.create_enrollment_token(user_id=test_user.id)
        claim = await service.claim_enrollment({
            "enrollment_token": tok["token"],
            "device_name": "API Test Workstation",
            "hardware_fingerprint": "hwfp_api_discovery_node",
            "os_platform": platform.system().lower(),
            "hostname": "discovery-pc",
        })
        dev_id = claim["device_id"]
        dev_token = claim["device_token"]

        # 2. Trigger application scan
        scan_resp = await async_client.post(
            f"/api/v1/devices/{dev_id}/apps/scan",
            json={"force_refresh": True, "include_system_apps": False},
        )
        assert scan_resp.status_code == 200
        scan_data = scan_resp.json()
        assert scan_data["device_id"] == dev_id
        assert scan_data["scanned_count"] >= 10
        assert "categories_summary" in scan_data
        assert "scan_duration_ms" in scan_data

        discovered_list = scan_data["discovered_apps"]
        test_app_id = discovered_list[0]["id"]
        test_app_name = discovered_list[0]["app_name"]

        # 3. List apps with search query
        search_resp = await async_client.get(
            f"/api/v1/devices/{dev_id}/apps?search={test_app_name[:4]}&limit=5"
        )
        assert search_resp.status_code == 200
        search_list = search_resp.json()
        assert len(search_list) >= 1

        # 4. Get single app details
        detail_resp = await async_client.get(f"/api/v1/devices/{dev_id}/apps/{test_app_id}")
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["id"] == test_app_id
        assert detail_data["app_name"] == test_app_name
        assert "capabilities" in detail_data
        assert "supported_actions" in detail_data

        # 5. Daemon bulk sync endpoint with X-Device-Token authentication
        sync_resp = await async_client.post(
            f"/api/v1/devices/{dev_id}/apps/sync",
            headers={"X-Device-Token": dev_token},
            json={
                "apps": [
                    {
                        "name": "Proprietary Data Miner",
                        "executable_path": "/opt/miner/bin",
                        "category": "finance",
                        "version": "3.1",
                    }
                ]
            },
        )
        assert sync_resp.status_code == 200
        sync_result = sync_resp.json()
        assert sync_result["synced_count"] == 1

        # 6. Verify newly synced app appears in catalog
        miner_check = await async_client.get(f"/api/v1/devices/{dev_id}/apps?search=Miner")
        assert miner_check.status_code == 200
        assert len(miner_check.json()) == 1
        assert miner_check.json()[0]["app_name"] == "Proprietary Data Miner"

    finally:
        app.dependency_overrides.pop(get_current_user, None)
