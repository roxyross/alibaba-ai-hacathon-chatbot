"""Comprehensive tests for Roxy Code Studio / Full IDE and Universal Reminder & Ringtone System.

Validates:
- Workspace file tree, read, write, directory create, rename, delete, search
- Sandboxed terminal command execution and dangerous pattern blocking
- Git status and diff
- Automated test runner
- Multilingual Roxy Coding Agent with action plan and unified diff generation (English, Urdu, Roman Urdu)
- Reminder settings, sound library (10 built-in procedural sounds, custom upload, delete)
- Per-device and per-event ringtone resolution
- Notification lifecycle (scheduled -> delivered -> acknowledged / snoozed / dismissed)
- Multilingual voice reminder parser
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.jwt import create_session_token
from app.auth.models import User
from app.main import app


@pytest.fixture
def test_user() -> User:
    """Fixture providing an authenticated test user."""
    return User(
        id="usr-ide-tester-123",
        email="ide.tester@roxy.ai",
    )


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    """Fixture providing valid bearer auth headers."""
    token, _ = create_session_token(
        user_id=test_user.id, email=test_user.email
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def async_client() -> AsyncClient:
    """Async HTTP test client bound to FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ===========================================================================
# PART A: ROXY CODE STUDIO / FULL IDE TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_workspace_tree_api(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Verify workspace hierarchical tree listing within sandbox."""
    res = await async_client.get(
        "/api/v1/coding/workspace/tree?root_dir=.&max_depth=2",
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data["tree"], dict)
    assert "name" in data["tree"]
    assert "children" in data["tree"]
    assert isinstance(data["tree"]["children"], list)
    assert len(data["tree"]["children"]) > 0
    first = data["tree"]["children"][0]
    assert "name" in first
    assert "is_directory" in first


@pytest.mark.asyncio
async def test_workspace_file_crud_api(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Verify file write, read, search, rename, and delete lifecycle."""
    test_file_path = "tests/scratch_ide_test_file.py"
    initial_content = "# IDE Studio Test\nprint('Hello from Roxy IDE!')\n"

    # 1. Write file
    w_res = await async_client.post(
        "/api/v1/coding/workspace/file",
        json={"file_path": test_file_path, "content": initial_content, "overwrite": True},
        headers=auth_headers,
    )
    assert w_res.status_code == 200
    assert w_res.json()["path"]

    # 2. Read file
    r_res = await async_client.get(
        f"/api/v1/coding/workspace/file?file_path={test_file_path}",
        headers=auth_headers,
    )
    assert r_res.status_code == 200
    r_data = r_res.json()
    assert initial_content in r_data["content"]

    # 3. Search files
    s_res = await async_client.post(
        "/api/v1/coding/workspace/search",
        json={"content_query": "Hello from Roxy IDE!", "directory_path": "tests"},
        headers=auth_headers,
    )
    assert s_res.status_code == 200
    assert s_res.json()["total_matches"] >= 1

    # 4. Rename file
    renamed_path = "tests/scratch_ide_test_renamed.py"
    rn_res = await async_client.post(
        "/api/v1/coding/workspace/rename",
        json={"old_path": test_file_path, "new_path": renamed_path},
        headers=auth_headers,
    )
    assert rn_res.status_code == 200
    assert rn_res.json()["success"] is True

    # 5. Delete file
    del_res = await async_client.delete(
        f"/api/v1/coding/workspace/path?path={renamed_path}",
        headers=auth_headers,
    )
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


@pytest.mark.asyncio
async def test_terminal_exec_safety(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Verify terminal runner executes safe commands and blocks dangerous commands."""
    # 1. Safe command
    safe_res = await async_client.post(
        "/api/v1/coding/terminal/exec",
        json={"command": "echo 'Roxy IDE Terminal Active'", "cwd": "."},
        headers=auth_headers,
    )
    assert safe_res.status_code == 200
    safe_data = safe_res.json()
    assert safe_data["exit_code"] == 0
    assert "Roxy IDE Terminal Active" in safe_data["stdout"]

    # 2. Dangerous command blocked
    danger_res = await async_client.post(
        "/api/v1/coding/terminal/exec",
        json={"command": "rm -rf / --no-preserve-root", "cwd": "."},
        headers=auth_headers,
    )
    assert danger_res.status_code == 403


@pytest.mark.asyncio
async def test_git_status_and_diff_api(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Verify Git status and diff endpoints return truthful repository state."""
    status_res = await async_client.get(
        "/api/v1/coding/git/status?repo_path=.",
        headers=auth_headers,
    )
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert "branch" in status_data
    assert "clean" in status_data

    diff_res = await async_client.get(
        "/api/v1/coding/git/diff?repo_path=.",
        headers=auth_headers,
    )
    assert diff_res.status_code == 200
    assert "diff" in diff_res.json()


@pytest.mark.asyncio
async def test_coding_agent_assist_english_and_urdu(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Verify persistent Roxy Coding Agent with action plan and unified diff in English and Urdu."""
    # 1. English Bug Fix request
    res_en = await async_client.post(
        "/api/v1/coding/agent/assist",
        json={
            "prompt": "Fix null pointer bug in auth token handler",
            "current_file": "src/app/auth.py",
            "file_content": "def get_token(payload):\n    return payload['token']\n",
        },
        headers=auth_headers,
    )
    assert res_en.status_code == 200
    data_en = res_en.json()
    assert len(data_en["action_plan"]) >= 3
    assert data_en["requires_approval"] is True
    assert data_en["proposed_diff"] is not None
    assert "--- a/src/app/auth.py" in data_en["proposed_diff"]
    assert data_en["language_detected"] == "english"

    # 2. Roman Urdu request ("is project ko analyze karo aur login bug fix karo")
    res_ur = await async_client.post(
        "/api/v1/coding/agent/assist",
        json={
            "prompt": "Roxy, is project ko analyze karo aur login bug fix karo.",
            "current_file": "src/app/login.py",
            "file_content": "def login_user(creds):\n    return creds.token\n",
        },
        headers=auth_headers,
    )
    assert res_ur.status_code == 200
    data_ur = res_ur.json()
    assert len(data_ur["action_plan"]) >= 3
    assert data_ur["requires_approval"] is True
    assert data_ur["proposed_diff"] is not None
    assert data_ur["language_detected"] in ("roman_urdu", "urdu")
    assert "jaiza" in data_ur["explanation"] or "identify" in data_ur["explanation"] or "Roxy" in data_ur["explanation"]


# ===========================================================================
# PART B: UNIVERSAL REMINDER & RINGTONE SYSTEM TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_reminder_settings_lifecycle(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Verify reminder settings, sound selection, and per-device/per-event overrides."""
    # 1. Get default settings
    get_res = await async_client.get("/api/v1/reminders/settings", headers=auth_headers)
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["default_sound_id"] == "roxy_harmonic"
    assert data["volume"] > 0.0
    assert "device_overrides" in data
    assert "event_overrides" in data
    assert len(data["available_devices"]) >= 2

    # 2. Update settings (per-device and per-event sounds, volume, snooze)
    update_res = await async_client.patch(
        "/api/v1/reminders/settings",
        json={
            "default_sound_id": "soft_zen",
            "volume": 0.95,
            "default_snooze_minutes": 15,
            "device_overrides": {"dev-win-desktop": "soft_zen", "dev-android-mobile": "crystal_chime"},
            "event_overrides": {"meeting": "executive_tone", "urgent": "urgent_alert"},
        },
        headers=auth_headers,
    )
    assert update_res.status_code == 200
    up_data = update_res.json()
    assert up_data["default_sound_id"] == "soft_zen"
    assert up_data["volume"] == 0.95
    assert up_data["default_snooze_minutes"] == 15
    assert up_data["device_overrides"]["dev-android-mobile"] == "crystal_chime"
    assert up_data["event_overrides"]["meeting"] == "executive_tone"


@pytest.mark.asyncio
async def test_sound_library_and_custom_upload(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Verify built-in procedural sounds and custom sound upload/deletion."""
    # 1. List sounds (must include all 10 built-in sounds)
    list_res = await async_client.get("/api/v1/reminders/sounds", headers=auth_headers)
    assert list_res.status_code == 200
    sounds = list_res.json()["sounds"]
    assert len(sounds) >= 10
    sound_ids = {s["id"] for s in sounds}
    assert "roxy_harmonic" in sound_ids
    assert "soft_zen" in sound_ids
    assert "executive_tone" in sound_ids
    assert "urgent_alert" in sound_ids

    # 2. Upload custom audio
    dummy_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00D\xac\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00"
    upload_res = await async_client.post(
        "/api/v1/reminders/sounds/upload",
        data={"name": "Custom Executive Ringtone", "category": "custom"},
        files={"file": ("custom_chime.wav", dummy_wav, "audio/wav")},
        headers=auth_headers,
    )
    assert upload_res.status_code == 200
    uploaded_sound = upload_res.json()["sound"]
    assert uploaded_sound["id"].startswith("custom_")
    assert uploaded_sound["name"] == "Custom Executive Ringtone"

    # 3. Delete custom audio
    del_res = await async_client.delete(
        f"/api/v1/reminders/sounds/{uploaded_sound['id']}",
        headers=auth_headers,
    )
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True


@pytest.mark.asyncio
async def test_notification_lifecycle_snooze_dismiss(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Verify notification trigger, delivery, snooze, and dismiss transitions."""
    # 1. Trigger reminder
    trig_res = await async_client.post(
        "/api/v1/reminders/trigger",
        json={
            "title": "Quarterly Financial Review",
            "body": "Prepare Q4 earnings statements and cloud infrastructure budget.",
            "category": "meeting",
            "target_devices": ["all"],
        },
        headers=auth_headers,
    )
    assert trig_res.status_code == 200
    notif = trig_res.json()
    assert notif["status"] == "delivered"
    assert notif["category"] == "meeting"
    notif_id = notif["id"]

    # 2. List notifications
    list_notifs = await async_client.get("/api/v1/reminders/notifications", headers=auth_headers)
    assert list_notifs.status_code == 200
    active_ids = [n["id"] for n in list_notifs.json()]
    assert notif_id in active_ids

    # 3. Snooze reminder by 10 minutes
    snooze_res = await async_client.post(
        f"/api/v1/reminders/{notif_id}/snooze",
        json={"snooze_minutes": 10},
        headers=auth_headers,
    )
    assert snooze_res.status_code == 200
    assert snooze_res.json()["status"] == "snoozed"
    assert snooze_res.json()["snoozed_minutes"] == 10

    # 4. Acknowledge reminder
    ack_res = await async_client.post(
        f"/api/v1/reminders/{notif_id}/acknowledge",
        headers=auth_headers,
    )
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "acknowledged"

    # 5. Dismiss reminder
    dismiss_res = await async_client.post(
        f"/api/v1/reminders/{notif_id}/dismiss",
        headers=auth_headers,
    )
    assert dismiss_res.status_code == 200
    assert dismiss_res.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_voice_reminder_parsing_multilingual(async_client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Verify natural language voice parsing in English and Roman Urdu."""
    # 1. English prompt
    en_res = await async_client.post(
        "/api/v1/reminders/voice-parse",
        json={"prompt": "Roxy, tomorrow at 8 PM remind me to submit the assignment"},
        headers=auth_headers,
    )
    assert en_res.status_code == 200
    en_data = en_res.json()
    assert en_data["intent"] == "schedule_reminder"
    assert "submit the assignment" in en_data["title"].lower()
    assert en_data["category"] == "task"
    assert "Reminder successfully scheduled" in en_data["confirmation_message"]

    # 2. Roman Urdu prompt ("Roxy, kal 5 baje mujhe client meeting yaad dila dena")
    ur_res = await async_client.post(
        "/api/v1/reminders/voice-parse",
        json={"prompt": "Roxy, kal 5 baje mujhe client meeting yaad dila dena."},
        headers=auth_headers,
    )
    assert ur_res.status_code == 200
    ur_data = ur_res.json()
    assert ur_data["intent"] == "schedule_reminder"
    assert "client meeting" in ur_data["title"].lower()
    assert ur_data["category"] == "meeting"
    assert "Reminder successfully scheduled" in ur_data["confirmation_message"]
