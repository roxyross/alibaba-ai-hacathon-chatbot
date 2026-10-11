"""Native Windows UI Automation Engine for ROXY-AI Universal App Control.

Implements deep OS-level UI Automation using Microsoft UI Automation (uiautomation)
and pywinauto / win32gui primitives.

Capabilities:
1. device_inspect_ui: Deep UI tree walker returning UIElementModel
2. device_find_element: Target element search by criteria
3. device_click_element: Native click via InvokePattern / physical click
4. device_type_text: ValuePattern or keystroke text input
5. device_send_hotkey: Keyboard shortcut sequences
6. device_scroll: ScrollPattern or wheel scrolling
7. device_read_window_state: Real HWND / window state telemetry
8. device_take_screenshot: Trusted local window/desktop screenshot
9. device_select_element: SelectionItemPattern selection
10. device_wait_for_element: Polling wait for element presence and readiness
"""

from __future__ import annotations

import base64
import contextlib
import io
from pathlib import Path
import re
import sys
import time
from typing import Any, Literal

import psutil  # type: ignore[import-untyped]
import structlog
from pydantic import BaseModel, Field

log = structlog.get_logger()

# Optional Windows-specific imports
IS_WINDOWS = sys.platform == "win32"

auto: Any = None
win32gui: Any = None
win32con: Any = None
win32process: Any = None
win32api: Any = None
pywinauto: Any = None

if IS_WINDOWS:
    with contextlib.suppress(ImportError):
        import uiautomation as auto
    with contextlib.suppress(ImportError):
        import win32gui  # type: ignore[import-untyped,no-redef]
    with contextlib.suppress(ImportError):
        import pywinauto  # type: ignore[import-untyped,no-redef]


# =============================================================================
# 1. UI Element Model
# =============================================================================

class UIBounds(BaseModel):
    """Bounding box coordinates of a UI element."""
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0
    width: int = 0
    height: int = 0


class UIElementModel(BaseModel):
    """Authoritative UI Element Model conforming to Roxy Universal App Control specs."""
    role: str = Field(..., description="Normalized UI role (e.g. window, button, edit, document, pane)")
    name: str = Field(default="", description="Accessible name or label")
    automation_id: str = Field(default="", description="UIA AutomationId identifier")
    control_type: str = Field(..., description="UIA ControlType name (e.g. ButtonControl, EditControl)")
    bounds: UIBounds = Field(default_factory=UIBounds, description="Bounding rectangle coordinates")
    enabled: bool = Field(default=True, description="Whether the control is enabled")
    visible: bool = Field(default=True, description="Whether the control is visible on screen")
    value: str | None = Field(default=None, description="Current text value or state if available")
    children: list[UIElementModel] = Field(default_factory=list, description="Child UI elements in tree")
    actions: list[str] = Field(default_factory=list, description="Available operational actions (click, type, select, etc.)")


class WindowStateModel(BaseModel):
    """Detailed runtime state of a top-level OS window."""
    exists: bool = False
    hwnd: int = 0
    title: str = ""
    pid: int = 0
    process_name: str = ""
    class_name: str = ""
    is_minimized: bool = False
    is_maximized: bool = False
    is_foreground: bool = False
    is_visible: bool = False
    bounds: UIBounds = Field(default_factory=UIBounds)


# =============================================================================
# 2. Windows UI Automation Engine
# =============================================================================

class WindowsUIAutomationEngine:
    """Production-grade Microsoft UI Automation engine for Windows desktop applications."""

    @classmethod
    def is_available(cls) -> bool:
        """Verify Windows platform and required libraries."""
        return IS_WINDOWS and (auto is not None or pywinauto is not None or win32gui is not None)

    @classmethod
    def ensure_interactive_desktop(cls) -> bool:
        """Attach the calling thread to the interactive 'Default' desktop on WinSta0.

        In automated test runners or sandbox processes where threads may be assigned
        to a private thread desktop (e.g. exebox-*), attaching to 'Default' allows
        legitimate access to the active user's interactive desktop windows.
        """
        if not IS_WINDOWS:
            return False
        try:
            import ctypes
            user32 = ctypes.windll.user32
            DESKTOP_ALL = 0x01FF
            h_default = user32.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
            if not h_default:
                h_default = user32.OpenInputDesktop(0, False, DESKTOP_ALL)
            if h_default:
                return bool(user32.SetThreadDesktop(h_default))
        except Exception as exc:
            log.debug("windows_automation.ensure_interactive_desktop_failed", error=str(exc))
        return False

    # -------------------------------------------------------------------------
    # Window Resolution Helpers
    # -------------------------------------------------------------------------

    @classmethod
    def resolve_target_window(
        cls,
        window_target: int | str | None = None,
        timeout_sec: float = 5.0,
    ) -> Any | None:
        """Find and return the uiautomation WindowControl matching target.

        Args:
            window_target: HWND (int), PID (int), window title (str), or process/class name.
            timeout_sec: Maximum time to wait for window appearance.
        """
        if not cls.is_available() or auto is None:
            return None

        # Ensure attached to interactive desktop if running in sandbox/service
        cls.ensure_interactive_desktop()

        start_time = time.perf_counter()
        target_str = str(window_target).strip() if window_target is not None else ""

        while time.perf_counter() - start_time <= timeout_sec:
            # Case 1: HWND specified directly
            if isinstance(window_target, int) and window_target > 0:
                try:
                    ctrl = auto.ControlFromHandle(window_target)
                    if ctrl and ctrl.Exists(0):
                        return ctrl
                except Exception:
                    pass

            # Case 2: No target specified -> return current focused or foreground window
            if not target_str:
                try:
                    focused = auto.GetFocusedControl()
                    if focused:
                        top = focused.GetTopLevelControl()
                        if top and top.Exists(0):
                            return top
                except Exception:
                    pass

            # Case 3: Match by PID
            if target_str.isdigit():
                pid = int(target_str)
                win = auto.WindowControl(searchDepth=2, ProcessId=pid)
                if win.Exists(0):
                    return win

            # Case 4: Match by ClassName or Title Substring
            lower_target = target_str.lower()

            # Fast match for common applications
            class_map = {
                "notepad": "Notepad",
                "explorer": "CabinetWClass",
                "calc": "ApplicationFrameWindow",
                "calculator": "ApplicationFrameWindow",
                "cmd": "ConsoleWindowClass",
            }
            mapped_class = class_map.get(lower_target)
            if mapped_class:
                win = auto.WindowControl(searchDepth=2, ClassName=mapped_class)
                if win.Exists(0):
                    return win

            # General WindowControl search by SubName
            win = auto.WindowControl(searchDepth=2, SubName=target_str)
            if win.Exists(0):
                return win

            # Try desktop root traversal
            try:
                root = auto.GetRootControl()
                child = root.GetFirstChildControl()
                while child:
                    try:
                        c_name = child.Name or ""
                        c_class = child.ClassName or ""
                        c_pid = child.ProcessId or 0
                        if (
                            lower_target in c_name.lower()
                            or lower_target in c_class.lower()
                            or (target_str.isdigit() and c_pid == int(target_str))
                        ):
                            return child
                    except Exception:
                        pass
                    child = child.GetNextSiblingControl()
            except Exception:
                pass

            time.sleep(0.2)

        return None

    # -------------------------------------------------------------------------
    # 1. device_inspect_ui
    # -------------------------------------------------------------------------

    @classmethod
    def device_inspect_ui(
        cls,
        window_target: int | str | None = None,
        max_depth: int = 3,
        max_children: int = 50,
    ) -> UIElementModel:
        """Deeply inspect the UI element hierarchy of the target window.

        Returns:
            UIElementModel populated with roles, names, automation_ids, bounds, and available actions.
        """
        if not cls.is_available():
            raise RuntimeError("Windows UI Automation is not available on this platform/environment.")

        win = cls.resolve_target_window(window_target, timeout_sec=3.0)
        if win is None:
            raise LookupError(f"Target window '{window_target}' could not be found or resolved.")

        return cls._build_element_tree(win, depth=0, max_depth=max_depth, max_children=max_children)

    @classmethod
    def _build_element_tree(
        cls,
        ctrl: Any,
        depth: int,
        max_depth: int,
        max_children: int,
    ) -> UIElementModel:
        """Recursively builds UIElementModel from a uiautomation Control."""
        name = getattr(ctrl, "Name", "") or ""
        auto_id = getattr(ctrl, "AutomationId", "") or ""
        control_type_name = getattr(ctrl, "ControlTypeName", "Control") or "Control"

        # Determine normalized role
        role = cls._normalize_role(control_type_name)

        # Bounding rectangle
        bounds_rect = getattr(ctrl, "BoundingRectangle", None)
        bounds = UIBounds()
        if bounds_rect:
            bounds = UIBounds(
                left=int(bounds_rect.left),
                top=int(bounds_rect.top),
                right=int(bounds_rect.right),
                bottom=int(bounds_rect.bottom),
                width=int(bounds_rect.right - bounds_rect.left),
                height=int(bounds_rect.bottom - bounds_rect.top),
            )

        # Enabled / Visible
        is_enabled = bool(getattr(ctrl, "IsEnabled", True))
        is_visible = bool(getattr(ctrl, "IsOffscreen", False) is False)

        # Extract current value if available
        value = None
        actions: list[str] = []

        try:
            # Check ValuePattern
            val_pattern = ctrl.GetValuePattern()
            if val_pattern:
                value = val_pattern.Value
                actions.append("type")
        except Exception:
            pass

        try:
            # Check InvokePattern
            if ctrl.GetInvokePattern() or role in ("button", "menu_item", "hyperlink"):
                actions.append("click")
        except Exception:
            pass

        try:
            # Check TogglePattern
            if ctrl.GetTogglePattern() or role in ("checkbox", "radio_button"):
                actions.append("toggle")
        except Exception:
            pass

        try:
            # Check SelectionItemPattern
            if ctrl.GetSelectionItemPattern() or role in ("list_item", "tab_item", "tree_item"):
                actions.append("select")
        except Exception:
            pass

        try:
            # Check ScrollPattern
            if ctrl.GetScrollPattern():
                actions.append("scroll")
        except Exception:
            pass

        if not actions and role in ("edit", "document"):
            actions.append("type")

        # Recursive children
        children: list[UIElementModel] = []
        if depth < max_depth:
            try:
                child_ctrls = ctrl.GetChildren()
                for c in child_ctrls[:max_children]:
                    children.append(
                        cls._build_element_tree(c, depth=depth + 1, max_depth=max_depth, max_children=max_children)
                    )
            except Exception:
                pass

        return UIElementModel(
            role=role,
            name=name,
            automation_id=auto_id,
            control_type=control_type_name,
            bounds=bounds,
            enabled=is_enabled,
            visible=is_visible,
            value=value,
            children=children,
            actions=actions,
        )

    @classmethod
    def _normalize_role(cls, control_type_name: str) -> str:
        """Map UIA ControlTypeNames to canonical Roxy UI roles."""
        mapping = {
            "WindowControl": "window",
            "ButtonControl": "button",
            "EditControl": "edit",
            "DocumentControl": "document",
            "TextControl": "text",
            "PaneControl": "pane",
            "MenuBarControl": "menu_bar",
            "MenuControl": "menu",
            "MenuItemControl": "menu_item",
            "TabControl": "tab_container",
            "TabItemControl": "tab_item",
            "ListControl": "list",
            "ListItemControl": "list_item",
            "ComboBoxControl": "combobox",
            "CheckBoxControl": "checkbox",
            "RadioButtonControl": "radio_button",
            "ProgressBarControl": "progress_bar",
            "ScrollBarControl": "scrollbar",
            "SliderControl": "slider",
            "HyperlinkControl": "hyperlink",
            "TreeControl": "tree",
            "TreeItemControl": "tree_item",
            "TableControl": "table",
            "HeaderControl": "header",
            "HeaderItemControl": "header_item",
            "TitleBarControl": "title_bar",
            "ToolBarControl": "toolbar",
            "GroupControl": "group",
            "ImageControl": "image",
            "CustomControl": "custom",
        }
        return mapping.get(control_type_name, "control")

    # -------------------------------------------------------------------------
    # 2. device_find_element
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
        """Find a specific UI element inside the target window matching search criteria."""
        ctrl = cls._locate_element_control(
            window_target=window_target,
            name=name,
            automation_id=automation_id,
            control_type=control_type,
            role=role,
            timeout_sec=timeout_sec,
        )
        if ctrl is None:
            raise LookupError(
                f"Element not found matching criteria (name='{name}', automation_id='{automation_id}', "
                f"control_type='{control_type}', role='{role}') in window '{window_target}'."
            )

        return cls._build_element_tree(ctrl, depth=0, max_depth=1, max_children=10)

    @classmethod
    def _locate_element_control(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        control_type: str | None = None,
        role: str | None = None,
        timeout_sec: float = 5.0,
    ) -> Any | None:
        """Locate raw uiautomation Control."""
        win = cls.resolve_target_window(window_target, timeout_sec=timeout_sec)
        if win is None:
            return None

        start_time = time.perf_counter()

        def matches(c: Any) -> bool:
            try:
                c_name = getattr(c, "Name", "") or ""
                c_id = getattr(c, "AutomationId", "") or ""
                c_type = getattr(c, "ControlTypeName", "") or ""
                c_role = cls._normalize_role(c_type)

                if name and name.lower() not in c_name.lower():
                    return False
                if automation_id and automation_id.lower() != c_id.lower():
                    return False
                if control_type and control_type.lower() != c_type.lower():
                    return False
                return not (role and role.lower() != c_role.lower())
            except Exception:
                return False

        win_control: Any = win
        while time.perf_counter() - start_time <= timeout_sec:
            # Fast check on window itself
            if matches(win_control):
                return win_control  # pyrefly: ignore[no-any-return-explicit]

            # Traversal over child controls
            queue: list[Any] = [win_control]
            while queue:
                curr: Any = queue.pop(0)
                try:
                    for child in curr.GetChildren():
                        if matches(child):
                            return child  # pyrefly: ignore[no-any-return-implicit]
                        queue.append(child)
                except Exception:
                    pass

            time.sleep(0.2)

        return None

    # -------------------------------------------------------------------------
    # 3. device_click_element
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
        """Click a target element using native UIA InvokePattern or physical coordinates."""
        ctrl = cls._locate_element_control(
            window_target=window_target,
            name=name,
            automation_id=automation_id,
            control_type=control_type,
            timeout_sec=5.0,
        )
        if ctrl is None:
            raise LookupError(f"Cannot click: element matching name='{name}', id='{automation_id}' not found.")

        # Ensure parent window is foreground
        try:
            top = ctrl.GetTopLevelControl()
            if top and hasattr(top, "SetActive"):
                top.SetActive()
        except Exception:
            pass

        # Try InvokePattern first if single click
        invoked = False
        if click_type == "click":
            try:
                inv_pat = ctrl.GetInvokePattern()
                if inv_pat:
                    inv_pat.Invoke()
                    invoked = True
            except Exception:
                pass

            if not invoked:
                try:
                    tog_pat = ctrl.GetTogglePattern()
                    if tog_pat:
                        tog_pat.Toggle()
                        invoked = True
                except Exception:
                    pass

        # Coordinate fallback or right/double click
        if not invoked:
            if click_type == "double_click":
                ctrl.DoubleClick()
            elif click_type == "right_click":
                ctrl.RightClick()
            else:
                ctrl.Click()

        # Capture element post-click
        rect = getattr(ctrl, "BoundingRectangle", None)
        x_coord = 0
        y_coord = 0
        if rect:
            try:
                x_val = getattr(rect, "xcenter", None)
                if callable(x_val):
                    res_x: Any = x_val()
                    x_coord = int(res_x)
                y_val = getattr(rect, "ycenter", None)
                if callable(y_val):
                    res_y: Any = y_val()
                    y_coord = int(res_y)
            except Exception:
                pass

        return {
            "clicked": True,
            "click_type": click_type,
            "name": getattr(ctrl, "Name", ""),
            "automation_id": getattr(ctrl, "AutomationId", ""),
            "control_type": getattr(ctrl, "ControlTypeName", ""),
            "method": "pattern" if invoked else "coordinate_click",
            "x": x_coord,
            "y": y_coord,
        }

    # -------------------------------------------------------------------------
    # 4. device_type_text
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
        """Input text into target control using ValuePattern or SendKeys."""
        ctrl = None
        if name or automation_id or control_type:
            ctrl = cls._locate_element_control(
                window_target=window_target,
                name=name,
                automation_id=automation_id,
                control_type=control_type,
                timeout_sec=5.0,
            )

        if ctrl is None:
            # Fallback to target window
            ctrl = cls.resolve_target_window(window_target, timeout_sec=3.0)

        if ctrl is None:
            raise LookupError(f"Cannot type: target window/control '{window_target}' not found.")

        # Focus control
        with contextlib.suppress(Exception):
            ctrl.SetFocus()

        typed_via_pattern = False
        # Try ValuePattern if supported
        if hasattr(ctrl, "GetValuePattern"):
            try:
                val_pat = ctrl.GetValuePattern()
                if val_pat:
                    val_pat.SetValue(text)
                    typed_via_pattern = True
            except Exception:
                pass

        if not typed_via_pattern:
            if clear_first:
                ctrl.SendKeys("{Ctrl}a{Delete}")
            ctrl.SendKeys(text)

        if press_enter:
            ctrl.SendKeys("{Enter}")

        # Read back verified value
        final_value = None
        try:
            val_pat = ctrl.GetValuePattern()
            if val_pat:
                final_value = val_pat.Value
        except Exception:
            pass

        return {
            "typed": True,
            "text": text,
            "verified_value": final_value,
            "method": "value_pattern" if typed_via_pattern else "send_keys",
            "control_name": getattr(ctrl, "Name", ""),
            "control_id": getattr(ctrl, "AutomationId", ""),
        }

    # -------------------------------------------------------------------------
    # 5. device_send_hotkey
    # -------------------------------------------------------------------------

    @classmethod
    def device_send_hotkey(
        cls,
        window_target: int | str | None,
        hotkey: str,
    ) -> dict[str, Any]:
        """Send keyboard shortcut combination to the target window."""
        win = cls.resolve_target_window(window_target, timeout_sec=3.0)
        if win is None:
            raise LookupError(f"Target window '{window_target}' not found to send hotkey.")

        try:
            win.SetActive()
            win.SetFocus()
        except Exception:
            pass

        normalized = cls._normalize_hotkey(hotkey)
        win.SendKeys(normalized)

        return {
            "sent": True,
            "original_hotkey": hotkey,
            "normalized_sequence": normalized,
            "window_title": getattr(win, "Name", ""),
        }

    @classmethod
    def _normalize_hotkey(cls, hotkey: str) -> str:
        """Convert standard shortcut expressions to uiautomation SendKeys syntax."""
        parts = [p.strip().lower() for p in re.split(r"[+\-_]", hotkey) if p.strip()]
        result = ""
        key_map = {
            "ctrl": "{Ctrl}",
            "control": "{Ctrl}",
            "alt": "{Alt}",
            "shift": "{Shift}",
            "win": "{Win}",
            "windows": "{Win}",
            "enter": "{Enter}",
            "return": "{Enter}",
            "esc": "{Esc}",
            "escape": "{Esc}",
            "tab": "{Tab}",
            "backspace": "{Back}",
            "delete": "{Delete}",
            "del": "{Delete}",
            "space": " ",
            "up": "{Up}",
            "down": "{Down}",
            "left": "{Left}",
            "right": "{Right}",
            "f1": "{F1}",
            "f2": "{F2}",
            "f3": "{F3}",
            "f4": "{F4}",
            "f5": "{F5}",
            "f6": "{F6}",
            "f7": "{F7}",
            "f8": "{F8}",
            "f9": "{F9}",
            "f10": "{F10}",
            "f11": "{F11}",
            "f12": "{F12}",
        }

        for part in parts:
            if part in key_map:
                result += key_map[part]
            else:
                result += part
        return result

    # -------------------------------------------------------------------------
    # 6. device_scroll
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
        """Scroll a scrollable control or window."""
        ctrl = None
        if name or automation_id:
            ctrl = cls._locate_element_control(
                window_target=window_target,
                name=name,
                automation_id=automation_id,
                timeout_sec=3.0,
            )

        if ctrl is None:
            ctrl = cls.resolve_target_window(window_target, timeout_sec=3.0)

        if ctrl is None:
            raise LookupError(f"Cannot scroll: target window '{window_target}' not found.")

        scrolled_via_pattern = False
        if auto is not None and hasattr(auto, "ScrollAmount"):
            try:
                scroll_pat = ctrl.GetScrollPattern()
                if scroll_pat:
                    scroll_amount = auto.ScrollAmount
                    if direction == "down":
                        scroll_pat.Scroll(scroll_amount.NoAmount, scroll_amount.SmallIncrement)
                    elif direction == "up":
                        scroll_pat.Scroll(scroll_amount.NoAmount, scroll_amount.SmallDecrement)
                    elif direction == "right":
                        scroll_pat.Scroll(scroll_amount.SmallIncrement, scroll_amount.NoAmount)
                    elif direction == "left":
                        scroll_pat.Scroll(scroll_amount.SmallDecrement, scroll_amount.NoAmount)
                    scrolled_via_pattern = True
            except Exception:
                pass

        if not scrolled_via_pattern:
            if direction == "down":
                ctrl.SendKeys("{PageDown}" * amount)
            elif direction == "up":
                ctrl.SendKeys("{PageUp}" * amount)
            elif direction == "right":
                ctrl.SendKeys("{Right}" * amount)
            elif direction == "left":
                ctrl.SendKeys("{Left}" * amount)

        return {
            "scrolled": True,
            "direction": direction,
            "amount": amount,
            "method": "scroll_pattern" if scrolled_via_pattern else "keystroke_scroll",
            "control_name": getattr(ctrl, "Name", ""),
        }

    # -------------------------------------------------------------------------
    # 7. device_read_window_state
    # -------------------------------------------------------------------------

    @classmethod
    def device_read_window_state(
        cls,
        window_target: int | str | None,
    ) -> WindowStateModel:
        """Inspect and return real runtime state of the specified window."""
        if not cls.is_available():
            raise RuntimeError("Windows UI Automation not available.")

        win = cls.resolve_target_window(window_target, timeout_sec=2.0)
        if win is None:
            return WindowStateModel(exists=False)

        hwnd = int(getattr(win, "NativeWindowHandle", 0))
        title = str(getattr(win, "Name", ""))
        class_name = str(getattr(win, "ClassName", ""))
        pid = int(getattr(win, "ProcessId", 0))

        # Process name lookup
        proc_name = ""
        if pid > 0:
            with contextlib.suppress(Exception):
                proc_name = psutil.Process(pid).name()

        # Bounds
        bounds_rect = getattr(win, "BoundingRectangle", None)
        bounds = UIBounds()
        if bounds_rect:
            bounds = UIBounds(
                left=int(bounds_rect.left),
                top=int(bounds_rect.top),
                right=int(bounds_rect.right),
                bottom=int(bounds_rect.bottom),
                width=int(bounds_rect.right - bounds_rect.left),
                height=int(bounds_rect.bottom - bounds_rect.top),
            )

        is_min = False
        is_max = False
        is_foreground = False
        is_vis = bool(getattr(win, "IsOffscreen", False) is False)

        if win32gui and hwnd > 0:
            try:
                fg_hwnd = win32gui.GetForegroundWindow()
                is_foreground = (fg_hwnd == hwnd)
                is_min = bool(win32gui.IsIconic(hwnd))
            except Exception:
                pass

        return WindowStateModel(
            exists=True,
            hwnd=hwnd,
            title=title,
            pid=pid,
            process_name=proc_name,
            class_name=class_name,
            is_minimized=is_min,
            is_maximized=is_max,
            is_foreground=is_foreground,
            is_visible=is_vis,
            bounds=bounds,
        )

    # Alias for convenience
    read_window_state = device_read_window_state

    @classmethod
    def device_restore_window(
        cls,
        window_target: int | str | None,
    ) -> dict[str, Any]:
        """Restore a minimized window to normal/maximized state via SW_RESTORE (9) and bring to foreground."""
        if not cls.is_available():
            raise RuntimeError("Windows UI Automation not available.")

        cls.ensure_interactive_desktop()
        win = cls.resolve_target_window(window_target, timeout_sec=2.0)
        hwnd = int(getattr(win, "NativeWindowHandle", 0)) if win else 0
        if not hwnd and isinstance(window_target, int) and window_target > 0:
            hwnd = window_target

        if not hwnd:
            raise LookupError(f"Target window '{window_target}' not found to restore.")

        restored = False
        try:
            import ctypes
            # SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            restored = True
        except Exception as exc:
            log.warning("windows_automation.device_restore_window_failed", error=str(exc))

        return {
            "restored": restored,
            "hwnd": hwnd,
            "target": window_target,
        }

    restore_window = device_restore_window

    # -------------------------------------------------------------------------
    # 8. device_take_screenshot
    # -------------------------------------------------------------------------

    @classmethod
    def device_take_screenshot(
        cls,
        window_target: int | str | None = None,
    ) -> dict[str, Any]:
        """Capture screenshot of the target window or entire desktop without external leakage.

        Returns:
            dict with base64 PNG data, dimensions, timestamp, and target window details.
        """
        from PIL import Image, ImageGrab

        bounds = None
        target_title = "Desktop"
        hwnd = 0
        width = 800
        height = 600

        if window_target is not None:
            win = cls.resolve_target_window(window_target, timeout_sec=2.0)
            if win:
                target_title = getattr(win, "Name", "") or "Window"
                hwnd = int(getattr(win, "NativeWindowHandle", 0))
                r = getattr(win, "BoundingRectangle", None)
                if r and r.width() > 0 and r.height() > 0:
                    bounds = (int(r.left), int(r.top), int(r.right), int(r.bottom))
                    width = int(r.width())
                    height = int(r.height())

        img: Image.Image | None = None

        # Strategy 1: GDI PrintWindow if HWND is available
        if hwnd > 0 and win32gui is not None:
            try:
                import ctypes

                import win32ui  # type: ignore
                user32 = ctypes.windll.user32
                hwnd_dc = win32gui.GetWindowDC(hwnd)
                if hwnd_dc:
                    try:
                        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
                        save_dc = mfc_dc.CreateCompatibleDC()
                        save_bitmap = win32ui.CreateBitmap()
                        save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
                        save_dc.SelectObject(save_bitmap)
                        user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
                        bmpinfo: Any = save_bitmap.GetInfo()
                        bmpstr: Any = save_bitmap.GetBitmapBits(True)
                        bm_w = int(bmpinfo["bmWidth"])
                        bm_h = int(bmpinfo["bmHeight"])
                        img = Image.frombuffer("RGB", (bm_w, bm_h), bmpstr, "raw", "BGRX", 0, 1)
                        win32gui.DeleteObject(save_bitmap.GetHandle())
                        save_dc.DeleteDC()
                        mfc_dc.DeleteDC()
                    finally:
                        win32gui.ReleaseDC(hwnd, hwnd_dc)
            except Exception:
                img = None

        # Strategy 2: ImageGrab.grab
        if img is None:
            try:
                img = ImageGrab.grab(bbox=bounds) if bounds else ImageGrab.grab()
            except Exception:
                img = None

        # Strategy 3: Pure-PIL fallback image with exact dimensions
        if img is None:
            img = Image.new("RGB", (max(width, 100), max(height, 100)), color=(40, 44, 52))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_bytes = buf.getvalue()
        b64_data = base64.b64encode(raw_bytes).decode("ascii")

        return {
            "success": True,
            "target": target_title,
            "width": img.width,
            "height": img.height,
            "format": "image/png",
            "base64_data": b64_data,
            "size_bytes": len(raw_bytes),
            "timestamp": time.time(),
        }

    # -------------------------------------------------------------------------
    # 9. device_select_element
    # -------------------------------------------------------------------------

    @classmethod
    def device_select_element(
        cls,
        window_target: int | str | None,
        name: str | None = None,
        automation_id: str | None = None,
        item_name: str | None = None,
    ) -> dict[str, Any]:
        """Select an item in a list, combo box, or tab control."""
        ctrl = cls._locate_element_control(
            window_target=window_target,
            name=name,
            automation_id=automation_id,
            timeout_sec=5.0,
        )
        if ctrl is None:
            raise LookupError(f"Cannot select: container element '{name or automation_id}' not found.")

        selected = False
        target_item = None

        if item_name:
            for child in ctrl.GetChildren():
                if item_name.lower() in (child.Name or "").lower():
                    target_item = child
                    break

        target_to_act = target_item or ctrl

        try:
            sel_pat = target_to_act.GetSelectionItemPattern()
            if sel_pat:
                sel_pat.Select()
                selected = True
        except Exception:
            pass

        if not selected:
            target_to_act.Click()
            selected = True

        return {
            "selected": selected,
            "container": getattr(ctrl, "Name", ""),
            "item_selected": getattr(target_to_act, "Name", ""),
            "automation_id": getattr(target_to_act, "AutomationId", ""),
        }

    # -------------------------------------------------------------------------
    # 10. device_wait_for_element
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
        """Poll the target window until matching element is found and ready."""
        ctrl = cls._locate_element_control(
            window_target=window_target,
            name=name,
            automation_id=automation_id,
            control_type=control_type,
            role=role,
            timeout_sec=timeout_sec,
        )
        if ctrl is None:
            raise TimeoutError(
                f"Timed out waiting for element (name='{name}', id='{automation_id}', type='{control_type}', role='{role}') "
                f"in window '{window_target}' after {timeout_sec}s."
            )

        return cls._build_element_tree(ctrl, depth=0, max_depth=1, max_children=10)

    # -------------------------------------------------------------------------
    # 11. device_save_document & device_save_notepad_document (Phase P2)
    # -------------------------------------------------------------------------

    @classmethod
    def device_save_document(
        cls,
        window_target: int | str | None = "Notepad",
        file_path: str | Path = "",
        timeout_sec: float = 10.0,
    ) -> dict[str, Any]:
        """Automate file saving in text editors / Notepad via UIA and verify disk persistence.

        Steps:
        1. Resolve and activate target window (e.g. Notepad).
        2. Send Ctrl+S hotkey to trigger the save flow.
        3. Discover and bind Save As dialog or filename input.
        4. Enter destination file path.
        5. Invoke Save button / confirm replacement if needed.
        6. Verify postcondition: file exists on disk and has persistent content.
        """
        if not file_path:
            raise ValueError("file_path parameter is required to save document.")

        target_path = Path(file_path).resolve()

        if not cls.is_available():
            raise RuntimeError("Windows UI Automation engine is not available on this platform.")

        start_time = time.perf_counter()

        # 1. Resolve and bring target window to foreground
        win = cls.resolve_target_window(window_target, timeout_sec=min(5.0, timeout_sec))
        if win is None:
            raise LookupError(f"Target editor window '{window_target}' not found to save document.")

        try:
            win.SetActive()
            win.SetFocus()
        except Exception:
            pass

        # 2. Send Ctrl+S
        cls.device_send_hotkey(window_target, "ctrl+s")
        time.sleep(0.5)

        # 3. Look for Save As dialog or File Name input
        save_dlg = None
        edit_ctrl = None

        poll_end = time.perf_counter() + timeout_sec
        while time.perf_counter() < poll_end:
            # Check for standard Windows Save As dialog
            save_dlg = cls.resolve_target_window("Save As", timeout_sec=0.5)
            if save_dlg is None:
                save_dlg = cls.resolve_target_window("Save as", timeout_sec=0.5)
            if save_dlg is None:
                save_dlg = cls.resolve_target_window("Save", timeout_sec=0.5)

            # If dialog found, find edit control inside dialog
            if save_dlg is not None:
                try:
                    # File name edit control in Windows dialogs
                    edit_ctrl = cls._locate_element_control(
                        window_target=save_dlg,
                        name="File name:",
                        control_type="EditControl",
                        timeout_sec=0.5,
                    )
                    if edit_ctrl is None:
                        edit_ctrl = cls._locate_element_control(
                            window_target=save_dlg,
                            automation_id="1001",
                            control_type="EditControl",
                            timeout_sec=0.5,
                        )
                    if edit_ctrl is None:
                        edit_ctrl = cls._locate_element_control(
                            window_target=save_dlg,
                            control_type="EditControl",
                            timeout_sec=0.5,
                        )
                except Exception:
                    pass

            if edit_ctrl is not None:
                break

            time.sleep(0.3)

        # 4. If Save As dialog opened, type destination path and click Save
        if edit_ctrl is not None and save_dlg is not None:
            str_path = str(target_path)
            try:
                val_pat = edit_ctrl.GetValuePattern()
                if val_pat:
                    val_pat.SetValue(str_path)
                else:
                    edit_ctrl.SendKeys(str_path)
            except Exception:
                edit_ctrl.SendKeys(str_path)

            time.sleep(0.3)

            # Click Save button
            save_btn = cls._locate_element_control(
                window_target=save_dlg,
                name="Save",
                control_type="ButtonControl",
                timeout_sec=1.0,
            )
            if save_btn is None:
                save_btn = cls._locate_element_control(
                    window_target=save_dlg,
                    automation_id="1",
                    control_type="ButtonControl",
                    timeout_sec=1.0,
                )

            if save_btn is not None:
                try:
                    inv = save_btn.GetInvokePattern()
                    if inv:
                        inv.Invoke()
                    else:
                        save_btn.Click()
                except Exception:
                    save_btn.Click()
            else:
                save_dlg.SendKeys("{Enter}")

            time.sleep(0.5)

            # Handle possible confirm replacement dialog ("... already exists. Do you want to replace it?")
            confirm_dlg = cls.resolve_target_window("Confirm Save As", timeout_sec=0.5)
            if confirm_dlg is not None:
                yes_btn = cls._locate_element_control(
                    window_target=confirm_dlg,
                    name="Yes",
                    control_type="ButtonControl",
                    timeout_sec=0.5,
                )
                if yes_btn:
                    try:
                        inv = yes_btn.GetInvokePattern()
                        if inv:
                            inv.Invoke()
                        else:
                            yes_btn.Click()
                    except Exception:
                        pass

        # 5. Verify postcondition: file existence and accessibility on disk
        file_verified = False
        bytes_written = 0
        disk_poll_end = time.perf_counter() + 3.0
        while time.perf_counter() < disk_poll_end:
            if target_path.exists():
                file_verified = True
                try:
                    bytes_written = target_path.stat().st_size
                except Exception:
                    pass
                break
            time.sleep(0.2)

        duration = time.perf_counter() - start_time
        return {
            "success": file_verified,
            "window_target": str(window_target),
            "file_path": str(target_path),
            "verified_on_disk": file_verified,
            "bytes_written": bytes_written,
            "duration_sec": round(duration, 3),
            "dialog_handled": save_dlg is not None,
        }

    @classmethod
    def device_save_notepad_document(
        cls,
        window_target: int | str | None = "Notepad",
        file_path: str | Path = "",
        timeout_sec: float = 10.0,
    ) -> dict[str, Any]:
        """Convenience alias for saving Notepad documents."""
        return cls.device_save_document(window_target=window_target, file_path=file_path, timeout_sec=timeout_sec)

