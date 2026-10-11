"""Universal Cross-Platform Desktop Automation Engine for ROXY-AI.

Unifies Windows (Microsoft UI Automation / pywinauto), macOS (AppleScript / AXUIElement),
and Linux (AT-SPI / X11 / Wayland) behind a single authoritative desktop automation interface.

All platforms conform to the canonical UIElementModel and WindowStateModel specifications.
"""

from __future__ import annotations

import sys
from typing import Any, Literal, cast

import structlog

from app.device.linux_automation import LinuxUIAutomationEngine
from app.device.macos_automation import MacOSUIAutomationEngine
from app.device.windows_automation import (
    UIElementModel,
    WindowStateModel,
    WindowsUIAutomationEngine,
)

log = structlog.get_logger()


class DesktopAutomationEngine:
    """Universal cross-platform desktop automation coordinator."""

    @classmethod
    def get_active_platform(cls) -> str:
        """Return the normalized current operating system name."""
        if sys.platform == "win32":
            return "windows"
        elif sys.platform == "darwin":
            return "macos"
        elif sys.platform.startswith("linux"):
            return "linux"
        return sys.platform

    @classmethod
    def is_available(cls, platform_override: str | None = None) -> bool:
        """Check if desktop automation is available on current or specified platform."""
        try:
            adapter = cls.get_adapter(platform_override)
            return bool(getattr(adapter, "is_available", lambda: True)())
        except Exception:
            return False

    @classmethod
    def get_adapter(cls, platform_override: str | None = None) -> Any:
        """Select and return the appropriate OS-specific automation engine."""
        plat = (platform_override or cls.get_active_platform()).lower()

        if plat in ("windows", "win32"):
            return WindowsUIAutomationEngine
        elif plat in ("macos", "darwin", "osx"):
            return MacOSUIAutomationEngine
        elif plat in ("linux", "ubuntu", "debian"):
            return LinuxUIAutomationEngine
        else:
            raise NotImplementedError(f"Desktop UI automation is not supported on platform: '{plat}'.")

    # -------------------------------------------------------------------------
    # Unified Capability Dispatchers
    # -------------------------------------------------------------------------

    @classmethod
    def inspect_ui(
        cls,
        window_target: int | str | None = None,
        max_depth: int = 3,
        max_children: int = 50,
        platform_override: str | None = None,
    ) -> UIElementModel:
        """Deeply inspect the UI element hierarchy of the target window."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            UIElementModel,
            adapter.device_inspect_ui(
                window_target=window_target,
                max_depth=max_depth,
                max_children=max_children,
            ),
        )

    @classmethod
    def find_element(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        role: str | None = None,
        timeout_sec: float = 5.0,
        platform_override: str | None = None,
    ) -> UIElementModel:
        """Find a target UI element matching search criteria in the specified window."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            UIElementModel,
            adapter.device_find_element(
                window_target=window_target,
                name=name,
                automation_id=automation_id,
                control_type=control_type,
                role=role,
                timeout_sec=timeout_sec,
            ),
        )

    @classmethod
    def click_element(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        click_type: Literal["click", "right_click", "double_click"] = "click",
        platform_override: str | None = None,
    ) -> dict[str, Any]:
        """Click an element in the target window."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            dict[str, Any],
            adapter.device_click_element(
                window_target=window_target,
                name=name,
                automation_id=automation_id,
                control_type=control_type,
                click_type=click_type,
            ),
        )

    @classmethod
    def type_text(
        cls,
        window_target: int | str | None,
        text: str,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        clear_first: bool = False,
        press_enter: bool = False,
        platform_override: str | None = None,
    ) -> dict[str, Any]:
        """Type text into focused element or window."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            dict[str, Any],
            adapter.device_type_text(
                window_target=window_target,
                text=text,
                name=name,
                automation_id=automation_id,
                control_type=control_type,
                clear_first=clear_first,
                press_enter=press_enter,
            ),
        )

    @classmethod
    def send_hotkey(
        cls,
        window_target: int | str | None,
        hotkey: str,
        platform_override: str | None = None,
    ) -> dict[str, Any]:
        """Send keyboard shortcut combination to the target window."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            dict[str, Any],
            adapter.device_send_hotkey(
                window_target=window_target,
                hotkey=hotkey,
            ),
        )

    @classmethod
    def scroll(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        direction: Literal["up", "down", "left", "right"] = "down",
        amount: int = 1,
        platform_override: str | None = None,
    ) -> dict[str, Any]:
        """Scroll application window or scrollable control."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            dict[str, Any],
            adapter.device_scroll(
                window_target=window_target,
                name=name,
                automation_id=automation_id,
                direction=direction,
                amount=amount,
            ),
        )

    @classmethod
    def read_window_state(
        cls,
        window_target: int | str | None,
        platform_override: str | None = None,
    ) -> WindowStateModel:
        """Inspect and return runtime state of the specified window."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            WindowStateModel,
            adapter.device_read_window_state(window_target=window_target),
        )

    @classmethod
    def restore_window(
        cls,
        window_target: int | str | None,
        platform_override: str | None = None,
    ) -> dict[str, Any]:
        """Restore minimized window to normal/foreground state."""
        adapter = cls.get_adapter(platform_override)
        if hasattr(adapter, "device_restore_window"):
            return cast(dict[str, Any], adapter.device_restore_window(window_target=window_target))
        return {"restored": False, "target": window_target}

    device_restore_window = restore_window

    @classmethod
    def take_screenshot(
        cls,
        window_target: int | str | None = None,
        platform_override: str | None = None,
    ) -> dict[str, Any]:
        """Capture screenshot of the target window or entire desktop without external leakage."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            dict[str, Any],
            adapter.device_take_screenshot(window_target=window_target),
        )

    @classmethod
    def select_element(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        item_name: str | None = None,
        platform_override: str | None = None,
    ) -> dict[str, Any]:
        """Select an item in a list or tab container."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            dict[str, Any],
            adapter.device_select_element(
                window_target=window_target,
                name=name,
                automation_id=automation_id,
                item_name=item_name,
            ),
        )

    @classmethod
    def wait_for_element(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        role: str | None = None,
        timeout_sec: float = 10.0,
        platform_override: str | None = None,
    ) -> UIElementModel:
        """Poll the target application until matching element appears."""
        adapter = cls.get_adapter(platform_override)
        return cast(
            UIElementModel,
            adapter.device_wait_for_element(
                window_target=window_target,
                name=name,
                automation_id=automation_id,
                control_type=control_type,
                role=role,
                timeout_sec=timeout_sec,
            ),
        )

    # Backwards-compatible aliases matching platform-specific engine naming
    device_inspect_ui = inspect_ui
    device_find_element = find_element
    device_click_element = click_element
    device_type_text = type_text
    device_send_hotkey = send_hotkey
    device_scroll = scroll
    device_read_window_state = read_window_state
    device_take_screenshot = take_screenshot
    device_select_element = select_element
    device_wait_for_element = wait_for_element
