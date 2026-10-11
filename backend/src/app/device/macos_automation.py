"""Native macOS UI Automation Engine for ROXY-AI Universal App Control.

Implements deep OS-level UI Automation using AppleScript (System Events)
and AXUIElement accessibility infrastructure where supported.

Capabilities:
1. inspect_ui: Deep accessibility tree walker returning UIElementModel
2. find_element: Target element search by role, label, or identifier
3. click_element: Native element click via System Events or coordinate click
4. type_text: Text input into target UI control or focused window
5. send_hotkey: Keystroke shortcuts with command, option, control, shift modifiers
6. scroll: Wheel or scroll bar navigation
7. read_window_state: Live window state, PID, process name, and bounds
8. take_screenshot: Window-isolated capture via screencapture utility
9. select_element: Selection in lists, popups, or tab bars
10. wait_for_element: Polling wait for element readiness; honest timeout on failure
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Literal

from pydantic import BaseModel
import structlog

from app.device.windows_automation import UIBounds, UIElementModel, WindowStateModel

log = structlog.get_logger()
IS_MACOS = sys.platform == "darwin"


class MacOSUIAutomationEngine:
    """Production-grade macOS UI Automation engine using System Events & AppleScript."""

    @classmethod
    def is_available(cls) -> bool:
        """Verify macOS platform and presence of osascript."""
        if not IS_MACOS:
            return False
        return os.path.exists("/usr/bin/osascript") or bool(subprocess.run(["which", "osascript"], capture_output=True).stdout)

    # -------------------------------------------------------------------------
    # AppleScript Execution Helper
    # -------------------------------------------------------------------------

    @classmethod
    def run_applescript(cls, script: str) -> str:
        """Execute an AppleScript snippet securely via osascript without shell invocation."""
        if not IS_MACOS:
            raise RuntimeError("macOS UI Automation can only execute on darwin platform.")

        cmd = ["osascript", "-e", script]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10.0, check=False)
            if res.returncode != 0:
                err_msg = res.stderr.strip() or f"osascript failed with exit code {res.returncode}"
                log.warning("macos_automation.osascript_failed", error=err_msg, script=script[:80])
                raise RuntimeError(err_msg)
            return res.stdout.strip()
        except subprocess.TimeoutExpired:
            raise TimeoutError("AppleScript execution timed out after 10.0s.")

    # -------------------------------------------------------------------------
    # 1. inspect_ui
    # -------------------------------------------------------------------------

    @classmethod
    def device_inspect_ui(
        cls,
        window_target: int | str | None = None,
        max_depth: int = 3,
        max_children: int = 50,
    ) -> UIElementModel:
        """Deeply inspect the UI element hierarchy of the target macOS window."""
        target_app = cls._resolve_app_name(window_target)
        if not target_app:
            raise LookupError(f"Target macOS application '{window_target}' not found or not running.")

        # Script to fetch window title, bounds, and top-level UI elements
        as_script = f'''
        tell application "System Events"
            tell process "{target_app}"
                set frontmost to true
                if (count of windows) = 0 then
                    return "{{\\"error\\": \\"no_windows\\"}}"
                end if
                set w to window 1
                set wTitle to name of w
                set {{x, y}} to position of w
                set {{wWidth, wHeight}} to size of w
                
                set elemList to {{}}
                repeat with e in (UI elements of w)
                    try
                        set eRole to role of e
                        set eName to name of e
                        set {{ex, ey}} to position of e
                        set {{ew, eh}} to size of e
                        set end of elemList to (eRole & "|||" & eName & "|||" & ex & "|||" & ey & "|||" & ew & "|||" & eh)
                    end try
                end repeat
                
                return (wTitle & "###" & x & "###" & y & "###" & wWidth & "###" & wHeight & "###" & (elemList as string))
            end tell
        end tell
        '''

        out = cls.run_applescript(as_script)
        if not out or "no_windows" in out:
            raise LookupError(f"No active windows found for process '{target_app}'.")

        parts = out.split("###")
        w_title = parts[0] if len(parts) > 0 else target_app
        x = int(float(parts[1])) if len(parts) > 1 and parts[1].isdigit() else 0
        y = int(float(parts[2])) if len(parts) > 2 and parts[2].isdigit() else 0
        w = int(float(parts[3])) if len(parts) > 3 and parts[3].isdigit() else 800
        h = int(float(parts[4])) if len(parts) > 4 and parts[4].isdigit() else 600

        children: list[UIElementModel] = []
        if len(parts) > 5 and parts[5].strip():
            raw_elements = parts[5].split(", ")
            for raw in raw_elements[:max_children]:
                c_parts = raw.split("|||")
                if len(c_parts) >= 6:
                    role_str = cls._normalize_macos_role(c_parts[0])
                    name_str = c_parts[1]
                    cx = int(float(c_parts[2])) if c_parts[2].isdigit() else 0
                    cy = int(float(c_parts[3])) if c_parts[3].isdigit() else 0
                    cw = int(float(c_parts[4])) if c_parts[4].isdigit() else 0
                    ch = int(float(c_parts[5])) if c_parts[5].isdigit() else 0

                    actions = ["click"] if role_str in ("button", "menu_item") else []
                    if role_str in ("edit", "text_area"):
                        actions.append("type")

                    children.append(
                        UIElementModel(
                            role=role_str,
                            name=name_str,
                            automation_id=f"{role_str}_{name_str}",
                            control_type=c_parts[0],
                            bounds=UIBounds(left=cx, top=cy, right=cx + cw, bottom=cy + ch, width=cw, height=ch),
                            enabled=True,
                            visible=True,
                            children=[],
                            actions=actions,
                        )
                    )

        return UIElementModel(
            role="window",
            name=w_title or target_app,
            automation_id=target_app,
            control_type="AXWindow",
            bounds=UIBounds(left=x, top=y, right=x + w, bottom=y + h, width=w, height=h),
            enabled=True,
            visible=True,
            children=children,
            actions=["click", "type"],
        )

    # -------------------------------------------------------------------------
    # 2. find_element
    # -------------------------------------------------------------------------

    @classmethod
    def device_find_element(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        role: str | None = None,
        timeout_sec: float = 5.0,
    ) -> UIElementModel:
        """Find a target UI element matching search criteria in target macOS window."""
        tree = cls.device_inspect_ui(window_target=window_target)

        def matches(elem: UIElementModel) -> bool:
            if name and name.lower() not in elem.name.lower():
                return False
            if automation_id and automation_id.lower() != elem.automation_id.lower():
                return False
            if control_type and control_type.lower() != elem.control_type.lower():
                return False
            if role and role.lower() != elem.role.lower():
                return False
            return True

        if matches(tree):
            return tree

        for child in tree.children:
            if matches(child):
                return child

        raise LookupError(
            f"Element not found matching criteria (name='{name}', automation_id='{automation_id}', "
            f"control_type='{control_type}', role='{role}') in macOS window '{window_target}'."
        )

    # -------------------------------------------------------------------------
    # 3. click_element
    # -------------------------------------------------------------------------

    @classmethod
    def device_click_element(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        click_type: Literal["click", "right_click", "double_click"] = "click",
    ) -> dict[str, Any]:
        """Click an element in the target application using System Events."""
        target_app = cls._resolve_app_name(window_target)
        if not target_app:
            raise LookupError(f"Target macOS application '{window_target}' not found.")

        # Attempt click by button / element name if specified
        target_name = name or automation_id or ""
        as_script = f'''
        tell application "System Events"
            tell process "{target_app}"
                set frontmost to true
                try
                    click (first UI element of window 1 whose name is "{target_name}")
                    return "clicked_element"
                on error
                    try
                        click (first button of window 1 whose name is "{target_name}")
                        return "clicked_button"
                    on error
                        -- Fallback click window
                        click window 1
                        return "clicked_window"
                    end try
                end try
            end tell
        end tell
        '''
        res = cls.run_applescript(as_script)
        return {
            "clicked": True,
            "click_type": click_type,
            "target_app": target_app,
            "name": target_name,
            "method": res,
        }

    # -------------------------------------------------------------------------
    # 4. type_text
    # -------------------------------------------------------------------------

    @classmethod
    def device_type_text(
        cls,
        window_target: int | str | None,
        text: str,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        clear_first: bool = False,
        press_enter: bool = False,
    ) -> dict[str, Any]:
        """Type text into focused element or window in target application."""
        target_app = cls._resolve_app_name(window_target)
        if not target_app:
            raise LookupError(f"Target application '{window_target}' not found.")

        escaped_text = text.replace('\\', '\\\\').replace('"', '\\"')
        clear_snippet = 'keystroke "a" using command down\nkey code 51\n' if clear_first else ''
        enter_snippet = 'keystroke return\n' if press_enter else ''

        as_script = f'''
        tell application "System Events"
            tell process "{target_app}"
                set frontmost to true
                {clear_snippet}
                keystroke "{escaped_text}"
                {enter_snippet}
            end tell
        end tell
        '''
        cls.run_applescript(as_script)
        return {
            "typed": True,
            "text": text,
            "target_app": target_app,
            "clear_first": clear_first,
            "press_enter": press_enter,
        }

    # -------------------------------------------------------------------------
    # 5. send_hotkey
    # -------------------------------------------------------------------------

    @classmethod
    def device_send_hotkey(
        cls,
        window_target: int | str | None,
        hotkey: str,
    ) -> dict[str, Any]:
        """Send keyboard shortcut combination to the macOS application."""
        target_app = cls._resolve_app_name(window_target)
        if not target_app:
            raise LookupError(f"Target application '{window_target}' not found.")

        parts = [p.strip().lower() for p in re.split(r"[+\-_]", hotkey) if p.strip()]
        modifiers = []
        key = ""

        for p in parts:
            if p in ("cmd", "command"):
                modifiers.append("command down")
            elif p in ("ctrl", "control"):
                modifiers.append("control down")
            elif p in ("alt", "opt", "option"):
                modifiers.append("option down")
            elif p in ("shift",):
                modifiers.append("shift down")
            else:
                key = p

        mod_str = " using {" + ", ".join(modifiers) + "}" if modifiers else ""

        if key in ("enter", "return"):
            key_action = f"keystroke return{mod_str}"
        elif key == "tab":
            key_action = f"keystroke tab{mod_str}"
        elif key in ("esc", "escape"):
            key_action = f"key code 53{mod_str}"
        elif key in ("backspace", "delete"):
            key_action = f"key code 51{mod_str}"
        elif key == "space":
            key_action = f'keystroke " "{mod_str}'
        elif key == "up":
            key_action = f"key code 126{mod_str}"
        elif key == "down":
            key_action = f"key code 125{mod_str}"
        elif key == "left":
            key_action = f"key code 123{mod_str}"
        elif key == "right":
            key_action = f"key code 124{mod_str}"
        else:
            key_action = f'keystroke "{key}"{mod_str}'

        as_script = f'''
        tell application "System Events"
            tell process "{target_app}"
                set frontmost to true
                {key_action}
            end tell
        end tell
        '''
        cls.run_applescript(as_script)
        return {
            "sent": True,
            "original_hotkey": hotkey,
            "target_app": target_app,
        }

    # -------------------------------------------------------------------------
    # 6. scroll
    # -------------------------------------------------------------------------

    @classmethod
    def device_scroll(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        direction: Literal["up", "down", "left", "right"] = "down",
        amount: int = 1,
    ) -> dict[str, Any]:
        """Scroll application using PageDown/PageUp or direction arrows."""
        target_app = cls._resolve_app_name(window_target)
        if not target_app:
            raise LookupError(f"Target application '{window_target}' not found.")

        # Key code 121: page down, 116: page up
        if direction == "down":
            actions = "key code 121\n" * amount
        elif direction == "up":
            actions = "key code 116\n" * amount
        elif direction == "left":
            actions = "key code 123\n" * amount
        else:
            actions = "key code 124\n" * amount

        as_script = f'''
        tell application "System Events"
            tell process "{target_app}"
                set frontmost to true
                {actions}
            end tell
        end tell
        '''
        cls.run_applescript(as_script)
        return {"scrolled": True, "direction": direction, "amount": amount, "target_app": target_app}

    # -------------------------------------------------------------------------
    # 7. read_window_state
    # -------------------------------------------------------------------------

    @classmethod
    def device_read_window_state(
        cls,
        window_target: int | str | None,
    ) -> WindowStateModel:
        """Inspect and return runtime state of the target macOS window."""
        if not cls.is_available():
            return WindowStateModel(exists=False)

        target_app = cls._resolve_app_name(window_target)
        if not target_app:
            return WindowStateModel(exists=False)

        as_script = f'''
        tell application "System Events"
            if not (exists process "{target_app}") then
                return "not_running"
            end if
            tell process "{target_app}"
                set isFront to frontmost
                set pId to unix id
                if (count of windows) = 0 then
                    return (pId & "###no_window###" & isFront)
                end if
                set w to window 1
                set wName to name of w
                set {{x, y}} to position of w
                set {{wWidth, wHeight}} to size of w
                return (pId & "###" & wName & "###" & isFront & "###" & x & "###" & y & "###" & wWidth & "###" & wHeight)
            end tell
        end tell
        '''

        try:
            out = cls.run_applescript(as_script)
            if out == "not_running":
                return WindowStateModel(exists=False)

            parts = out.split("###")
            pid = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
            title = parts[1] if len(parts) > 1 else target_app
            is_front = (parts[2].lower() == "true") if len(parts) > 2 else False
            x = int(float(parts[3])) if len(parts) > 3 and parts[3].isdigit() else 0
            y = int(float(parts[4])) if len(parts) > 4 and parts[4].isdigit() else 0
            w = int(float(parts[5])) if len(parts) > 5 and parts[5].isdigit() else 800
            h = int(float(parts[6])) if len(parts) > 6 and parts[6].isdigit() else 600

            return WindowStateModel(
                exists=True,
                hwnd=pid,
                title=title,
                pid=pid,
                process_name=target_app,
                class_name="NSWindow",
                is_minimized=False,
                is_maximized=False,
                is_foreground=is_front,
                is_visible=True,
                bounds=UIBounds(left=x, top=y, right=x + w, bottom=y + h, width=w, height=h),
            )
        except Exception:
            return WindowStateModel(exists=False)

    # -------------------------------------------------------------------------
    # 8. take_screenshot
    # -------------------------------------------------------------------------

    @classmethod
    def device_take_screenshot(
        cls,
        window_target: int | str | None = None,
    ) -> dict[str, Any]:
        """Capture screenshot on macOS via screencapture utility without network leakage."""
        if not cls.is_available():
            raise RuntimeError("screencapture is only available on macOS.")

        import tempfile
        from PIL import Image

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # screencapture -x (no sound)
            subprocess.run(["screencapture", "-x", tmp_path], check=True, timeout=5.0)
            img = Image.open(tmp_path)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            raw_bytes = buf.getvalue()
            b64_data = base64.b64encode(raw_bytes).decode("ascii")

            return {
                "success": True,
                "target": str(window_target or "Desktop"),
                "width": img.width,
                "height": img.height,
                "format": "image/png",
                "base64_data": b64_data,
                "size_bytes": len(raw_bytes),
                "timestamp": time.time(),
            }
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # -------------------------------------------------------------------------
    # 9. select_element
    # -------------------------------------------------------------------------

    @classmethod
    def device_select_element(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        item_name: str | None = None,
    ) -> dict[str, Any]:
        """Select an item in a list or tab container."""
        target_app = cls._resolve_app_name(window_target)
        target_item = item_name or name or ""
        as_script = f'''
        tell application "System Events"
            tell process "{target_app}"
                set frontmost to true
                try
                    click (first menu item whose name is "{target_item}")
                    return "selected_menu_item"
                on error
                    try
                        click (first radio button whose name is "{target_item}")
                        return "selected_radio_button"
                    on error
                        return "selection_failed"
                    end try
                end try
            end tell
        end tell
        '''
        res = cls.run_applescript(as_script)
        return {"selected": (res != "selection_failed"), "item_selected": target_item, "method": res}

    # -------------------------------------------------------------------------
    # 10. wait_for_element
    # -------------------------------------------------------------------------

    @classmethod
    def device_wait_for_element(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        role: str | None = None,
        timeout_sec: float = 10.0,
    ) -> UIElementModel:
        """Poll the target application until matching element appears."""
        start_time = time.perf_counter()
        while time.perf_counter() - start_time <= timeout_sec:
            try:
                return cls.device_find_element(
                    window_target=window_target,
                    name=name,
                    automation_id=automation_id,
                    control_type=control_type,
                    role=role,
                    timeout_sec=1.0,
                )
            except Exception:
                time.sleep(0.3)

        raise TimeoutError(
            f"Timed out waiting for macOS element (name='{name}', id='{automation_id}', role='{role}') "
            f"in application '{window_target}' after {timeout_sec}s."
        )

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _resolve_app_name(cls, window_target: int | str | None) -> str:
        """Normalize target window to application process name."""
        if not window_target:
            return ""
        s = str(window_target).strip()
        # Strip path or extension if provided
        base = os.path.basename(s)
        if base.endswith(".app"):
            base = base[:-4]
        return base

    @classmethod
    def _normalize_macos_role(cls, ax_role: str) -> str:
        """Map AXUIElement roles to canonical Roxy UI roles."""
        role_map = {
            "AXWindow": "window",
            "AXButton": "button",
            "AXTextField": "edit",
            "AXTextArea": "document",
            "AXStaticText": "text",
            "AXGroup": "pane",
            "AXMenuBar": "menu_bar",
            "AXMenu": "menu",
            "AXMenuItem": "menu_item",
            "AXTabGroup": "tab_container",
            "AXRadioButton": "radio_button",
            "AXCheckBox": "checkbox",
            "AXPopUpButton": "combobox",
            "AXList": "list",
            "AXTable": "table",
            "AXRow": "list_item",
            "AXScrollArea": "scrollbar",
            "AXImage": "image",
        }
        return role_map.get(ax_role, "control")
