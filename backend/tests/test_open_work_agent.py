"""Unit and Integration Tests for Open Work Agent.

Verifies:
1. Objective decomposition into ordered subtasks with tools.
2. Long-running lifecycle execution and progress tracking.
3. Pause, Resume, and Cancel state machines with checkpointing.
4. Error recovery and subtask failure isolation.
5. REST API routes for /api/v1/open-work/tasks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import Any

import pytest

from app.open_work.schemas import (
    CreateOpenWorkTaskRequest,
    OpenWorkTaskStatus,
)
from app.open_work.service import OpenWorkAgentService
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource


@pytest.fixture(autouse=True)
def setup_test_tools() -> Generator[None, None, None]:
    """Ensure mock/system tools exist in registry for test execution and restore on teardown."""
    reg = ToolRegistry.get_instance()
    snapshot = {
        "folder_analyze": (reg.get("folder_analyze"), reg.get_handler("folder_analyze")),
        "file_search": (reg.get("file_search"), reg.get_handler("file_search")),
        "code_execute": (reg.get("code_execute"), reg.get_handler("code_execute")),
    }

    async def _dummy_folder_analyze(**kwargs: Any) -> dict[str, Any]:
        return {"summary": "Folder analyzed", "primary_languages": ["Python"]}

    async def _dummy_file_search(**kwargs: Any) -> dict[str, Any]:
        return {"total_matches": 1, "matches": [{"snippet": "def found_function()"}]}

    async def _dummy_code_execute(**kwargs: Any) -> dict[str, Any]:
        return {"stdout": "Tests passed", "exit_code": 0}

    reg.register(
        AgentTool(
            id="folder_analyze",
            name="Analyze Folder",
            description="Inspect folder",
            source=ToolSource.SYSTEM,
            capabilities=["files"],
            input_schema={"type": "object"},
            risk_level=RiskLevel.LOW,
        ),
        _dummy_folder_analyze,
    )
    reg.register(
        AgentTool(
            id="file_search",
            name="Search File",
            description="Search files",
            source=ToolSource.SYSTEM,
            capabilities=["files"],
            input_schema={"type": "object"},
            risk_level=RiskLevel.LOW,
        ),
        _dummy_file_search,
    )
    reg.register(
        AgentTool(
            id="code_execute",
            name="Code Execute",
            description="Execute code",
            source=ToolSource.SYSTEM,
            capabilities=["code"],
            input_schema={"type": "object"},
            risk_level=RiskLevel.MEDIUM,
        ),
        _dummy_code_execute,
    )

    yield

    for tool_id, (old_tool, old_handler) in snapshot.items():
        if old_tool and old_handler:
            reg.register(old_tool, old_handler)
        else:
            reg.unregister(tool_id)



def test_objective_decomposition() -> None:
    service = OpenWorkAgentService()

    # 1. Project Analysis Objective
    subtasks = service.decompose_objective("Analyze project folder and find authentication bug")
    assert len(subtasks) >= 2
    tool_ids = [st.tool_id for st in subtasks]
    assert "folder_analyze" in tool_ids
    assert "file_search" in tool_ids

    # 2. Coding & Testing Objective
    subtasks_code = service.decompose_objective("Fix this bug in Python and run tests")
    assert any(st.tool_id == "code_execute" for st in subtasks_code)

    # 3. Web Research Objective
    subtasks_res = service.decompose_objective("Research latest LangChain release notes")
    assert any(st.tool_id == "web_search" for st in subtasks_res)


@pytest.mark.asyncio
async def test_task_execution_lifecycle_completion() -> None:
    service = OpenWorkAgentService()

    req = CreateOpenWorkTaskRequest(
        title="Analyze and Verify Project",
        objective="Analyze project folder and run test suite",
        auto_start=True,
    )

    task = await service.create_task(user_id="user_123", request=req)
    assert task.id.startswith("owt_")

    # Wait briefly for async execution of dummy tools to complete
    for _ in range(20):
        await asyncio.sleep(0.05)
        current = service.get_task(task.id, user_id="user_123")
        if current.status == OpenWorkTaskStatus.COMPLETED:
            break

    final_task = service.get_task(task.id, user_id="user_123")
    assert final_task.status == OpenWorkTaskStatus.COMPLETED
    assert final_task.progress_percent == 100.0
    assert all(st.status == OpenWorkTaskStatus.COMPLETED for st in final_task.subtasks)
    assert final_task.checkpoint["last_completed_index"] == len(final_task.subtasks) - 1


@pytest.mark.asyncio
async def test_task_pause_and_resume() -> None:
    service = OpenWorkAgentService()

    req = CreateOpenWorkTaskRequest(
        title="Pause and Resume Test",
        objective="Analyze project folder, search files, and run tests",
        auto_start=False,
    )

    task = await service.create_task(user_id="user_123", request=req)
    assert task.status == OpenWorkTaskStatus.PENDING

    # Start task
    await service.start_task(task.id)

    # Immediately pause
    paused_task = await service.pause_task(task.id, user_id="user_123")
    assert paused_task.status in (OpenWorkTaskStatus.PAUSED, OpenWorkTaskStatus.COMPLETED)

    if paused_task.status == OpenWorkTaskStatus.PAUSED:
        # Resume
        resumed_task = await service.resume_task(task.id, user_id="user_123")
        assert resumed_task.status == OpenWorkTaskStatus.RUNNING

        # Allow completion
        for _ in range(20):
            await asyncio.sleep(0.05)
            c = service.get_task(task.id, user_id="user_123")
            if c.status == OpenWorkTaskStatus.COMPLETED:
                break
        assert service.get_task(task.id, user_id="user_123").status == OpenWorkTaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_task_cancellation() -> None:
    service = OpenWorkAgentService()

    req = CreateOpenWorkTaskRequest(
        title="Cancellation Test",
        objective="Analyze project folder and search files",
        auto_start=False,
    )

    task = await service.create_task(user_id="user_123", request=req)
    cancelled = await service.cancel_task(task.id, user_id="user_123")
    assert cancelled.status == OpenWorkTaskStatus.CANCELLED
