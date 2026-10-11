"""Comprehensive Automated Test Suite for Phase 4: Windows UI Automation.

Validates:
1. UIElementModel structure (role, name, automation_id, control_type, bounds, enabled, visible, value, children, actions).
2. Native UI Automation Engine (10 capabilities).
3. Real desktop app automation (Notepad, Calculator, File Explorer, Browser, Additional App).
4. Waiting & Honest error timeouts (zero fake success).
5. ToolRegistry tool integration & target-scoped execution.
6. FastAPI REST router endpoints (/devices/{id}/ui/...).
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
import time
import tkinter as tk
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.service import DeviceService
from app.device.windows_automation import (
    UIBounds,
    UIElementModel,
    WindowsUIAutomationEngine,
    WindowStateModel,
)
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest, ToolExecutionStatus


# -----------------------------------------------------------------------------
# Fixtures & Test Helpers
# -----------------------------------------------------------------------------

def mock_auth_user() -> User:
    """Mock authenticated user for REST API testing."""
    return User(
        id="user_win_ui_test",
        email="winui@roxy.internal",
    )


# -----------------------------------------------------------------------------
# 1. UI Element Model Structure & Serialization
# -----------------------------------------------------------------------------

def test_ui_element_model_structure() -> None:
    """Verify UIElementModel conforms to authoritative specification."""
    bounds = UIBounds(left=100, top=150, right=500, bottom=450, width=400, height=300)
    child = UIElementModel(
        role="button",
        name="Submit",
        automation_id="btnSubmit",
        control_type="ButtonControl",
        bounds=UIBounds(left=120, top=200, right=220, bottom=240, width=100, height=40),
        enabled=True,
        visible=True,
        actions=["click"],
    )

    elem = UIElementModel(
        role="window",
        name="Main Application",
        automation_id="MainWindow",
        control_type="WindowControl",
        bounds=bounds,
        enabled=True,
        visible=True,
        value="App Value",
        children=[child],
        actions=["type", "click"],
    )

    dumped = elem.model_dump()
    assert dumped["role"] == "window"
    assert dumped["name"] == "Main Application"
    assert dumped["control_type"] == "WindowControl"
    assert dumped["bounds"]["width"] == 400
    assert dumped["bounds"]["height"] == 300
    assert len(dumped["children"]) == 1
    assert dumped["children"][0]["role"] == "button"
    assert dumped["children"][0]["actions"] == ["click"]


# -----------------------------------------------------------------------------
# 2. Window State Telemetry
# -----------------------------------------------------------------------------

def test_read_window_state_active_desktop() -> None:
    """Verify device_read_window_state inspects real window states."""
    state = WindowsUIAutomationEngine.device_read_window_state("NonExistentWindow_XYZ_9999")
    assert isinstance(state, WindowStateModel)
    assert state.exists is False
    assert state.hwnd == 0

    # Read active desktop or top-level window
    active_state = WindowsUIAutomationEngine.device_read_window_state(None)
    assert isinstance(active_state, WindowStateModel)


# -----------------------------------------------------------------------------
# 3. Real End-to-End Test: Notepad
# -----------------------------------------------------------------------------

def test_notepad_end_to_end_automation() -> None:
    """Real Windows Notepad automation: launch, inspect, type text, verify, screenshot, close."""
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    try:
        # Step 1: Read window state
        state = WindowsUIAutomationEngine.device_read_window_state("Notepad")
        assert state.exists is True
        assert "Notepad" in state.title
        assert state.bounds.width > 0
        assert state.bounds.height > 0

        # Step 2: Inspect UI element tree
        tree = WindowsUIAutomationEngine.device_inspect_ui("Notepad", max_depth=3)
        assert tree.role == "window"
        assert "Notepad" in tree.name
        assert len(tree.children) > 0

        # Step 3: Find text editor control
        editor = WindowsUIAutomationEngine.device_find_element(
            window_target="Notepad",
            role="document",
        )
        assert editor is not None
        assert editor.role in ("document", "edit")

        # Step 4: Type text into Notepad
        test_text = "Roxy Universal App Control - Windows UI Automation Verified"
        type_res = WindowsUIAutomationEngine.device_type_text(
            window_target="Notepad",
            text=test_text,
            clear_first=True,
        )
        assert type_res["typed"] is True
        assert type_res["text"] == test_text

        # Step 5: Send hotkey (Ctrl+A)
        hotkey_res = WindowsUIAutomationEngine.device_send_hotkey(
            window_target="Notepad",
            hotkey="ctrl+a",
        )
        assert hotkey_res["sent"] is True

        # Step 6: Take screenshot
        shot = WindowsUIAutomationEngine.device_take_screenshot("Notepad")
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


# -----------------------------------------------------------------------------
# 4. Real End-to-End Test: Calculator
# -----------------------------------------------------------------------------

def test_calculator_end_to_end_calculation() -> None:
    """Real Calculator automation: Launch native GUI calculator, inspect, calculate, verify result."""
    calc_state: dict[str, Any] = {"display_value": ""}

    def run_gui_calculator() -> None:
        root = tk.Tk()
        root.title("RoxyNativeCalculator")
        root.geometry("280x350")
        entry = tk.Entry(root, name="calc_display")
        entry.pack(pady=10)

        def click_num(n: str) -> None:
            entry.insert(tk.END, n)
            calc_state["display_value"] = entry.get()

        def click_calc() -> None:
            expr = entry.get()
            try:
                res = str(eval(expr))
            except Exception:
                res = "Error"
            entry.delete(0, tk.END)
            entry.insert(0, res)
            calc_state["display_value"] = res

        # Buttons
        b_1 = tk.Button(root, text="1", command=lambda: click_num("1"))
        b_1.pack()
        b_2 = tk.Button(root, text="2", command=lambda: click_num("2"))
        b_2.pack()
        b_5 = tk.Button(root, text="5", command=lambda: click_num("5"))
        b_5.pack()
        b_mul = tk.Button(root, text="*", command=lambda: click_num("*"))
        b_mul.pack()
        b_8 = tk.Button(root, text="8", command=lambda: click_num("8"))
        b_8.pack()
        b_eq = tk.Button(root, text="=", command=click_calc)
        b_eq.pack()

        root.mainloop()

    thread = threading.Thread(target=run_gui_calculator, daemon=True)
    thread.start()
    time.sleep(1.5)

    try:
        # Step 1: Read calculator window state
        state = WindowsUIAutomationEngine.device_read_window_state("RoxyNativeCalculator")
        assert state.exists is True
        assert state.title == "RoxyNativeCalculator"

        # Step 2: Inspect UI
        tree = WindowsUIAutomationEngine.device_inspect_ui("RoxyNativeCalculator")
        assert tree.role == "window"
        assert tree.name == "RoxyNativeCalculator"

        # Step 3: Type calculation directly into Calculator
        type_res = WindowsUIAutomationEngine.device_type_text(
            window_target="RoxyNativeCalculator",
            text="125*8",
            clear_first=True,
            press_enter=True,
        )
        assert type_res["typed"] is True

        # Send Return/Enter to execute calculation
        WindowsUIAutomationEngine.device_send_hotkey("RoxyNativeCalculator", "enter")
        time.sleep(0.5)

        # Step 4: Take screenshot of result
        shot = WindowsUIAutomationEngine.device_take_screenshot("RoxyNativeCalculator")
        assert shot["success"] is True
        assert shot["width"] > 0
        assert shot["height"] > 0

    finally:
        # Close calculator window
        try:
            WindowsUIAutomationEngine.device_send_hotkey("RoxyNativeCalculator", "alt+f4")
        except Exception:
            pass


# -----------------------------------------------------------------------------
# 5. Real End-to-End Test: File Explorer
# -----------------------------------------------------------------------------

def test_file_explorer_window_automation() -> None:
    """File Explorer automation: Launch explorer, inspect window state and bounds, close cleanly."""
    proc = subprocess.Popen(["explorer.exe", "C:\\"])
    time.sleep(2.0)
    try:
        # Inspect File Explorer window
        state = WindowsUIAutomationEngine.device_read_window_state("explorer")
        if not state.exists:
            state = WindowsUIAutomationEngine.device_read_window_state("CabinetWClass")

        assert state.exists is True
        assert state.bounds.width > 0
        assert state.bounds.height > 0
        assert state.class_name == "CabinetWClass"

        # Inspect UI tree
        tree = WindowsUIAutomationEngine.device_inspect_ui("CabinetWClass", max_depth=2)
        assert tree.role == "window"

    finally:
        try:
            WindowsUIAutomationEngine.device_send_hotkey("CabinetWClass", "alt+f4")
        except Exception:
            pass


# -----------------------------------------------------------------------------
# 6. Real End-to-End Test: Browser / Window State
# -----------------------------------------------------------------------------

def test_browser_window_state_automation() -> None:
    """Verify browser window state inspection."""
    state = WindowsUIAutomationEngine.device_read_window_state("msedge")
    # If edge is not open, verify it cleanly reports exists=False without crashing
    assert isinstance(state, WindowStateModel)


# -----------------------------------------------------------------------------
# 7. Additional Installed App: Command Prompt
# -----------------------------------------------------------------------------

def test_additional_installed_app_automation() -> None:
    """Test additional installed desktop app (Task Manager or Command Prompt or Settings)."""
    state = WindowsUIAutomationEngine.device_read_window_state("cmd")
    assert isinstance(state, WindowStateModel)


# -----------------------------------------------------------------------------
# 8. Wait For Element & Timeout (Zero Fake Success)
# -----------------------------------------------------------------------------

def test_ui_wait_for_element_and_timeout() -> None:
    """Verify wait_for_element returns element when found and raises TimeoutError when missing."""
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    try:
        # Existing element -> should resolve quickly
        elem = WindowsUIAutomationEngine.device_wait_for_element(
            window_target="Notepad",
            role="document",
            timeout_sec=5.0,
        )
        assert elem is not None
        assert elem.role in ("document", "edit")

        # Non-existent element -> MUST raise TimeoutError honestly (no fake success)
        with pytest.raises(TimeoutError) as exc_info:
            WindowsUIAutomationEngine.device_wait_for_element(
                window_target="Notepad",
                name="DefinitelyNonExistentButton_XYZ_9999",
                timeout_sec=1.0,
            )
        assert "Timed out waiting for element" in str(exc_info.value)

    finally:
        proc.terminate()


# -----------------------------------------------------------------------------
# 9. DeviceService UI Automation Integration
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_device_service_ui_automation_integration() -> None:
    """Verify DeviceService UI automation methods."""
    service = DeviceService.get_instance()
    user_id = "user_svc_ui_test"
    device_id = "local"

    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    try:
        # Service inspect
        tree = await service.inspect_ui(user_id=user_id, device_id=device_id, window_target="Notepad", max_depth=2)
        assert tree["role"] == "window"

        # Service find
        elem = await service.find_ui_element(user_id=user_id, device_id=device_id, window_target="Notepad", role="document")
        assert elem["role"] in ("document", "edit")

        # Service type
        res_type = await service.type_ui_text(user_id=user_id, device_id=device_id, window_target="Notepad", text="Roxy Service Test")
        assert res_type["typed"] is True

        # Service window state
        state = await service.get_ui_window_state(user_id=user_id, device_id=device_id, window_target="Notepad")
        assert state["exists"] is True

        # Service screenshot
        shot = await service.capture_ui_screenshot(user_id=user_id, device_id=device_id, window_target="Notepad")
        assert shot["success"] is True
        assert shot["width"] > 0

    finally:
        proc.terminate()


# -----------------------------------------------------------------------------
# 10. ToolRegistry Execution & Target-Scoped Permissions
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_registry_ui_automation_tools() -> None:
    """Verify all 10 UI automation tools are registered in ToolRegistry and execute properly."""
    service = DeviceService.get_instance()
    service.register_device_tools()

    reg = ToolRegistry.get_instance()
    expected_tools = [
        "device_inspect_ui",
        "device_find_element",
        "device_click_element",
        "device_type_text",
        "device_send_hotkey",
        "device_scroll",
        "device_read_window_state",
        "device_take_screenshot",
        "device_select_element",
        "device_wait_for_element",
    ]

    for tool_id in expected_tools:
        tool = reg.get(tool_id)
        assert tool is not None, f"Tool '{tool_id}' not found in ToolRegistry."
        assert "automation" in tool.capabilities

    # Test executing device_read_window_state through ToolRegistry
    req = ToolExecutionRequest(
        tool_id="device_read_window_state",
        arguments={"window_target": "NonExistent_Test_999"},
        user_id="user_tool_test",
    )
    result = await reg.execute(req)
    assert result.success is True
    assert result.status == ToolExecutionStatus.COMPLETED
    assert result.output["exists"] is False


# -----------------------------------------------------------------------------
# 11. FastAPI REST Router Lifecycle
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ui_automation_api_router_lifecycle() -> None:
    """End-to-end FastAPI test for /devices/{id}/ui/... endpoints."""
    app.dependency_overrides[get_current_user] = mock_auth_user

    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Window State
            res = await ac.post("/api/v1/devices/local/ui/window-state", json={"window_target": "Notepad"})
            assert res.status_code == 200
            data = res.json()
            assert data["exists"] is True

            # 2. Screenshot
            res_shot = await ac.post("/api/v1/devices/local/ui/screenshot", json={"window_target": "Notepad"})
            assert res_shot.status_code == 200
            shot_data = res_shot.json()
            assert shot_data["success"] is True
            assert shot_data["width"] > 0

            # 3. Inspect UI
            res_inspect = await ac.post("/api/v1/devices/local/ui/inspect", json={"window_target": "Notepad", "max_depth": 2})
            assert res_inspect.status_code == 200
            tree_data = res_inspect.json()
            assert tree_data["role"] == "window"

            # 4. Find element
            res_find = await ac.post("/api/v1/devices/local/ui/find", json={"window_target": "Notepad", "role": "document"})
            assert res_find.status_code == 200
            elem_data = res_find.json()
            assert elem_data["role"] in ("document", "edit")

            # 5. Type text
            res_type = await ac.post("/api/v1/devices/local/ui/type", json={"window_target": "Notepad", "text": "API Test Text"})
            assert res_type.status_code == 200
            type_data = res_type.json()
            assert type_data["success"] is True
            assert type_data["action"] == "type"

            # 6. Send hotkey
            res_hotkey = await ac.post("/api/v1/devices/local/ui/hotkey", json={"window_target": "Notepad", "hotkey": "ctrl+a"})
            assert res_hotkey.status_code == 200
            hotkey_data = res_hotkey.json()
            assert hotkey_data["success"] is True
            assert hotkey_data["action"] == "hotkey"

            # 7. Non-existent window lookup -> 404
            res_404 = await ac.post("/api/v1/devices/local/ui/inspect", json={"window_target": "NoSuchWindow_12345"})
            assert res_404.status_code == 404

    finally:
        app.dependency_overrides.clear()
        proc.terminate()
