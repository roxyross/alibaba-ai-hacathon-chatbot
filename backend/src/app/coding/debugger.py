"""Python Sandboxed Debugger Engine for ROXY-AI Code Studio.

Implements real, stateful debugging via Python's standard bdb (Breakpoint Debugger):
- Breakpoint management (set, toggle, clear)
- Execution stepping (step_over, step_into, step_out, continue)
- Local variable inspection and call stack unwinding
- Exception and error capture
- Workspace path containment via FileSecuritySandbox
- Tenant isolation (session bound to owner user_id)
- Thread and process lifecycle cleanup
"""

from __future__ import annotations

import bdb
import io
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from app.files.sandbox import FileSecuritySandbox

log = structlog.get_logger()


@dataclass
class BreakpointInfo:
    file_path: str
    line_number: int
    enabled: bool = True
    hit_count: int = 0


@dataclass
class StackFrameInfo:
    function: str
    filename: str
    lineno: int
    locals: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "filename": self.filename,
            "lineno": self.lineno,
            "locals": self.locals,
        }


class SandboxedBdb(bdb.Bdb):
    """Custom standard-library BDB engine for interactive execution stepping."""

    def __init__(self, session: DebugSession) -> None:
        super().__init__()
        self.session = session

    def user_line(self, frame: Any) -> None:
        """Called when execution reaches a line or breakpoint."""
        # Only pause if execution is inside target workspace file (ignore internal debugger frames)
        raw_fn = str(frame.f_code.co_filename)
        canon_fn = Path(raw_fn).resolve()
        target_canon = self.session.file_path.resolve()

        if canon_fn != target_canon:
            # Step until we return to user script
            return

        lineno = frame.f_lineno
        self.session.current_file = str(canon_fn)
        self.session.current_line = lineno

        # Extract local variables
        raw_locals = frame.f_locals
        self.session.local_variables = {
            str(k): repr(v)
            for k, v in raw_locals.items()
            if not str(k).startswith("__")
        }

        # Extract call stack
        stack: list[StackFrameInfo] = []
        cur = frame
        while cur is not None:
            fn_code = cur.f_code
            stack.append(
                StackFrameInfo(
                    function=fn_code.co_name,
                    filename=str(Path(fn_code.co_filename).resolve()),
                    lineno=cur.f_lineno,
                    locals={
                        str(k): repr(v)
                        for k, v in cur.f_locals.items()
                        if not str(k).startswith("__")
                    },
                )
            )
            cur = cur.f_back
        self.session.call_stack = stack

        bp_found = False
        matching_bp_key = None
        for (bp_path, bp_line), bp_info in self.session.breakpoints.items():
            if bp_line == lineno and Path(bp_path).resolve() == canon_fn and bp_info.enabled:
                bp_found = True
                matching_bp_key = (bp_path, bp_line)
                break

        # If not at an active breakpoint and not in stepping mode, continue running without pause
        if not bp_found and not self.session.stepping_active:
            self.set_continue()
            return

        if bp_found and matching_bp_key:
            self.session.breakpoints[matching_bp_key].hit_count += 1
            self.session.state = "PAUSED_AT_BREAKPOINT"
        else:
            self.session.state = "PAUSED_STEPPING"

        self.session.stepping_active = False

        # Signal that debugger is paused and waiting for user command
        self.session.resume_event.clear()
        self.session.state_changed_event.set()

        # Wait for user action
        resumed = self.session.resume_event.wait(timeout=120.0)
        if not resumed or self.session.requested_action == "stop":
            self.set_quit()
            raise bdb.BdbQuit("Debugging terminated by user request or timeout.")

        action = self.session.requested_action
        if action == "continue":
            self.set_continue()
        elif action == "step_over":
            self.set_next(frame)
        elif action == "step_into":
            self.set_step()
        elif action == "step_out":
            self.set_return(frame)
        else:
            self.set_continue()

    def user_exception(self, frame: Any, exc_info: Any) -> None:
        """Called when an unhandled exception occurs in user code."""
        exc_type, exc_val, _ = exc_info
        if exc_type is not bdb.BdbQuit:
            self.session.exception_info = f"{exc_type.__name__}: {exc_val}"
            log.info("debugger.user_exception", session_id=self.session.session_id, error=self.session.exception_info)


@dataclass
class DebugSession:
    """Represents an active interactive debug session."""

    session_id: str
    user_id: str
    workspace_root: Path
    file_path: Path
    state: str = "INITIALIZING"  # INITIALIZING, RUNNING, PAUSED_AT_BREAKPOINT, PAUSED_STEPPING, TERMINATED, ERROR
    current_line: int | None = None
    current_file: str | None = None
    call_stack: list[StackFrameInfo] = field(default_factory=list)
    local_variables: dict[str, str] = field(default_factory=dict)
    breakpoints: dict[tuple[str, int], BreakpointInfo] = field(default_factory=dict)
    stdout_chunks: list[str] = field(default_factory=list)
    stderr_chunks: list[str] = field(default_factory=list)
    exception_info: str | None = None
    exit_code: int | None = None
    requested_action: str = "continue"
    stepping_active: bool = False
    resume_event: threading.Event = field(default_factory=threading.Event)
    state_changed_event: threading.Event = field(default_factory=threading.Event)
    runner_thread: threading.Thread | None = None
    created_at: float = field(default_factory=time.time)

    def to_state_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "state": self.state,
            "current_file": self.current_file,
            "current_line": self.current_line,
            "call_stack": [s.to_dict() for s in self.call_stack],
            "local_variables": self.local_variables,
            "breakpoints": [
                {
                    "file_path": bp.file_path,
                    "line_number": bp.line_number,
                    "enabled": bp.enabled,
                    "hit_count": bp.hit_count,
                }
                for bp in self.breakpoints.values()
            ],
            "stdout": "".join(self.stdout_chunks),
            "stderr": "".join(self.stderr_chunks),
            "exception": self.exception_info,
            "exit_code": self.exit_code,
        }


class PythonDebuggerManager:
    """Manages multi-tenant sandboxed Python debugging sessions."""

    _instance: PythonDebuggerManager | None = None

    def __init__(self) -> None:
        self._sessions: dict[str, DebugSession] = {}

    @classmethod
    def get_instance(cls) -> PythonDebuggerManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start_session(
        self,
        user_id: str,
        workspace_root: Path,
        relative_file_path: str,
        initial_breakpoints: list[dict[str, Any]] | None = None,
    ) -> DebugSession:
        """Initialize and start a sandboxed debug run in a managed background thread."""
        sandbox = FileSecuritySandbox(allowed_roots=[workspace_root])
        canon_file = sandbox.validate_path(relative_file_path, must_exist=True)

        if not canon_file.is_file():
            raise ValueError(f"Path '{relative_file_path}' is not a regular file.")
        if canon_file.suffix != ".py":
            raise ValueError("Interactive debugger is currently verified for Python (.py) scripts.")

        session_id = f"dbg-{uuid.uuid4().hex[:12]}"
        session = DebugSession(
            session_id=session_id,
            user_id=user_id,
            workspace_root=workspace_root,
            file_path=canon_file,
        )

        # Register initial breakpoints
        if initial_breakpoints:
            for bp in initial_breakpoints:
                line = int(bp.get("line_number", 1))
                key = (str(canon_file), line)
                session.breakpoints[key] = BreakpointInfo(
                    file_path=str(canon_file),
                    line_number=line,
                    enabled=bool(bp.get("enabled", True)),
                )

        self._sessions[session_id] = session

        # Start execution in background thread
        thread = threading.Thread(
            target=self._run_debugger_thread,
            args=(session,),
            name=f"RoxyDebugger-{session_id}",
            daemon=True,
        )
        session.runner_thread = thread
        thread.start()

        log.info(
            "debugger.session_started",
            session_id=session_id,
            user_id=user_id,
            file=str(canon_file),
        )
        return session

    def _run_debugger_thread(self, session: DebugSession) -> None:
        """Target worker thread executing code under BDB control."""
        bdb_engine = SandboxedBdb(session)

        # Apply breakpoints to BDB
        for bp in session.breakpoints.values():
            if bp.enabled:
                bdb_engine.set_break(bp.file_path, bp.line_number)

        code_text = session.file_path.read_text(encoding="utf-8")
        compiled_code = compile(code_text, str(session.file_path), "exec")

        session.state = "RUNNING"

        # Redirect stdout and stderr safely for this thread execution
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr

        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        global_scope: dict[str, Any] = {
            "__name__": "__main__",
            "__file__": str(session.file_path),
            "__builtins__": __builtins__,
        }

        try:
            bdb_engine.run(compiled_code, global_scope)
            session.exit_code = 0
            session.state = "TERMINATED"
        except bdb.BdbQuit:
            session.exit_code = 130
            session.state = "TERMINATED"
        except Exception as exc:
            session.exception_info = f"{type(exc).__name__}: {exc}"
            session.exit_code = 1
            session.state = "ERROR"
            log.warning("debugger.runtime_exception", session_id=session.session_id, error=str(exc))
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            session.stdout_chunks.append(stdout_capture.getvalue())
            session.stderr_chunks.append(stderr_capture.getvalue())
            session.state_changed_event.set()
            log.info("debugger.session_ended", session_id=session.session_id, state=session.state)

    def get_session(self, session_id: str, user_id: str | None = None) -> DebugSession:
        """Retrieve session and verify user ownership to prevent cross-tenant access."""
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"Debug session '{session_id}' not found.")
        if user_id is not None and session.user_id != user_id:
            raise PermissionError(f"Access denied: Debug session '{session_id}' does not belong to authorized user.")
        return session

    def set_breakpoint(self, session_id: str, user_id: str, line_number: int, enabled: bool = True) -> BreakpointInfo:
        """Add or update a breakpoint in an active session."""
        session = self.get_session(session_id, user_id)
        key = (str(session.file_path), line_number)
        bp = BreakpointInfo(
            file_path=str(session.file_path),
            line_number=line_number,
            enabled=enabled,
        )
        session.breakpoints[key] = bp
        return bp

    def clear_breakpoint(self, session_id: str, user_id: str, line_number: int) -> bool:
        """Remove a breakpoint from the session."""
        session = self.get_session(session_id, user_id)
        key = (str(session.file_path), line_number)
        if key in session.breakpoints:
            del session.breakpoints[key]
            return True
        return False

    def send_action(self, session_id: str, user_id: str, action: str) -> dict[str, Any]:
        """Dispatch stepping action: continue, step_over, step_into, step_out, stop."""
        valid_actions = {"continue", "step_over", "step_into", "step_out", "stop"}
        if action not in valid_actions:
            raise ValueError(f"Invalid debugger action '{action}'. Valid actions: {valid_actions}")

        session = self.get_session(session_id, user_id)
        if session.state in ("TERMINATED", "ERROR"):
            return session.to_state_dict()

        session.requested_action = action
        if action in ("step_over", "step_into", "step_out"):
            session.stepping_active = True
        else:
            session.stepping_active = False

        session.state = "RUNNING"
        session.state_changed_event.clear()
        session.resume_event.set()

        # Wait briefly for debugger to either pause at next location or terminate
        session.state_changed_event.wait(timeout=2.0)
        return session.to_state_dict()

    def stop_session(self, session_id: str, user_id: str) -> bool:
        """Stop and clean up debug session resources."""
        session = self.get_session(session_id, user_id)
        session.requested_action = "stop"
        session.state = "TERMINATED"
        session.resume_event.set()

        if session.runner_thread and session.runner_thread.is_alive():
            session.runner_thread.join(timeout=2.0)

        self._sessions.pop(session_id, None)
        log.info("debugger.stopped_and_cleaned", session_id=session_id)
        return True
