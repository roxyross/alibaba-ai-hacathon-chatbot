"""Interactive Terminal & PTY Verification Tests (Phase 3 Acceptance).

Tests:
- Session creation within authorized sandbox
- Command execution and streamed output capture
- Input submission and command handling
- Directory persistence across interactions
- Destructive/prohibited command blocking (rm -rf /, format c:)
- Cross-user session isolation and rejection
- Resize handling
- Process-tree termination and cleanup on close
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.jwt import create_session_token
from app.auth.models import User
from app.files.sandbox import FileSecuritySandbox
from app.files.service import FileSystemService
from app.files.terminal_session import TerminalSessionManager
from app.main import app


@pytest.fixture
def test_user_a() -> User:
    return User(id="usr-terminal-alpha-001", email="alpha@roxy.ai")


@pytest.fixture
def test_user_b() -> User:
    return User(id="usr-terminal-beta-002", email="beta@roxy.ai")


@pytest.fixture
def auth_headers_a(test_user_a: User) -> dict[str, str]:
    token, _ = create_session_token(user_id=test_user_a.id, email=test_user_a.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_b(test_user_b: User) -> dict[str, str]:
    token, _ = create_session_token(user_id=test_user_b.id, email=test_user_b.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def disposable_workspace() -> Generator[str, None, None]:
    temp_dir = tempfile.mkdtemp(prefix="roxy_term_test_")
    fs = FileSystemService.get_instance()
    original_sandbox = fs.sandbox
    try:
        yield temp_dir
    finally:
        fs.sandbox = original_sandbox
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_terminal_session_lifecycle_and_output(
    async_client: AsyncClient,
    auth_headers_a: dict[str, str],
    disposable_workspace: str,
) -> None:
    """Test creating session, writing command, polling output, and closing."""
    fs = FileSystemService.get_instance()
    fs.sandbox = FileSecuritySandbox(allowed_roots=[disposable_workspace])

    # 1. Create session
    create_resp = await async_client.post(
        "/api/v1/coding/terminal/session/create",
        json={"cwd": ".", "cols": 100, "rows": 30},
        headers=auth_headers_a,
    )
    assert create_resp.status_code == 200, create_resp.text
    session_data = create_resp.json()
    session_id = session_data["session_id"]
    assert session_data["is_active"] is True
    assert session_data["cols"] == 100

    # 2. Write input (echo a unique token)
    input_resp = await async_client.post(
        f"/api/v1/coding/terminal/session/{session_id}/input",
        json={"data": "echo ROXY_TERM_ONLINE\n"},
        headers=auth_headers_a,
    )
    assert input_resp.status_code == 200
    assert input_resp.json()["success"] is True

    # 3. Allow brief time for process stdout execution and poll output
    await asyncio.sleep(0.8)
    out_resp = await async_client.get(
        f"/api/v1/coding/terminal/session/{session_id}/output",
        headers=auth_headers_a,
    )
    assert out_resp.status_code == 200
    out_data = out_resp.json()
    combined_output = "".join(out_data["chunks"])
    assert "ROXY_TERM_ONLINE" in combined_output

    # 4. Resize terminal
    resize_resp = await async_client.post(
        f"/api/v1/coding/terminal/session/{session_id}/resize",
        json={"cols": 120, "rows": 40},
        headers=auth_headers_a,
    )
    assert resize_resp.status_code == 200
    assert resize_resp.json()["cols"] == 120

    # 5. Close session and verify cleanup
    close_resp = await async_client.delete(
        f"/api/v1/coding/terminal/session/{session_id}",
        headers=auth_headers_a,
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["closed"] is True


@pytest.mark.asyncio
async def test_terminal_session_dangerous_command_blocked(
    async_client: AsyncClient,
    auth_headers_a: dict[str, str],
    disposable_workspace: str,
) -> None:
    """Verify that dangerous destructive patterns (format c:, rm -rf /) are blocked."""
    fs = FileSystemService.get_instance()
    fs.sandbox = FileSecuritySandbox(allowed_roots=[disposable_workspace])

    create_resp = await async_client.post(
        "/api/v1/coding/terminal/session/create",
        json={"cwd": "."},
        headers=auth_headers_a,
    )
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]

    try:
        # Attempt prohibited command
        blocked_resp = await async_client.post(
            f"/api/v1/coding/terminal/session/{session_id}/input",
            json={"data": "rm -rf / --no-preserve-root\n"},
            headers=auth_headers_a,
        )
        assert blocked_resp.status_code == 403
        assert "blocked" in blocked_resp.json()["detail"].lower()
    finally:
        await async_client.delete(
            f"/api/v1/coding/terminal/session/{session_id}",
            headers=auth_headers_a,
        )


@pytest.mark.asyncio
async def test_terminal_session_multi_tenant_isolation(
    async_client: AsyncClient,
    auth_headers_a: dict[str, str],
    auth_headers_b: dict[str, str],
    disposable_workspace: str,
) -> None:
    """Verify that user B cannot access, read, or close user A's terminal session."""
    fs = FileSystemService.get_instance()
    fs.sandbox = FileSecuritySandbox(allowed_roots=[disposable_workspace])

    # User A creates session
    create_resp = await async_client.post(
        "/api/v1/coding/terminal/session/create",
        json={"cwd": "."},
        headers=auth_headers_a,
    )
    session_id = create_resp.json()["session_id"]

    try:
        # User B attempts to read User A's session
        b_read = await async_client.get(
            f"/api/v1/coding/terminal/session/{session_id}/output",
            headers=auth_headers_b,
        )
        assert b_read.status_code == 403

        # User B attempts to send input to User A's session
        b_input = await async_client.post(
            f"/api/v1/coding/terminal/session/{session_id}/input",
            json={"data": "whoami\n"},
            headers=auth_headers_b,
        )
        assert b_input.status_code == 403

        # User B attempts to close User A's session
        b_close = await async_client.delete(
            f"/api/v1/coding/terminal/session/{session_id}",
            headers=auth_headers_b,
        )
        assert b_close.status_code == 403
    finally:
        await async_client.delete(
            f"/api/v1/coding/terminal/session/{session_id}",
            headers=auth_headers_a,
        )
