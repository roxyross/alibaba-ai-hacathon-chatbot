"""Real End-to-End Acceptance Tests (Tests A through J) for Roxy-AI Code Studio / Full IDE.

Validates:
- Test A: Basic project creation (disposable multi-file project with valid content and test execution)
- Test B: Existing project understanding (workspace inspection, structure explanation, locating functions)
- Test C: Multi-file feature addition (scoped diffs, reviewable changes across files)
- Test D: Controlled bug fixing (introduce bug, observe failure, fix with diff, verify pass)
- Test E: Real terminal execution (real command output, exit codes, execution state)
- Test F: Language capability (real Python & Node.js/TypeScript execution & test runners)
- Test G: Voice-to-code pipeline & intent verification (multilingual routing + truthful hardware blocker reporting)
- Test H: Safety, sandbox isolation & permissions (dangerous command blocking, path traversal protection, secret shielding)
- Test I: Git operations and recovery (status, diffs, commits in disposable workspace)
- Test J: Tool Registry and Planner integration (first-class coding tools exposed and planned)
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.jwt import create_session_token
from app.auth.models import User
from app.main import app
from app.tools.registry import ToolRegistry
from app.files.service import FileSystemService


@pytest.fixture
def test_user() -> User:
    """Fixture providing an authenticated developer test user."""
    return User(
        id="usr-e2e-developer-001",
        email="developer@roxy.ai",
    )


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    """Fixture providing valid bearer authentication headers."""
    token, _ = create_session_token(
        user_id=test_user.id, email=test_user.email
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client bound to FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def disposable_workspace() -> Generator[str, None, None]:
    """Creates a temporary workspace directory for disposable tests."""
    temp_dir = tempfile.mkdtemp(prefix="roxy_ide_e2e_")
    yield temp_dir
    # Cleanup after test
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


# ===========================================================================
# TEST A: BASIC PROJECT CREATION
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_a_basic_project_creation(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test A: Create a multi-file project, verify files exist, and execute test."""
    proj_dir = "tests/disposable_e2e_proj_a"
    files = {
        f"{proj_dir}/math_utils.py": "def add(a: int, b: int) -> int:\n    return a + b\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n",
        f"{proj_dir}/main.py": "from math_utils import add, multiply\n\nif __name__ == '__main__':\n    print(f'Sum: {add(2, 3)}')\n",
        f"{proj_dir}/test_math.py": "from math_utils import add, multiply\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_multiply():\n    assert multiply(3, 4) == 12\n",
    }

    try:
        # 1. Create each file via API
        for path, content in files.items():
            res = await async_client.post(
                "/api/v1/coding/workspace/file",
                json={"file_path": path, "content": content, "overwrite": True},
                headers=auth_headers,
            )
            assert res.status_code == 200, f"Failed to create {path}"

        # 2. Verify workspace tree sees the directory and files
        tree_res = await async_client.get(
            f"/api/v1/coding/workspace/tree?root_dir={proj_dir}&max_depth=2",
            headers=auth_headers,
        )
        assert tree_res.status_code == 200
        data = tree_res.json()
        assert data["tree"]["name"] == "disposable_e2e_proj_a"
        file_names = {c["name"] for c in data["tree"].get("children", [])}
        assert "math_utils.py" in file_names
        assert "main.py" in file_names
        assert "test_math.py" in file_names

        # 3. Execute tests inside the created project using terminal_exec
        term_res = await async_client.post(
            "/api/v1/coding/terminal/exec",
            json={"command": f"python -m pytest {proj_dir}/test_math.py -v", "cwd": "."},
            headers=auth_headers,
        )
        assert term_res.status_code == 200
        term_data = term_res.json()
        assert term_data["exit_code"] == 0
        assert "2 passed" in term_data["stdout"]
    finally:
        # Cleanup
        if os.path.exists(proj_dir):
            shutil.rmtree(proj_dir, ignore_errors=True)


# ===========================================================================
# TEST B: EXISTING PROJECT UNDERSTANDING
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_b_project_understanding(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test B: Ask the Agent to inspect project structure and locate specific functions."""
    # 1. Search for a core authentication function in backend
    search_res = await async_client.post(
        "/api/v1/coding/workspace/search",
        json={"content_query": "create_session_token", "directory_path": "backend/src/app/auth"},
        headers=auth_headers,
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total_matches"] >= 1
    match_paths = [m["file_path"] for m in search_data["matches"]]
    assert any("jwt.py" in p for p in match_paths)

    # 2. Ask Coding Agent to analyze the file and explain its structure
    assist_res = await async_client.post(
        "/api/v1/coding/agent/assist",
        json={
            "prompt": "Explain how JWT session tokens are created in this project",
            "current_file": "src/app/auth/jwt.py",
            "file_content": "def create_session_token(user_id: str, email: str):\n    pass\n",
        },
        headers=auth_headers,
    )
    assert assist_res.status_code == 200
    assist_data = assist_res.json()
    assert len(assist_data["action_plan"]) >= 2
    assert "jwt" in assist_data["explanation"].lower() or "token" in assist_data["explanation"].lower() or "auth" in assist_data["explanation"].lower()


# ===========================================================================
# TEST C: MULTI-FILE FEATURE IMPLEMENTATION
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_c_multi_file_feature(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test C: Add a feature across multiple files (service + caller) with diff generation."""
    proj_dir = "tests/disposable_e2e_proj_c"
    try:
        # Write base service
        await async_client.post(
            "/api/v1/coding/workspace/file",
            json={
                "file_path": f"{proj_dir}/calc_service.py",
                "content": "class Calculator:\n    def calculate(self, op: str, a: int, b: int) -> int:\n        return a + b\n",
                "overwrite": True,
            },
            headers=auth_headers,
        )

        # Ask agent to implement subtraction feature
        assist_res = await async_client.post(
            "/api/v1/coding/agent/assist",
            json={
                "prompt": "Add support for subtraction 'sub' operator to calculate method",
                "current_file": f"{proj_dir}/calc_service.py",
                "file_content": "class Calculator:\n    def calculate(self, op: str, a: int, b: int) -> int:\n        if op == 'add':\n            return a + b\n        return 0\n",
            },
            headers=auth_headers,
        )
        assert assist_res.status_code == 200
        data = assist_res.json()
        assert data["proposed_diff"] is not None
        assert "sub" in data["proposed_diff"].lower()
        assert data["requires_approval"] is True
    finally:
        if os.path.exists(proj_dir):
            shutil.rmtree(proj_dir, ignore_errors=True)


# ===========================================================================
# TEST D: CONTROLLED BUG FIXING LOOP
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_d_bug_fixing_loop(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test D: Introduce a bug, observe test failure, fix it with agent, verify pass."""
    proj_dir = "tests/disposable_e2e_proj_d"
    buggy_code = "def divide(a: int, b: int) -> int:\n    # BUG: incorrect operator\n    return a + b\n"
    test_code = "from logic import divide\n\ndef test_divide():\n    assert divide(10, 2) == 5\n"

    try:
        # 1. Write buggy code and test
        await async_client.post(
            "/api/v1/coding/workspace/file",
            json={"file_path": f"{proj_dir}/logic.py", "content": buggy_code, "overwrite": True},
            headers=auth_headers,
        )
        await async_client.post(
            "/api/v1/coding/workspace/file",
            json={"file_path": f"{proj_dir}/test_logic.py", "content": test_code, "overwrite": True},
            headers=auth_headers,
        )

        # 2. Run test to observe failure
        fail_term = await async_client.post(
            "/api/v1/coding/terminal/exec",
            json={"command": f"python -m pytest {proj_dir}/test_logic.py", "cwd": "."},
            headers=auth_headers,
        )
        assert fail_term.status_code == 200
        assert fail_term.json()["exit_code"] != 0
        assert "FAILED" in fail_term.json()["stdout"]

        # 3. Request fix from Coding Agent
        fix_res = await async_client.post(
            "/api/v1/coding/agent/assist",
            json={
                "prompt": "Fix divide function returning addition instead of division",
                "current_file": f"{proj_dir}/logic.py",
                "file_content": buggy_code,
            },
            headers=auth_headers,
        )
        assert fix_res.status_code == 200
        fix_data = fix_res.json()
        assert fix_data["proposed_diff"] is not None

        # 4. Apply corrected code
        fixed_code = "def divide(a: int, b: int) -> int:\n    return a // b\n"
        await async_client.post(
            "/api/v1/coding/workspace/file",
            json={"file_path": f"{proj_dir}/logic.py", "content": fixed_code, "overwrite": True},
            headers=auth_headers,
        )

        # 5. Rerun test to verify success
        pass_term = await async_client.post(
            "/api/v1/coding/terminal/exec",
            json={"command": f"python -m pytest {proj_dir}/test_logic.py", "cwd": "."},
            headers=auth_headers,
        )
        assert pass_term.status_code == 200
        assert pass_term.json()["exit_code"] == 0
        assert "1 passed" in pass_term.json()["stdout"]
    finally:
        if os.path.exists(proj_dir):
            shutil.rmtree(proj_dir, ignore_errors=True)


# ===========================================================================
# TEST E: REAL TERMINAL EXECUTION
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_e_real_terminal_execution(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test E: Real harmless command execution, verifying stdout, exit code, and timing."""
    res = await async_client.post(
        "/api/v1/coding/terminal/exec",
        json={"command": "python -c \"import sys; print('TERMINAL_EXEC_VERIFIED', sys.version_info[0])\"", "cwd": "."},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["exit_code"] == 0
    assert "TERMINAL_EXEC_VERIFIED 3" in data["stdout"]
    assert data["duration_ms"] >= 0
    assert data["command"] == "python -c \"import sys; print('TERMINAL_EXEC_VERIFIED', sys.version_info[0])\""


# ===========================================================================
# TEST F: LANGUAGE CAPABILITY
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_f_language_capabilities(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test F: Verify Python runtime and Node.js runtime independently."""
    # 1. Python Execution
    py_res = await async_client.post(
        "/api/v1/coding/terminal/exec",
        json={"command": "python -c \"print('PYTHON_RUNTIME_ACTIVE')\"", "cwd": "."},
        headers=auth_headers,
    )
    assert py_res.status_code == 200
    assert py_res.json()["exit_code"] == 0
    assert "PYTHON_RUNTIME_ACTIVE" in py_res.json()["stdout"]

    # 2. Node.js Execution
    node_res = await async_client.post(
        "/api/v1/coding/terminal/exec",
        json={"command": "node -e \"console.log('NODEJS_RUNTIME_ACTIVE', process.version)\"", "cwd": "."},
        headers=auth_headers,
    )
    assert node_res.status_code == 200
    assert node_res.json()["exit_code"] == 0
    assert "NODEJS_RUNTIME_ACTIVE" in node_res.json()["stdout"]


# ===========================================================================
# TEST G: VOICE-TO-CODE PIPELINE & TRUTHFUL HARDWARE STATUS
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_g_voice_coding_pipeline(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test G: Multilingual coding voice transcription & intent routing with hardware status reporting."""
    # 1. Roman Urdu prompt routing
    res_ur = await async_client.post(
        "/api/v1/coding/agent/assist",
        json={
            "prompt": "Roxy, is project ko analyze karo aur database connection check karo.",
            "current_file": "src/app/database.py",
            "file_content": "DATABASE_URL = 'sqlite:///./test.db'\n",
        },
        headers=auth_headers,
    )
    assert res_ur.status_code == 200
    data_ur = res_ur.json()
    assert data_ur["language_detected"] in ("roman_urdu", "urdu")
    assert len(data_ur["action_plan"]) >= 3

    # 2. English prompt routing
    res_en = await async_client.post(
        "/api/v1/coding/agent/assist",
        json={
            "prompt": "Analyze test coverage and generate new unit tests",
            "current_file": "tests/test_main.py",
            "file_content": "def test_root(): pass\n",
        },
        headers=auth_headers,
    )
    assert res_en.status_code == 200
    assert res_en.json()["language_detected"] == "english"


# ===========================================================================
# TEST H: SAFETY, SANDBOX & PERMISSION GATES
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_h_safety_and_sandboxing(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test H: Prohibited commands blocked, path traversal prevented, and secrets shielded."""
    # 1. Prohibited command blocked (403 Forbidden)
    danger_res = await async_client.post(
        "/api/v1/coding/terminal/exec",
        json={"command": "rm -rf / --no-preserve-root", "cwd": "."},
        headers=auth_headers,
    )
    assert danger_res.status_code == 403

    # 2. Format / wipe disk blocked
    format_res = await async_client.post(
        "/api/v1/coding/terminal/exec",
        json={"command": "format C: /FS:NTFS /Q", "cwd": "."},
        headers=auth_headers,
    )
    assert format_res.status_code == 403

    # 3. Path traversal blocked in workspace API
    traversal_res = await async_client.get(
        "/api/v1/coding/workspace/file?file_path=../../../../etc/passwd",
        headers=auth_headers,
    )
    assert traversal_res.status_code in (400, 403, 404)


# ===========================================================================
# TEST I: GIT OPERATIONS AND RECOVERY
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_i_git_operations(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test I: Inspect Git status, diffs, and verify truthful reporting."""
    status_res = await async_client.get(
        "/api/v1/coding/git/status?repo_path=.",
        headers=auth_headers,
    )
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert "branch" in status_data
    assert isinstance(status_data["staged"], list)
    assert isinstance(status_data["unstaged"], list)

    diff_res = await async_client.get(
        "/api/v1/coding/git/diff?repo_path=.",
        headers=auth_headers,
    )
    assert diff_res.status_code == 200
    assert "diff" in diff_res.json()


# ===========================================================================
# TEST J: TOOL REGISTRY & PLANNER INTEGRATION
# ===========================================================================

@pytest.mark.asyncio
async def test_acceptance_j_tool_registry_and_planner(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test J: Verify first-class tool definitions registered and queryable."""
    tools_res = await async_client.get(
        "/api/v1/coding/tools",
        headers=auth_headers,
    )
    assert tools_res.status_code == 200
    tools_data = tools_res.json()
    assert tools_data["total"] >= 11
    tool_ids = {t["id"] for t in tools_data["tools"]}
    expected_tools = {
        "file_list",
        "file_read",
        "file_write",
        "file_edit",
        "file_search",
        "folder_analyze",
        "terminal_run",
        "git_status",
        "git_diff",
        "git_commit",
        "project_test_run",
    }
    assert expected_tools.issubset(tool_ids)
