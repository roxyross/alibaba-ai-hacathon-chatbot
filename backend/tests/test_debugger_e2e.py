"""Interactive Sandboxed Python Debugger Verification Tests (Phase 5 Acceptance).

Tests:
- Launching debug session on workspace Python file
- Setting and pausing at breakpoints
- Local variable inspection at breakpoint
- Call stack unwinding across nested function calls
- Execution stepping (step_over, continue)
- Output capture and normal termination
- Cross-user session isolation and rejection
- Session termination and resource cleanup
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
from app.coding.debugger import PythonDebuggerManager
from app.main import app


@pytest.fixture
def test_user_a() -> User:
    return User(id="usr-dbg-alpha-001", email="dbg-alpha@roxy.ai")


@pytest.fixture
def test_user_b() -> User:
    return User(id="usr-dbg-beta-002", email="dbg-beta@roxy.ai")


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
    temp_dir = tempfile.mkdtemp(prefix="roxy_dbg_test_")
    fs = FileSystemService.get_instance()
    original_sandbox = fs.sandbox
    try:
        yield temp_dir
    finally:
        fs.sandbox = original_sandbox
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_debugger_e2e_breakpoints_stepping_and_variables(
    async_client: AsyncClient,
    auth_headers_a: dict[str, str],
    disposable_workspace: str,
) -> None:
    """End-to-end verification of real Python debugger: breakpoint pause, stack/var inspection, stepping, completion."""
    fs = FileSystemService.get_instance()
    fs.sandbox = FileSecuritySandbox(allowed_roots=[disposable_workspace])

    # 1. Create a sample Python file to debug
    sample_code = (
        "def compute_sum(a, b):\n"
        "    result = a + b\n"
        "    return result\n"
        "\n"
        "x = 15\n"
        "y = 25\n"
        "total = compute_sum(x, y)\n"
        "print(f'COMPUTED:{total}')\n"
    )
    script_path = Path(disposable_workspace) / "math_sample.py"
    script_path.write_text(sample_code, encoding="utf-8")

    # 2. Launch debug session with breakpoint on line 2 (inside compute_sum: result = a + b)
    start_resp = await async_client.post(
        "/api/v1/coding/debug/session/start",
        json={
            "file_path": "math_sample.py",
            "breakpoints": [{"line_number": 2, "enabled": True}],
        },
        headers=auth_headers_a,
    )
    assert start_resp.status_code == 200, start_resp.text
    session_id = start_resp.json()["session_id"]

    try:
        # Wait up to 2 seconds for execution to reach line 2
        paused = False
        state_data: dict[str, Any] = {}
        for _ in range(20):
            await asyncio.sleep(0.1)
            state_resp = await async_client.get(
                f"/api/v1/coding/debug/session/{session_id}/state",
                headers=auth_headers_a,
            )
            assert state_resp.status_code == 200
            state_data = state_resp.json()
            if state_data["state"] == "PAUSED_AT_BREAKPOINT":
                paused = True
                break

        assert paused, f"Debugger did not pause at breakpoint. Current state: {state_data}"
        assert state_data["current_line"] == 2
        # Verify local variables inside compute_sum
        assert state_data["local_variables"].get("a") == "15"
        assert state_data["local_variables"].get("b") == "25"
        # Verify call stack has compute_sum on top
        assert len(state_data["call_stack"]) >= 1
        assert state_data["call_stack"][0]["function"] == "compute_sum"

        # 3. Step over to line 3 (return result)
        step_resp = await async_client.post(
            f"/api/v1/coding/debug/session/{session_id}/action",
            json={"action": "step_over"},
            headers=auth_headers_a,
        )
        assert step_resp.status_code == 200
        step_data = step_resp.json()
        assert step_data["current_line"] == 3
        assert step_data["local_variables"].get("result") == "40"

        # 4. Continue execution to completion
        cont_resp = await async_client.post(
            f"/api/v1/coding/debug/session/{session_id}/action",
            json={"action": "continue"},
            headers=auth_headers_a,
        )
        assert cont_resp.status_code == 200

        # Wait for termination
        for _ in range(10):
            await asyncio.sleep(0.1)
            final_resp = await async_client.get(
                f"/api/v1/coding/debug/session/{session_id}/state",
                headers=auth_headers_a,
            )
            final_data = final_resp.json()
            if final_data["state"] == "TERMINATED":
                break

        assert final_data["state"] == "TERMINATED"
        assert final_data["exit_code"] == 0
        assert "COMPUTED:40" in final_data["stdout"]

    finally:
        await async_client.delete(
            f"/api/v1/coding/debug/session/{session_id}",
            headers=auth_headers_a,
        )


@pytest.mark.asyncio
async def test_debugger_multi_tenant_isolation(
    async_client: AsyncClient,
    auth_headers_a: dict[str, str],
    auth_headers_b: dict[str, str],
    disposable_workspace: str,
) -> None:
    """Verify that User B cannot inspect or step User A's debugger session."""
    fs = FileSystemService.get_instance()
    fs.sandbox = FileSecuritySandbox(allowed_roots=[disposable_workspace])

    script_path = Path(disposable_workspace) / "test_iso.py"
    script_path.write_text("v = 1\nfor i in range(100):\n    v += i\n", encoding="utf-8")

    start_resp = await async_client.post(
        "/api/v1/coding/debug/session/start",
        json={
            "file_path": "test_iso.py",
            "breakpoints": [{"line_number": 3, "enabled": True}],
        },
        headers=auth_headers_a,
    )
    assert start_resp.status_code == 200
    session_id = start_resp.json()["session_id"]

    try:
        # User B attempts to read User A's debug state
        b_state = await async_client.get(
            f"/api/v1/coding/debug/session/{session_id}/state",
            headers=auth_headers_b,
        )
        assert b_state.status_code == 403

        # User B attempts to step User A's session
        b_action = await async_client.post(
            f"/api/v1/coding/debug/session/{session_id}/action",
            json={"action": "step_over"},
            headers=auth_headers_b,
        )
        assert b_action.status_code == 403

        # User B attempts to stop User A's session
        b_stop = await async_client.delete(
            f"/api/v1/coding/debug/session/{session_id}",
            headers=auth_headers_b,
        )
        assert b_stop.status_code == 403
    finally:
        await async_client.delete(
            f"/api/v1/coding/debug/session/{session_id}",
            headers=auth_headers_a,
        )
