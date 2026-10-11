"""Tests for Phase 4: Persistent Cowork and Open Work Storage across simulated restarts."""

from __future__ import annotations

import os
import shutil
import tempfile
import pytest

from app.artifacts.repository import ArtifactRepository, clear_in_memory_stores
from app.artifacts.schemas import ArtifactType
from app.open_work.service import OpenWorkAgentService, _get_open_work_storage_path
from app.open_work.schemas import CreateOpenWorkTaskRequest, OpenWorkTaskStatus


@pytest.fixture(autouse=True)
def setup_isolated_storage(monkeypatch):
    """Set up an isolated temporary storage directory for testing."""
    temp_dir = tempfile.mkdtemp(prefix="roxy_storage_test_")
    monkeypatch.setenv("ROXY_STORAGE_DIR", temp_dir)
    clear_in_memory_stores(clear_disk=True)
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_cowork_artifact_restart_persistence():
    """Verify that Cowork artifacts and version history survive a process restart."""
    # 1. First process life: Create artifact and add version
    repo1 = ArtifactRepository()
    created = await repo1.create_artifact(
        user_id="user_alice",
        title="Design System Doc",
        content="# Initial System Architecture",
        artifact_type=ArtifactType.MARKDOWN,
    )
    art_id = created["id"]
    assert created["current_version"] == 1

    # Update artifact to create version 2
    updated = await repo1.update_artifact(
        user_id="user_alice",
        artifact_id=art_id,
        content="# Initial System Architecture\n\n## Section 2: Components",
        change_summary="Added Section 2",
    )
    assert updated is not None
    assert updated["current_version"] == 2

    # 2. Simulate process shutdown and restart by clearing RAM cache and loading new instance
    clear_in_memory_stores(clear_disk=False)
    repo2 = ArtifactRepository()

    # Verify artifact survived
    loaded = await repo2.get_artifact(user_id="user_alice", artifact_id=art_id)
    assert loaded is not None
    assert loaded["id"] == art_id
    assert loaded["title"] == "Design System Doc"
    assert loaded["current_version"] == 2
    assert "Section 2: Components" in loaded["content"]

    # Verify version history survived
    assert len(loaded["versions"]) == 2
    assert loaded["versions"][0]["version_number"] == 1
    assert loaded["versions"][1]["version_number"] == 2

    # Verify user ownership isolation (returns None for unauthorized user)
    unauthorized = await repo2.get_artifact(user_id="user_bob_unauthorized", artifact_id=art_id)
    assert unauthorized is None


@pytest.mark.asyncio
async def test_open_work_task_restart_persistence():
    """Verify that Open Work tasks and checkpoints survive process restart."""
    # 1. Process life 1: Create an Open Work task
    OpenWorkAgentService._instance = None
    service1 = OpenWorkAgentService()
    task = await service1.create_task(
        user_id="user_alice",
        request=CreateOpenWorkTaskRequest(
            title="Refactor Auth Subsystem",
            objective="Analyze project folder and find bug",
            auto_start=False,
            context={"folder_path": "backend/src/app/auth"},
        ),
    )
    task_id = task.id
    assert task.status == OpenWorkTaskStatus.PENDING
    assert len(task.subtasks) >= 2

    # Simulate subtask progress manually and save
    task.current_subtask_index = 1
    task.progress_percent = 50.0
    task.checkpoint["last_completed_index"] = 0
    task.checkpoint["step_0_output"] = {"status": "ok", "files_found": 5}
    from app.open_work.service import _save_tasks_to_disk
    _save_tasks_to_disk(service1._tasks)

    # 2. Simulate process shutdown and restart: instantiate a fresh OpenWorkAgentService
    OpenWorkAgentService._instance = None
    service2 = OpenWorkAgentService()

    # Verify task reloaded from disk with checkpoint intact
    reloaded_task = service2.get_task(task_id, user_id="user_alice")
    assert reloaded_task.id == task_id
    assert reloaded_task.title == "Refactor Auth Subsystem"
    assert reloaded_task.current_subtask_index == 1
    assert reloaded_task.progress_percent == 50.0
    assert reloaded_task.checkpoint["last_completed_index"] == 0
    assert reloaded_task.checkpoint["step_0_output"]["files_found"] == 5

    # Verify user ownership isolation
    with pytest.raises(PermissionError):
        service2.get_task(task_id, user_id="user_intruder")
