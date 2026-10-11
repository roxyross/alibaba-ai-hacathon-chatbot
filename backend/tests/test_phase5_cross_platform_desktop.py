"""Comprehensive Automated Test Suite for Phase 5: macOS + Linux Desktop UI Automation.

Validates:
1. Cross-Platform Desktop Automation Architecture:
   - Platform detection and adapter resolution (Windows, macOS, Linux).
   - Unified interface conforming to UIElementModel and WindowStateModel.
2. macOS UI Automation Engine:
   - Platform guards and honest non-Darwin handling.
   - AXUIElement role normalization and path parsing.
   - AppleScript output parsing for window state, screenshot, and element tree.
3. Linux UI Automation Engine:
   - Platform guards and honest display/tool requirement handling.
   - AT-SPI role normalization and wmctrl window geometry parsing.
4. Unified DesktopAutomationEngine Dispatch:
   - Passthrough to active native engine on host.
   - Real end-to-end desktop automation (Window state, UI inspection, typing, hotkey, screenshot).
   - Cross-platform platform_override capability.
5. Service & ToolRegistry Integration:
   - DeviceService methods dispatching via DesktopAutomationEngine.
   - AgentTool execution for desktop UI capabilities.
6. Daemon UI Command Dispatch:
   - RoxyDeviceDaemon executing ui_* commands via DesktopAutomationEngine.
7. Zero Simulation & Honest Error Handling:
   - Non-existent elements and windows raise honest errors/timeouts.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.auth.models import User
from app.device.daemon import RoxyDeviceDaemon
from app.device.desktop_automation import DesktopAutomationEngine
from app.device.linux_automation import LinuxUIAutomationEngine
from app.device.macos_automation import MacOSUIAutomationEngine
from app.device.service import DeviceService
from app.device.windows_automation import (
    UIBounds,
    UIElementModel,
    WindowsUIAutomationEngine,
    WindowStateModel,
)
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest, ToolExecutionStatus


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_user() -> User:
    """Mock authenticated user for device service testing."""
    return User(
        id="user_desktop_crossplat_test",
        email="crossplat@roxy.internal",
    )


# -----------------------------------------------------------------------------
# 1. Desktop Automation Platform Resolution
# -----------------------------------------------------------------------------

def test_desktop_engine_platform_resolution() -> None:
    """Verify platform detection and adapter routing."""
    active_plat = DesktopAutomationEngine.get_active_platform()
    assert active_plat in ("windows", "macos", "linux") or sys.platform in active_plat

    # Adapter mapping
    assert DesktopAutomationEngine.get_adapter("windows") is WindowsUIAutomationEngine
    assert DesktopAutomationEngine.get_adapter("win32") is WindowsUIAutomationEngine
    assert DesktopAutomationEngine.get_adapter("macos") is MacOSUIAutomationEngine
    assert DesktopAutomationEngine.get_adapter("darwin") is MacOSUIAutomationEngine
    assert DesktopAutomationEngine.get_adapter("osx") is MacOSUIAutomationEngine
    assert DesktopAutomationEngine.get_adapter("linux") is LinuxUIAutomationEngine
    assert DesktopAutomationEngine.get_adapter("ubuntu") is LinuxUIAutomationEngine

    # Unsupported platform
    with pytest.raises(NotImplementedError) as exc_info:
        DesktopAutomationEngine.get_adapter("freebsd")
    assert "not supported on platform" in str(exc_info.value)


def test_desktop_engine_is_available() -> None:
    """Verify is_available detects host capability honestly."""
    # On Windows host, windows should be available
    if sys.platform == "win32":
        assert DesktopAutomationEngine.is_available("windows") is True
        # macOS shouldn't be available on Windows
        assert DesktopAutomationEngine.is_available("macos") is False
    elif sys.platform == "darwin":
        assert DesktopAutomationEngine.is_available("macos") is True
        assert DesktopAutomationEngine.is_available("windows") is False
    elif sys.platform.startswith("linux"):
        assert DesktopAutomationEngine.is_available("windows") is False


# -----------------------------------------------------------------------------
# 2. macOS UI Automation Engine Unit Contract & Parsing
# -----------------------------------------------------------------------------

def test_macos_engine_guard_and_role_normalization() -> None:
    """Verify macOS engine honors platform constraints and role mappings."""
    if sys.platform != "darwin":
        assert MacOSUIAutomationEngine.is_available() is False
        with pytest.raises(RuntimeError) as exc_info:
            MacOSUIAutomationEngine.run_applescript('return "test"')
        assert "darwin" in str(exc_info.value)

    # Test application name resolver
    assert MacOSUIAutomationEngine._resolve_app_name("Calculator.app") == "Calculator"
    assert MacOSUIAutomationEngine._resolve_app_name("/Applications/Notes.app") == "Notes"
    assert MacOSUIAutomationEngine._resolve_app_name("Finder") == "Finder"
    assert MacOSUIAutomationEngine._resolve_app_name("") == ""

    # Test role normalizer
    assert MacOSUIAutomationEngine._normalize_macos_role("AXWindow") == "window"
    assert MacOSUIAutomationEngine._normalize_macos_role("AXButton") == "button"
    assert MacOSUIAutomationEngine._normalize_macos_role("AXTextField") == "edit"
    assert MacOSUIAutomationEngine._normalize_macos_role("AXTextArea") == "document"
    assert MacOSUIAutomationEngine._normalize_macos_role("AXMenuBar") == "menu_bar"
    assert MacOSUIAutomationEngine._normalize_macos_role("AXMenuItem") == "menu_item"
    assert MacOSUIAutomationEngine._normalize_macos_role("AXTable") == "table"
    assert MacOSUIAutomationEngine._normalize_macos_role("AXUnknownRandom") == "control"


def test_macos_engine_synthetic_output_parsing() -> None:
    """Verify AppleScript raw output is parsed into canonical UIElementModel."""
    synthetic_out = "Safari Window###100###150###1024###768###AXButton|||Back|||110|||160|||50|||30, AXTextField|||Search|||200|||160|||300|||30"

    with patch.object(MacOSUIAutomationEngine, "run_applescript", return_value=synthetic_out):
        with patch.object(MacOSUIAutomationEngine, "_resolve_app_name", return_value="Safari"):
            tree = MacOSUIAutomationEngine.device_inspect_ui("Safari", max_depth=2)

            assert isinstance(tree, UIElementModel)
            assert tree.role == "window"
            assert tree.name == "Safari Window"
            assert tree.bounds.left == 100
            assert tree.bounds.top == 150
            assert tree.bounds.width == 1024
            assert tree.bounds.height == 768
            assert len(tree.children) == 2

            btn = tree.children[0]
            assert btn.role == "button"
            assert btn.name == "Back"
            assert btn.bounds.width == 50
            assert "click" in btn.actions

            edit = tree.children[1]
            assert edit.role == "edit"
            assert edit.name == "Search"
            assert edit.bounds.width == 300
            assert "type" in edit.actions


def test_macos_engine_synthetic_window_state_parsing() -> None:
    """Verify AppleScript window bounds and PID output parses into WindowStateModel."""
    synthetic_state = "12345###TextEdit - Document 1###true###100###200###800###600"

    with patch.object(MacOSUIAutomationEngine, "is_available", return_value=True):
        with patch.object(MacOSUIAutomationEngine, "run_applescript", return_value=synthetic_state):
            with patch.object(MacOSUIAutomationEngine, "_resolve_app_name", return_value="TextEdit"):
                state = MacOSUIAutomationEngine.device_read_window_state("TextEdit")

                assert isinstance(state, WindowStateModel)
                assert state.exists is True
                assert state.pid == 12345
                assert state.process_name == "TextEdit"
                assert state.title == "TextEdit - Document 1"
                assert state.bounds.left == 100
                assert state.bounds.top == 200
                assert state.bounds.width == 800
                assert state.bounds.height == 600


# -----------------------------------------------------------------------------
# 3. Linux UI Automation Engine Unit Contract & Parsing
# -----------------------------------------------------------------------------

def test_linux_engine_guard_and_role_normalization() -> None:
    """Verify Linux engine honors display/tool requirements and role mappings."""
    if sys.platform != "linux":
        assert LinuxUIAutomationEngine.is_available() is False
        with pytest.raises(RuntimeError) as exc_info:
            LinuxUIAutomationEngine.device_inspect_ui("terminal")
        assert "Linux UI Automation requires" in str(exc_info.value)

    # Test role normalizer
    assert LinuxUIAutomationEngine._normalize_atspi_role("push button") == "button"
    assert LinuxUIAutomationEngine._normalize_atspi_role("toggle button") == "button"
    assert LinuxUIAutomationEngine._normalize_atspi_role("entry") == "edit"
    assert LinuxUIAutomationEngine._normalize_atspi_role("text") == "edit"
    assert LinuxUIAutomationEngine._normalize_atspi_role("window") == "window"
    assert LinuxUIAutomationEngine._normalize_atspi_role("frame") == "window"
    assert LinuxUIAutomationEngine._normalize_atspi_role("menu bar") == "menu_bar"
    assert LinuxUIAutomationEngine._normalize_atspi_role("random") == "control"


def test_linux_engine_synthetic_wmctrl_parsing() -> None:
    """Verify wmctrl -l -p -G table parsing into WindowStateModel."""
    # Format: <xid> <desktop_num> <pid> <x> <y> <w> <h> <client> <title>
    sample_wmctrl = (
        "0x04000003  0 4567  150  250 1200  800  my-host Calculator - Simple\n"
        "0x04000004  0 8910   50   50  600  400  my-host Terminal\n"
    )

    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = sample_wmctrl

    with patch.object(LinuxUIAutomationEngine, "is_available", return_value=True):
        with patch("app.device.linux_automation.subprocess.run", return_value=mock_res):
            state = LinuxUIAutomationEngine.device_read_window_state("Calculator")

            assert isinstance(state, WindowStateModel)
            assert state.exists is True
            assert state.pid == 4567
            assert state.title == "Calculator - Simple"
            assert state.bounds.left == 150
            assert state.bounds.top == 250
            assert state.bounds.width == 1200
            assert state.bounds.height == 800


# -----------------------------------------------------------------------------
# 4. Real End-to-End Desktop Automation via DesktopAutomationEngine
# -----------------------------------------------------------------------------

def test_desktop_automation_notepad_e2e() -> None:
    """Execute real end-to-end desktop automation through unified DesktopAutomationEngine."""
    if sys.platform != "win32":
        pytest.skip("E2E desktop test requires Windows platform.")

    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    try:
        # Step 1: Read Window State via unified engine
        state = DesktopAutomationEngine.read_window_state("Notepad")
        assert state.exists is True
        assert "Notepad" in state.title
        assert state.bounds.width > 0
        assert state.bounds.height > 0

        # Step 2: Inspect UI Element Tree
        tree = DesktopAutomationEngine.inspect_ui("Notepad", max_depth=3)
        assert isinstance(tree, UIElementModel)
        assert tree.role == "window"
        assert len(tree.children) > 0

        # Step 3: Find Editor Element
        editor = DesktopAutomationEngine.find_element(
            window_target="Notepad",
            role="document",
        )
        assert editor is not None
        assert editor.role in ("document", "edit")

        # Step 4: Type text via unified engine
        sample_text = "Universal Desktop Automation Verified via Phase 5 Engine"
        type_res = DesktopAutomationEngine.type_text(
            window_target="Notepad",
            text=sample_text,
            clear_first=True,
        )
        assert type_res["typed"] is True
        assert type_res["text"] == sample_text

        # Step 5: Send Hotkey
        hotkey_res = DesktopAutomationEngine.send_hotkey("Notepad", "ctrl+a")
        assert hotkey_res["sent"] is True

        # Step 6: Take Screenshot
        shot = DesktopAutomationEngine.take_screenshot("Notepad")
        assert shot["success"] is True
        assert shot["width"] > 0
        assert shot["height"] > 0
        assert len(shot["base64_data"]) > 100

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except Exception:
            pass


def test_desktop_automation_cross_platform_override() -> None:
    """Verify platform_override routes to requested engine and handles platform mismatches."""
    # When overriding to an unavailable platform on host, it must honestly fail rather than simulate
    if sys.platform != "darwin":
        with pytest.raises(RuntimeError):
            DesktopAutomationEngine.inspect_ui(window_target="Finder", platform_override="macos")

    if sys.platform != "linux":
        with pytest.raises(RuntimeError):
            DesktopAutomationEngine.inspect_ui(window_target="XTerm", platform_override="linux")


def test_desktop_automation_honest_wait_timeout() -> None:
    """Verify wait_for_element times out honestly when element does not exist."""
    start_time = time.perf_counter()
    with pytest.raises((TimeoutError, LookupError)):
        DesktopAutomationEngine.wait_for_element(
            window_target="NonExistentWindow_Phase5_XYZ_9999",
            name="GhostButton",
            timeout_sec=0.5,
        )
    elapsed = time.perf_counter() - start_time
    # Should exit within ~1.5s
    assert elapsed < 3.0


# -----------------------------------------------------------------------------
# 5. Service & ToolRegistry Integration with DesktopAutomationEngine
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_device_service_desktop_automation(mock_user: User) -> None:
    """Verify DeviceService routes UI methods through DesktopAutomationEngine."""
    service = DeviceService()
    dev = await service.get_or_create_local_device(mock_user.id)

    # Read window state of active screen
    state = await service.get_ui_window_state(
        user_id=mock_user.id,
        device_id=dev["id"],
        window_target=None,
    )
    assert isinstance(state, dict)
    assert "exists" in state
    assert "bounds" in state

    # Capture desktop screenshot
    shot = await service.capture_ui_screenshot(
        user_id=mock_user.id,
        device_id=dev["id"],
        window_target=None,
    )
    assert isinstance(shot, dict)
    assert shot["success"] is True
    assert "base64_data" in shot


@pytest.mark.asyncio
async def test_tool_registry_ui_tools(mock_user: User) -> None:
    """Verify ToolRegistry executes device_inspect_ui and device_read_window_state tools."""
    service = DeviceService()
    registry = service._tool_registry

    # Tool 1: device_read_window_state
    req_state = ToolExecutionRequest(
        tool_id="device_read_window_state",
        arguments={"window_target": None, "user_id": mock_user.id},
        user_id=mock_user.id,
    )
    res_state = await registry.execute(req_state)
    assert res_state.status == ToolExecutionStatus.COMPLETED
    assert res_state.output is not None
    assert "exists" in res_state.output

    # Tool 2: device_take_screenshot
    req_shot = ToolExecutionRequest(
        tool_id="device_take_screenshot",
        arguments={"window_target": None, "user_id": mock_user.id},
        user_id=mock_user.id,
        bypass_confirmation=True,
    )
    res_shot = await registry.execute(req_shot)
    assert res_shot.status == ToolExecutionStatus.COMPLETED
    assert res_shot.output["success"] is True
    assert "base64_data" in res_shot.output




# -----------------------------------------------------------------------------
# 6. Daemon UI Command Execution via DesktopAutomationEngine
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daemon_ui_command_dispatch() -> None:
    """Verify RoxyDeviceDaemon executes ui_* commands using DesktopAutomationEngine."""
    daemon = RoxyDeviceDaemon(
        backend_url="http://127.0.0.1:8000",
        device_id="test_daemon_5555",
    )

    # Command 1: ui_window_state
    status, payload, err = await daemon.execute_command({
        "command_type": "ui_window_state",
        "payload": {"window_target": None},
    })
    assert status == "completed"
    assert payload is not None
    assert "exists" in payload
    assert err is None

    # Command 2: ui_screenshot
    status, payload, err = await daemon.execute_command({
        "command_type": "ui_screenshot",
        "payload": {"window_target": None},
    })
    assert status == "completed"
    assert payload is not None
    assert payload["success"] is True
    assert err is None

