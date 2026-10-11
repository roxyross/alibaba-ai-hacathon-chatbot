"""Phase 2 (P2) Acceptance Tests: Application-Specific Integrations & Device Bridges.

Covers:
1. Windows Notepad UIA Save Automation and Disk Postcondition Verification
2. Android ADB Prerequisite Detection & Platform Guidance
3. Safe WhatsApp Web QR Session Onboarding CLI Launcher
4. Meta WhatsApp Business Cloud API Credential & Configuration Validation
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.device.android_automation import AndroidAutomationEngine
from app.device.schemas import AndroidPrerequisiteReport
from app.device.windows_automation import WindowsUIAutomationEngine
from app.integrations.whatsapp.cloud_api_adapter import WhatsAppCloudApiAdapter
from app.integrations.whatsapp.launch_web_profile import (
    check_profile_status,
    launch_whatsapp_web_onboarding,
)
from app.integrations.whatsapp.launch_web_profile import (
    main as launcher_main,
)

# =============================================================================
# Typed Mock Stubs for IDE Type Checking (Pylance/Pyright)
# =============================================================================

def _mock_return_none(*_args: Any, **_kwargs: Any) -> Any:
    return None


def _mock_return_true(*_args: Any, **_kwargs: Any) -> bool:
    return True


def _mock_adb_win(*_args: Any, **_kwargs: Any) -> str:
    return "C:\\platform-tools\\adb.exe"


def _mock_adb_unix(*_args: Any, **_kwargs: Any) -> str:
    return "/usr/bin/adb"


def _mock_adb_devices_attached(*_args: Any, **_kwargs: Any) -> list[str]:
    return ["emulator-5554", "RF8M10ABCDE"]


def _mock_adb_devices_empty(*_args: Any, **_kwargs: Any) -> list[str]:
    return []


def _mock_hotkey_sent(*_args: Any, **_kwargs: Any) -> dict[str, bool]:
    return {"sent": True}


# =============================================================================
# 1. Android ADB Prerequisite Detection Tests
# =============================================================================

class TestAndroidPrerequisites:
    """Verify AndroidAutomationEngine.check_prerequisites under all conditions."""

    def test_adb_missing_reports_actionable_guidance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When adb is missing from PATH, returns status='ADB_MISSING' with platform install commands."""
        monkeypatch.setattr(shutil, "which", _mock_return_none)

        report = AndroidAutomationEngine.check_prerequisites()
        assert isinstance(report, AndroidPrerequisiteReport)
        assert report.is_adb_installed is False
        assert report.adb_path is None
        assert report.status == "ADB_MISSING"
        assert report.attached_devices == []

        if sys.platform == "win32":
            assert report.installation_command == "winget install Google.PlatformTools"
            assert any("winget install" in r for r in report.recommendations)
        elif sys.platform == "darwin":
            assert report.installation_command == "brew install android-platform-tools"
        else:
            assert report.installation_command == "sudo apt-get install -y adb"

    def test_adb_installed_with_devices(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When adb is installed and devices are connected, returns status='READY'."""
        monkeypatch.setattr(shutil, "which", _mock_adb_win)
        monkeypatch.setattr(
            AndroidAutomationEngine,
            "list_adb_devices",
            classmethod(_mock_adb_devices_attached),
        )

        report = AndroidAutomationEngine.check_prerequisites()
        assert report.is_adb_installed is True
        assert report.adb_path == "C:\\platform-tools\\adb.exe"
        assert report.status == "READY"
        assert len(report.attached_devices) == 2
        assert "emulator-5554" in report.attached_devices
        assert any("2 Android device(s)" in r for r in report.recommendations)

    def test_adb_installed_no_devices(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When adb is installed but no devices are connected, returns status='NO_DEVICES' with setup steps."""
        monkeypatch.setattr(shutil, "which", _mock_adb_unix)
        monkeypatch.setattr(
            AndroidAutomationEngine,
            "list_adb_devices",
            classmethod(_mock_adb_devices_empty),
        )

        report = AndroidAutomationEngine.check_prerequisites()
        assert report.is_adb_installed is True
        assert report.status == "NO_DEVICES"
        assert report.attached_devices == []
        assert any("USB Debugging" in r for r in report.recommendations)
        assert any("Developer Options" in r for r in report.recommendations)

    def test_cross_platform_installation_commands(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify command synthesis across Windows, macOS, and Linux."""
        monkeypatch.setattr(shutil, "which", _mock_return_none)

        # 1. Darwin (macOS)
        monkeypatch.setattr(sys, "platform", "darwin")
        darwin_report = AndroidAutomationEngine.check_prerequisites()
        assert darwin_report.installation_command == "brew install android-platform-tools"

        # 2. Linux
        monkeypatch.setattr(sys, "platform", "linux")
        linux_report = AndroidAutomationEngine.check_prerequisites()
        assert linux_report.installation_command == "sudo apt-get install -y adb"

        # 3. Windows
        monkeypatch.setattr(sys, "platform", "win32")
        win_report = AndroidAutomationEngine.check_prerequisites()
        assert win_report.installation_command == "winget install Google.PlatformTools"


# =============================================================================
# 2. Windows Notepad Save Automation Tests
# =============================================================================

class TestWindowsNotepadSave:
    """Verify WindowsUIAutomationEngine.device_save_document."""

    def test_save_document_requires_path(self) -> None:
        """ValueError raised when file_path is empty."""
        with pytest.raises(ValueError, match="file_path parameter is required"):
            WindowsUIAutomationEngine.device_save_document(window_target="Notepad", file_path="")

    def test_save_document_window_not_found(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LookupError raised when target editor window does not exist."""
        monkeypatch.setattr(WindowsUIAutomationEngine, "is_available", classmethod(_mock_return_true))
        monkeypatch.setattr(WindowsUIAutomationEngine, "resolve_target_window", classmethod(_mock_return_none))

        with pytest.raises(LookupError, match="Target editor window 'NonExistentEditor' not found"):
            WindowsUIAutomationEngine.device_save_document(
                window_target="NonExistentEditor",
                file_path="C:/tmp/test.txt",
                timeout_sec=0.5,
            )

    def test_save_document_mocked_end_to_end(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify complete simulated save flow with disk postcondition verification."""
        test_file = tmp_path / "mocked_save_note.txt"

        mock_notepad_win = MagicMock()
        mock_save_dlg = MagicMock()
        mock_edit_ctrl = MagicMock()
        mock_save_btn = MagicMock()

        # Simulate Save button click writing the file to disk
        def _mock_save_click(*args: Any, **kwargs: Any) -> None:
            test_file.write_text("Saved by Roxy Universal Automation", encoding="utf-8")

        mock_save_btn.Click.side_effect = _mock_save_click
        mock_save_btn.Click = _mock_save_click
        mock_save_btn.GetInvokePattern.return_value = None

        def _mock_resolve_window(cls: Any, /, *args: Any, target: Any = None, **kwargs: Any) -> Any:
            resolved = target if target is not None else (args[0] if args else None)
            if resolved and "Notepad" in str(resolved):
                return mock_notepad_win
            elif resolved and "Save" in str(resolved):
                return mock_save_dlg
            return None

        def _mock_locate_element(
            cls: Any,
            /,
            *args: Any,
            window_target: Any = None,
            name: Any = None,
            automation_id: Any = None,
            control_type: Any = None,
            **kwargs: Any,
        ) -> Any:
            if control_type == "EditControl" or name == "File name:":
                return mock_edit_ctrl
            elif control_type == "ButtonControl" or name == "Save":
                return mock_save_btn
            return None

        monkeypatch.setattr(WindowsUIAutomationEngine, "is_available", classmethod(_mock_return_true))
        monkeypatch.setattr(WindowsUIAutomationEngine, "resolve_target_window", classmethod(_mock_resolve_window))
        monkeypatch.setattr(WindowsUIAutomationEngine, "_locate_element_control", classmethod(_mock_locate_element))
        monkeypatch.setattr(WindowsUIAutomationEngine, "device_send_hotkey", classmethod(_mock_hotkey_sent))

        result = WindowsUIAutomationEngine.device_save_document(
            window_target="Notepad",
            file_path=str(test_file),
            timeout_sec=2.0,
        )

        assert result["success"] is True
        assert result["verified_on_disk"] is True
        assert result["file_path"] == str(test_file.resolve())
        assert result["bytes_written"] > 0
        assert test_file.read_text(encoding="utf-8") == "Saved by Roxy Universal Automation"

    def test_save_notepad_document_alias(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify device_save_notepad_document alias invokes device_save_document."""
        test_file = tmp_path / "alias_note.txt"
        test_file.write_text("Hello", encoding="utf-8")

        def _mock_save_doc(
            cls: Any,
            /,
            window_target: Any = "Notepad",
            file_path: Any = "",
            timeout_sec: float = 10.0,
            **kwargs: Any,
        ) -> dict[str, Any]:
            return {
                "success": True,
                "file_path": str(file_path),
                "verified_on_disk": True,
            }

        monkeypatch.setattr(
            WindowsUIAutomationEngine,
            "device_save_document",
            classmethod(_mock_save_doc),
        )

        res = WindowsUIAutomationEngine.device_save_notepad_document("Notepad", str(test_file))
        assert res["success"] is True
        assert res["verified_on_disk"] is True


# =============================================================================
# 3. Safe WhatsApp Web QR Session Onboarding Tests
# =============================================================================

class TestWhatsAppWebOnboardingLauncher:
    """Verify launch_web_profile CLI and programmatic functions."""

    def test_check_profile_status_uninitialized(self, tmp_path: Path) -> None:
        """Uninitialized profile folder reports status='EMPTY' or 'NOT_CONFIGURED'."""
        empty_profile = tmp_path / "empty_wa_profile"
        status_before = check_profile_status(empty_profile)
        assert status_before["exists"] is False
        assert status_before["status"] == "NOT_CONFIGURED"
        assert status_before["is_authenticated"] is False

        # Create empty directory
        empty_profile.mkdir()
        status_after = check_profile_status(empty_profile)
        assert status_after["exists"] is True
        assert status_after["status"] == "EMPTY"
        assert status_after["file_count"] == 0
        assert status_after["is_authenticated"] is False

    def test_check_profile_status_authenticated(self, tmp_path: Path) -> None:
        """Profile folder with storage items reports status='AUTHENTICATED'."""
        auth_profile = tmp_path / "auth_wa_profile"
        auth_profile.mkdir()
        (auth_profile / "Cookies").write_bytes(b"dummy_session_cookie_store")
        (auth_profile / "Local Storage").mkdir()

        status = check_profile_status(auth_profile)
        assert status["exists"] is True
        assert status["status"] == "AUTHENTICATED"
        assert status["file_count"] == 2
        assert status["total_bytes"] > 0
        assert status["is_authenticated"] is True

    @pytest.mark.asyncio
    async def test_launch_whatsapp_web_onboarding_dry_run(self, tmp_path: Path) -> None:
        """Dry-run validates profile directory setup without launching browser."""
        test_profile = tmp_path / "dry_run_profile"
        result = await launch_whatsapp_web_onboarding(
            profile_dir=test_profile,
            dry_run=True,
        )
        assert result["success"] is True
        assert result["dry_run"] is True
        assert test_profile.exists()
        assert "Dry-run check succeeded" in result["message"]

    def test_cli_main_dry_run_and_status(self, tmp_path: Path) -> None:
        """CLI main function exits cleanly with code 0 on --dry-run and --check-status."""
        test_profile = tmp_path / "cli_profile"

        exit_code_status = launcher_main(["--check-status", "--profile-dir", str(test_profile)])
        assert exit_code_status == 0

        exit_code_dry = launcher_main(["--dry-run", "--profile-dir", str(test_profile)])
        assert exit_code_dry == 0


# =============================================================================
# 4. Meta WhatsApp Business Cloud API Validation Tests
# =============================================================================

class TestWhatsAppCloudApiValidation:
    """Verify WhatsAppCloudApiAdapter.validate_credentials."""

    def test_validate_credentials_missing_all(self) -> None:
        """Empty credentials configuration returns valid=False with specific errors."""
        res = WhatsAppCloudApiAdapter.validate_credentials({})
        assert res["valid"] is False
        assert any("WHATSAPP_PHONE_NUMBER_ID is missing" in err for err in res["errors"])
        assert any("WHATSAPP_ACCESS_TOKEN is missing" in err for err in res["errors"])

    def test_validate_credentials_invalid_formats(self) -> None:
        """Non-numeric phone ID and truncated token trigger explicit errors."""
        bad_config = {
            "phone_number_id": "not_a_number_id",
            "access_token": "short_tok",
            "business_account_id": "invalid_b_id",
        }
        res = WhatsAppCloudApiAdapter.validate_credentials(bad_config)
        assert res["valid"] is False
        assert any("must be numeric" in err for err in res["errors"])
        assert any("truncated or invalid" in err for err in res["errors"])
        assert any("typically numeric" in w for w in res["warnings"])

    def test_validate_credentials_valid_config(self) -> None:
        """Valid Meta System User token and phone number ID pass validation."""
        valid_config = {
            "enabled": True,
            "phone_number_id": "104958372619485",
            "access_token": "EAAX1234567890abcdef1234567890abcdef",
            "business_account_id": "987654321098765",
            "app_secret": "abcdef0123456789abcdef0123456789",
        }
        res = WhatsAppCloudApiAdapter.validate_credentials(valid_config)
        assert res["valid"] is True
        assert len(res["errors"]) == 0
        assert res["configured_phone_number_id"] == "104958372619485"
        assert res["is_enabled"] is True
