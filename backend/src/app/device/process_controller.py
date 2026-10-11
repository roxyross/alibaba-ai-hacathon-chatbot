"""Universal Local Application Launcher & Process Lifecycle Controller.

Under the Zero Simulation doctrine:
1. Cross-platform safe process launching with execution flags, working directories, and URI scheme handling.
2. Hardened execution: zero `shell=True`, parameter validation, injection prevention, and path traversal checks.
3. Process lifecycle management: graceful termination, tree-wide child process termination, and forceful kill.
4. Critical system process protection: shielding system-critical processes (PID <= 4, System, csrss, init, etc.).
5. Process window focus activation via native OS windowing APIs (Win32, AppleScript, wmctrl).
6. Live process inspection and telemetry retrieval (PID, CPU, Memory RSS/VMS, child trees) via psutil.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path

import psutil  # type: ignore[import-untyped]
import structlog

from app.device.schemas import (
    ProcessDetailsModel,
    ProcessInfoModel,
    ProcessLaunchResultModel,
    ProcessTerminationResultModel,
)

log = structlog.get_logger()


# -----------------------------------------------------------------------------
# Protected System Processes Shield
# -----------------------------------------------------------------------------

CRITICAL_SYSTEM_PROCESSES: set[str] = {
    # Windows
    "system",
    "system idle process",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "winlogon.exe",
    "dwm.exe",
    # macOS
    "launchd",
    "kernel_task",
    "loginwindow",
    "windowserver",
    "distnoted",
    # Linux
    "init",
    "systemd",
    "kthreadd",
    "ksoftirqd",
    "rcu_sched",
}

DANGEROUS_SHELL_PATTERNS = re.compile(r"[;&|`$><\n\r\0]")


# -----------------------------------------------------------------------------
# Universal Process Lifecycle Controller
# -----------------------------------------------------------------------------

class ProcessLifecycleController:
    """Production-grade universal application launcher and process lifecycle controller."""

    @classmethod
    def sanitize_command_target(cls, target: str) -> None:
        """Validate target against command injection and path traversal."""
        if not target or not target.strip():
            raise ValueError("Target executable or application name cannot be empty.")

        if DANGEROUS_SHELL_PATTERNS.search(target):
            raise ValueError(f"Dangerous characters detected in target: '{target}'. Execution blocked.")

        if ".." in target.replace("\\", "/").split("/"):
            raise ValueError(f"Directory traversal detected in target: '{target}'. Execution blocked.")

    @classmethod
    def is_critical_process(cls, proc: psutil.Process) -> bool:
        """Verify if process is a protected operating system component."""
        if proc.pid <= 4:
            return True

        try:
            name = proc.name().lower()
            if name in CRITICAL_SYSTEM_PROCESSES:
                return True
            for crit in CRITICAL_SYSTEM_PROCESSES:
                if name == crit or name == f"{crit}.exe":
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

        return False

    @classmethod
    def resolve_executable(cls, target: str) -> str | None:
        """Resolve executable path across PATH and filesystem."""
        # 1. Direct path check
        p = Path(target)
        if p.exists() and not p.is_dir():
            return str(p.resolve())

        # 2. PATH resolution
        which_path = shutil.which(target)
        if which_path:
            return which_path

        # 3. Windows .exe suffix fallback
        if platform.system().lower() == "windows" and not target.lower().endswith(".exe"):
            which_exe = shutil.which(f"{target}.exe")
            if which_exe:
                return which_exe

        return None

    @classmethod
    def launch(
        cls,
        target: str,
        arguments: list[str] | None = None,
        working_directory: str | None = None,
        environment: dict[str, str] | None = None,
        wait_for_window: bool = False,
        window_timeout_sec: float = 5.0,
    ) -> ProcessLaunchResultModel:
        """Launch an application, binary, or URI scheme securely across platforms."""
        cls.sanitize_command_target(target)
        args = arguments or []
        for arg in args:
            if "\0" in arg:
                raise ValueError("Null byte detected in argument.")

        if working_directory:
            wd_p = Path(working_directory)
            if not wd_p.exists() or not wd_p.is_dir():
                raise ValueError(f"Working directory does not exist or is not a directory: '{working_directory}'.")
            if ".." in working_directory.replace("\\", "/").split("/"):
                raise ValueError(f"Directory traversal in working directory: '{working_directory}'.")

        env = os.environ.copy()
        if environment:
            env.update(environment)

        start_time = time.perf_counter()
        os_name = platform.system().lower()

        # Handle URI scheme launch (e.g. 'slack://', 'https://', 'vscode://')
        if "://" in target:
            try:
                if os_name == "windows" and hasattr(os, "startfile"):
                    os.startfile(target)  # ShellExecuteW directly without command shell
                elif os_name == "darwin":
                    subprocess.Popen(["open", target], shell=False, env=env)
                else:
                    subprocess.Popen(["xdg-open", target], shell=False, env=env)

                dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return ProcessLaunchResultModel(
                    success=True,
                    target=target,
                    executable_path=target,
                    duration_ms=dur_ms,
                )
            except Exception as exc:
                dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return ProcessLaunchResultModel(
                    success=False,
                    target=target,
                    error=str(exc),
                    duration_ms=dur_ms,
                )

        resolved = cls.resolve_executable(target)

        # macOS .app bundle handling
        if not resolved and os_name == "darwin":
            candidates = [
                Path(f"/Applications/{target}.app"),
                Path(f"/System/Applications/{target}.app"),
                Path.home() / f"Applications/{target}.app",
            ]
            for cand in candidates:
                if cand.exists():
                    cmd = ["open", "-a", str(cand)]
                    if args:
                        cmd.extend(["--args"] + args)
                    proc = subprocess.Popen(cmd, cwd=working_directory, env=env, shell=False)
                    dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    return ProcessLaunchResultModel(
                        success=True,
                        pid=proc.pid,
                        target=target,
                        executable_path=str(cand),
                        duration_ms=dur_ms,
                    )

        # Windows startfile fallback for registered system shortcuts (.lnk)
        if (
            not resolved
            and os_name == "windows"
            and hasattr(os, "startfile")
            and Path(target).suffix.lower() == ".lnk"
            and Path(target).exists()
        ):
            try:
                os.startfile(target)
                dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return ProcessLaunchResultModel(
                    success=True,
                    target=target,
                    executable_path=target,
                    duration_ms=dur_ms,
                )
            except Exception as exc:
                dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return ProcessLaunchResultModel(
                    success=False,
                    target=target,
                    error=str(exc),
                    duration_ms=dur_ms,
                )

        if not resolved:
            dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return ProcessLaunchResultModel(
                success=False,
                target=target,
                error=f"Executable or application '{target}' not found on system PATH.",
                duration_ms=dur_ms,
            )

        cmd = [resolved] + args
        try:
            if os_name == "windows":
                proc = subprocess.Popen(
                    cmd,
                    cwd=working_directory,
                    env=env,
                    shell=False,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                proc = subprocess.Popen(cmd, cwd=working_directory, env=env, shell=False)

            pid = proc.pid
            window_detected = False
            window_title: str | None = None

            if wait_for_window:
                from app.device.desktop_automation import DesktopAutomationEngine
                deadline = time.time() + window_timeout_sec
                while time.time() < deadline:
                    state = DesktopAutomationEngine.read_window_state(window_target=pid)
                    if state.exists:
                        window_detected = True
                        window_title = state.title
                        break
                    time.sleep(0.25)

            dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return ProcessLaunchResultModel(
                success=True,
                pid=pid,
                target=target,
                executable_path=resolved,
                window_detected=window_detected,
                window_title=window_title,
                duration_ms=dur_ms,
            )
        except Exception as exc:
            dur_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return ProcessLaunchResultModel(
                success=False,
                target=target,
                executable_path=resolved,
                error=str(exc),
                duration_ms=dur_ms,
            )

    @classmethod
    def terminate(
        cls,
        target: int | str,
        force: bool = False,
        timeout_sec: float = 5.0,
        terminate_children: bool = True,
    ) -> ProcessTerminationResultModel:
        """Gracefully or forcibly terminate a process and its child process tree."""
        target_str = str(target)
        target_pids: list[int] = []

        # 1. Resolve target PID(s)
        if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
            pid = int(target)
            if not psutil.pid_exists(pid):
                return ProcessTerminationResultModel(
                    success=True,
                    target=target_str,
                    already_dead=True,
                )
            target_pids.append(pid)
        else:
            name_query = str(target).lower().strip()
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    p_name = p.name().lower()
                    if p_name == name_query or p_name == f"{name_query}.exe":
                        target_pids.append(p.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        if not target_pids:
            return ProcessTerminationResultModel(
                success=True,
                target=target_str,
                already_dead=True,
            )

        terminated: list[int] = []
        errors: list[str] = []

        for pid in target_pids:
            try:
                proc = psutil.Process(pid)
            except psutil.NoSuchProcess:
                terminated.append(pid)
                continue

            # 2. Critical system process protection check
            if cls.is_critical_process(proc):
                err = f"Security Violation: Process '{proc.name()}' (PID {pid}) is a critical operating system process. Termination blocked."
                log.error("process_controller.critical_process_shield_triggered", pid=pid, name=proc.name())
                errors.append(err)
                continue

            # 3. Gather child process tree
            procs_to_kill: list[psutil.Process] = []
            if terminate_children:
                try:
                    children = proc.children(recursive=True)
                    procs_to_kill.extend(children)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            procs_to_kill.append(proc)

            # 4. Terminate execution
            for p in procs_to_kill:
                try:
                    if force:
                        p.kill()
                    else:
                        p.terminate()
                except psutil.NoSuchProcess:
                    pass
                except Exception as exc:
                    errors.append(f"PID {p.pid}: {exc}")

            # Wait for exit
            _, still_alive = psutil.wait_procs(procs_to_kill, timeout=timeout_sec)
            for p in still_alive:
                with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                    p.kill()

            # Final verification
            for p in procs_to_kill:
                if not psutil.pid_exists(p.pid):
                    terminated.append(p.pid)

        all_success = len(errors) == 0 and len(terminated) > 0
        return ProcessTerminationResultModel(
            success=all_success,
            target=target_str,
            terminated_pids=list(set(terminated)),
            already_dead=len(terminated) == 0 and len(errors) == 0,
            error="; ".join(errors) if errors else None,
        )

    @classmethod
    def restart(
        cls,
        target: int | str,
        force: bool = False,
        arguments: list[str] | None = None,
        wait_timeout_sec: float = 5.0,
    ) -> ProcessLaunchResultModel:
        """Restart an active process, preserving original arguments and working directory if possible."""
        pid: int | None = None
        exe_path: str | None = None
        cmdline_args: list[str] = []
        cwd: str | None = None

        # Try to find running process telemetry before termination
        if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
            p_int = int(target)
            if psutil.pid_exists(p_int):
                try:
                    p = psutil.Process(p_int)
                    exe_path = p.exe()
                    cmdline_args = p.cmdline()[1:] if len(p.cmdline()) > 1 else []
                    cwd = p.cwd()
                    pid = p_int
                except Exception:
                    pass
        else:
            name_q = str(target).lower().strip()
            for p in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    if p.name().lower() in (name_q, f"{name_q}.exe"):
                        exe_path = p.exe()
                        cmdline_args = p.cmdline()[1:] if len(p.cmdline()) > 1 else []
                        cwd = p.cwd()
                        pid = p.pid
                        break
                except Exception:
                    continue

        # Terminate active process
        term_target = pid if pid is not None else target
        term_res = cls.terminate(term_target, force=force, timeout_sec=wait_timeout_sec)
        if not term_res.success and not term_res.already_dead:
            return ProcessLaunchResultModel(
                success=False,
                target=str(target),
                error=f"Failed to terminate active process before restart: {term_res.error}",
            )

        # Wait briefly for OS resources to release
        time.sleep(0.5)

        # Relaunch
        relaunch_target = exe_path or str(target)
        relaunch_args = arguments if arguments is not None else cmdline_args
        return cls.launch(
            target=relaunch_target,
            arguments=relaunch_args,
            working_directory=cwd,
        )

    @classmethod
    def focus(cls, target: int | str) -> bool:
        """Bring application window to active foreground via native OS APIs."""
        os_name = platform.system().lower()

        # 1. Windows: Native Win32 SetForegroundWindow or PowerShell AppActivate
        if os_name == "windows":
            # Try DesktopAutomationEngine first
            from app.device.desktop_automation import DesktopAutomationEngine
            try:
                state = DesktopAutomationEngine.read_window_state(window_target=target)
                if state.exists and state.hwnd and hasattr(ctypes, "windll"):
                    hwnd = int(state.hwnd)
                    # SW_RESTORE = 9
                    ctypes.windll.user32.ShowWindow(hwnd, 9)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    return True
            except Exception:
                pass

            # Fallback to WScript.Shell AppActivate
            try:
                app_target_str = str(target)
                ps_script = f"""
                $wshell = New-Object -ComObject WScript.Shell;
                $wshell.AppActivate('{app_target_str}')
                """
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    timeout=3,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return "True" in res.stdout or res.returncode == 0
            except Exception:
                return False

        # 2. macOS: AppleScript activate
        elif os_name == "darwin":
            try:
                app_name = str(target)
                script = f'tell application "{app_name}" to activate'
                res = subprocess.run(
                    ["osascript", "-e", script],
                    timeout=3,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return res.returncode == 0
            except Exception:
                return False

        # 3. Linux: wmctrl -a or xdotool
        elif os_name == "linux":
            try:
                if isinstance(target, int) or str(target).isdigit():
                    res = subprocess.run(
                        ["xdotool", "search", "--pid", str(target), "windowactivate"],
                        timeout=3,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if res.returncode == 0:
                        return True
                res = subprocess.run(
                    ["wmctrl", "-a", str(target)],
                    timeout=3,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return res.returncode == 0
            except Exception:
                return False

        return False

    @classmethod
    def list_processes(
        cls,
        filter_name: str | None = None,
        running_only: bool = True,
        limit: int = 100,
    ) -> list[ProcessInfoModel]:
        """List active processes with memory and CPU telemetry."""
        results: list[ProcessInfoModel] = []
        name_filter = filter_name.lower().strip() if filter_name else None

        for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "cpu_percent", "memory_info", "status", "create_time", "username"]):
            try:
                info = proc.info
                p_name = info.get("name") or ""
                if name_filter and name_filter not in p_name.lower():
                    continue

                status = info.get("status") or "running"
                if running_only and status in (psutil.STATUS_STOPPED, psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
                    continue

                mem = info.get("memory_info")
                rss_mb = round(mem.rss / (1024 * 1024), 2) if mem else 0.0
                vms_mb = round(mem.vms / (1024 * 1024), 2) if mem else 0.0

                results.append(ProcessInfoModel(
                    pid=info["pid"],
                    name=p_name,
                    exe=info.get("exe"),
                    cmdline=info.get("cmdline") or [],
                    cpu_percent=round(info.get("cpu_percent") or 0.0, 1),
                    memory_rss_mb=rss_mb,
                    memory_vms_mb=vms_mb,
                    status=str(status),
                    create_time=info.get("create_time") or 0.0,
                    username=info.get("username"),
                ))
                if len(results) >= limit:
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return results

    @classmethod
    def get_process_details(cls, pid: int) -> ProcessDetailsModel | None:
        """Retrieve detailed telemetry and relationship hierarchy for a specific process PID."""
        if not psutil.pid_exists(pid):
            return None

        try:
            p = psutil.Process(pid)
            mem = p.memory_info()
            rss_mb = round(mem.rss / (1024 * 1024), 2) if mem else 0.0
            vms_mb = round(mem.vms / (1024 * 1024), 2) if mem else 0.0

            children_pids: list[int] = []
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                children_pids = [c.pid for c in p.children(recursive=False)]

            open_files_count = 0
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                open_files_count = len(p.open_files())

            cwd: str | None = None
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                cwd = p.cwd()

            ppid: int | None = None
            with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                ppid = p.ppid()

            return ProcessDetailsModel(
                pid=p.pid,
                ppid=ppid,
                name=p.name(),
                exe=p.exe() if hasattr(p, "exe") else None,
                cmdline=p.cmdline(),
                cpu_percent=round(p.cpu_percent(), 1),
                memory_rss_mb=rss_mb,
                memory_vms_mb=vms_mb,
                status=p.status(),
                create_time=p.create_time(),
                username=p.username() if hasattr(p, "username") else None,
                num_threads=p.num_threads(),
                open_files_count=open_files_count,
                children_pids=children_pids,
                cwd=cwd,
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None


# Backward-compatible alias for orchestrator and consumers
ProcessController = ProcessLifecycleController
