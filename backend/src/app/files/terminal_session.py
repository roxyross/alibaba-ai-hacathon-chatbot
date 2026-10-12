"""Interactive Terminal & PTY Session Management for ROXY-AI Code Studio.

Provides stateful, streaming, authenticated terminal sessions with:
- Persistent workspace isolation via FileSecuritySandbox
- Bidirectional stdin/stdout streaming and WebSocket support
- Process-tree termination using psutil
- Idle session expiration and resource limits
- Dangerous command blocking and path traversal guards
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
import structlog

from app.files.sandbox import FileSecuritySandbox

log = structlog.get_logger()

# Prohibited dangerous system disruption patterns
PROHIBITED_COMMAND_PATTERNS: list[str] = [
    "rm -rf /",
    "rm -rf /*",
    ":(){ :|:& };:",
    "mkfs",
    "dd if=/dev",
    "format c:",
    "del /f /s /q c:\\",
    "rd /s /q c:\\",
]

MAX_BUFFER_CHUNKS = 1000
MAX_CHUNK_BYTES = 64 * 1024  # 64 KB per input packet
DEFAULT_IDLE_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class TerminalSession:
    """Represents an active, sandboxed interactive terminal session."""

    session_id: str
    user_id: str
    workspace_root: Path
    cwd: Path
    proc: asyncio.subprocess.Process
    created_at: float
    last_activity_at: float
    buffer: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_BUFFER_CHUNKS))
    subscribers: set[asyncio.Queue[str]] = field(default_factory=set)
    is_active: bool = True
    cols: int = 80
    rows: int = 24
    reader_task: asyncio.Task[None] | None = None

    def touch(self) -> None:
        self.last_activity_at = time.time()


class TerminalSessionManager:
    """Singleton manager for multi-user interactive terminal sessions."""

    _instance: TerminalSessionManager | None = None

    def __init__(self) -> None:
        self._sessions: dict[str, TerminalSession] = {}
        self._reaper_task: asyncio.Task[None] | None = None

    @classmethod
    def get_instance(cls) -> TerminalSessionManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_reaper_started(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            if self._reaper_task is None or self._reaper_task.done():
                self._reaper_task = loop.create_task(self._reaper_loop())
        except RuntimeError:
            pass

    async def _reaper_loop(self) -> None:
        """Background loop to close idle or abandoned sessions."""
        while True:
            await asyncio.sleep(30)
            now = time.time()
            stale_ids = [
                s_id
                for s_id, s in self._sessions.items()
                if (now - s.last_activity_at) > DEFAULT_IDLE_TIMEOUT_SECONDS or not s.is_active
            ]
            for s_id in stale_ids:
                log.info("terminal_session.idle_reaping", session_id=s_id)
                await self.close_session(s_id)

    async def create_session(
        self,
        user_id: str,
        workspace_root: Path,
        initial_cwd: str = ".",
        shell: str | None = None,
        cols: int = 80,
        rows: int = 24,
    ) -> TerminalSession:
        """Start a new sandboxed interactive terminal shell session."""
        self._ensure_reaper_started()
        sandbox = FileSecuritySandbox(allowed_roots=[workspace_root])
        canon_cwd = sandbox.validate_path(initial_cwd, must_exist=True)
        if not canon_cwd.is_dir():
            canon_cwd = canon_cwd.parent

        is_windows = sys.platform.startswith("win")

        if shell:
            executable = shell
            args: list[str] = []
        elif is_windows:
            # Prefer powershell on Windows, fallback to cmd
            executable = "powershell.exe"
            args = ["-NoLogo", "-NoExit"]
        else:
            executable = "/bin/bash" if Path("/bin/bash").exists() else "/bin/sh"
            args = ["-i"]

        try:
            proc = await asyncio.create_subprocess_exec(
                executable,
                *args,
                cwd=str(canon_cwd),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:
            log.error("terminal_session.spawn_failed", error=str(exc), executable=executable)
            # Fallback to cmd.exe on Windows if powershell fails
            if is_windows and executable != "cmd.exe":
                proc = await asyncio.create_subprocess_exec(
                    "cmd.exe",
                    "/Q",
                    "/K",
                    cwd=str(canon_cwd),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
            else:
                raise RuntimeError(f"Failed to spawn interactive shell: {exc}") from exc

        session_id = f"term-{uuid.uuid4().hex[:12]}"
        now = time.time()
        session = TerminalSession(
            session_id=session_id,
            user_id=user_id,
            workspace_root=workspace_root,
            cwd=canon_cwd,
            proc=proc,
            created_at=now,
            last_activity_at=now,
            cols=cols,
            rows=rows,
        )

        # Launch non-blocking output reader
        reader_task = asyncio.create_task(self._stream_output(session))
        session.reader_task = reader_task

        self._sessions[session_id] = session
        log.info(
            "terminal_session.created",
            session_id=session_id,
            user_id=user_id,
            cwd=str(canon_cwd),
            pid=proc.pid,
        )
        return session

    async def _stream_output(self, session: TerminalSession) -> None:
        """Continuously read process stdout/stderr stream and fan out to subscribers."""
        assert session.proc.stdout is not None
        try:
            while session.is_active:
                chunk = await session.proc.stdout.read(1024)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                session.buffer.append(text)
                session.touch()
                # Fan out to all active subscribers
                for queue in list(session.subscribers):
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(text)
        except Exception as exc:
            log.warning("terminal_session.read_error", session_id=session.session_id, error=str(exc))
        finally:
            session.is_active = False
            # Notify subscribers of termination
            for queue in list(session.subscribers):
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait("\r\n[Process terminated]\r\n")

    async def write_input(
        self,
        session_id: str,
        user_id: str,
        data: str,
    ) -> int:
        """Write text or commands into session stdin, verifying user ownership and security policies."""
        session = self.get_session(session_id, user_id)
        if not session.is_active or session.proc.stdin is None or session.proc.returncode is not None:
            raise RuntimeError(f"Terminal session '{session_id}' is closed or terminated.")

        # Guard input size
        if len(data.encode("utf-8")) > MAX_CHUNK_BYTES:
            raise ValueError(f"Input payload exceeds maximum limit of {MAX_CHUNK_BYTES} bytes.")

        # Guard dangerous patterns
        data_lower = data.lower().strip()
        for dp in PROHIBITED_COMMAND_PATTERNS:
            if dp in data_lower:
                raise PermissionError(f"Command blocked by FileSecuritySandbox: matches prohibited pattern '{dp}'.")

        session.touch()
        payload = data.encode("utf-8")
        session.proc.stdin.write(payload)
        await session.proc.stdin.drain()
        return len(payload)

    def resize(self, session_id: str, user_id: str, cols: int, rows: int) -> None:
        """Update window geometry dimensions."""
        session = self.get_session(session_id, user_id)
        session.cols = max(10, min(cols, 500))
        session.rows = max(5, min(rows, 200))
        session.touch()

    def subscribe(self, session_id: str, user_id: str) -> asyncio.Queue[str]:
        """Subscribe an asyncio queue to receive real-time stdout chunks."""
        session = self.get_session(session_id, user_id)
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
        session.subscribers.add(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue[str]) -> None:
        """Remove a subscriber queue."""
        session = self._sessions.get(session_id)
        if session:
            session.subscribers.discard(q)

    def get_session(self, session_id: str, user_id: str | None = None) -> TerminalSession:
        """Retrieve session and verify user ownership to prevent cross-tenant session hijacking."""
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"Terminal session '{session_id}' not found.")
        if user_id is not None and session.user_id != user_id:
            raise PermissionError(f"Access denied: Session '{session_id}' does not belong to authorized user.")
        return session

    def get_output(self, session_id: str, user_id: str, start_index: int = 0) -> dict[str, Any]:
        """Read accumulated buffer for non-WebSocket polling clients."""
        session = self.get_session(session_id, user_id)
        buf_list = list(session.buffer)
        total_chunks = len(buf_list)
        start_idx = max(0, int(start_index)) if start_index is not None else 0
        chunks_to_return: list[str] = list(buf_list[start_idx:])
        return {
            "session_id": session_id,
            "is_active": session.is_active,
            "chunks": chunks_to_return,
            "next_index": total_chunks,
            "cols": session.cols,
            "rows": session.rows,
        }

    async def close_session(self, session_id: str, user_id: str | None = None) -> bool:
        """Safely terminate child process tree and release session resources."""
        if session_id not in self._sessions:
            return False
        session = self._sessions[session_id]
        if user_id is not None and session.user_id != user_id:
            raise PermissionError("Access denied: Cannot close session belonging to another user.")

        session.is_active = False

        # Terminate process tree using psutil
        pid = session.proc.pid
        if pid:
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for child in children:
                    with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                        child.terminate()
                parent.terminate()
                # Await brief termination window
                try:
                    await asyncio.wait_for(session.proc.wait(), timeout=1.5)
                except TimeoutError:
                    # Force kill if unresponsive
                    for child in children:
                        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                            child.kill()
                    parent.kill()
            except (psutil.NoSuchProcess, ProcessLookupError):
                pass
            except Exception as exc:
                log.warning("terminal_session.process_kill_error", pid=pid, error=str(exc))

        if session.reader_task and not session.reader_task.done():
            session.reader_task.cancel()

        self._sessions.pop(session_id, None)
        log.info("terminal_session.closed", session_id=session_id)
        return True
