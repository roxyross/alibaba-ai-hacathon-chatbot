"""File and Folder Intelligence Service for ROXY 2.0.

Provides sandboxed, verified file inspection, editing, multi-format reading,
content search, and recursive project folder structural analysis.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, ClassVar

import structlog

from app.files.sandbox import FileSecuritySandbox
from app.files.schemas import (
    FileItem,
    FileListResponse,
    FileReadResponse,
    FileSearchResponse,
    FileSearchResultItem,
    FileWriteResponse,
    FolderAnalysisReport,
)
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

log = structlog.get_logger()


class FileSystemService:
    """Core domain service for sandboxed filesystem and folder operations."""

    _instance: ClassVar[FileSystemService | None] = None

    def __init__(self, sandbox: FileSecuritySandbox | None = None) -> None:
        self.sandbox = sandbox or FileSecuritySandbox()

    @classmethod
    def get_instance(cls) -> FileSystemService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def list_files(
        self,
        directory_path: str = ".",
        max_depth: int = 2,
        include_hidden: bool = False,
    ) -> FileListResponse:
        """List contents of a directory within the sandbox boundary."""
        canon = self.sandbox.validate_path(directory_path, must_exist=True)
        if not canon.is_dir():
            raise NotADirectoryError(f"Path is not a directory: '{directory_path}'")

        items: list[FileItem] = []
        root_path = self.sandbox.allowed_roots[0]

        for root, dirs, files in os.walk(canon):
            current_depth = len(Path(root).relative_to(canon).parts)
            if current_depth >= max_depth:
                dirs.clear()
                continue

            if not include_hidden:
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                files = [f for f in files if not f.startswith(".")]

            for d in dirs:
                full_d = Path(root) / d
                try:
                    rel_p = str(full_d.relative_to(root_path))
                    stat = full_d.stat()
                    items.append(
                        FileItem(
                            name=d,
                            relative_path=rel_p,
                            absolute_path=str(full_d),
                            is_directory=True,
                            size_bytes=0,
                            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        )
                    )
                except Exception:
                    pass

            for f in files:
                full_f = Path(root) / f
                try:
                    rel_p = str(full_f.relative_to(root_path))
                    stat = full_f.stat()
                    items.append(
                        FileItem(
                            name=f,
                            relative_path=rel_p,
                            absolute_path=str(full_f),
                            is_directory=False,
                            size_bytes=stat.st_size,
                            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                            extension=full_f.suffix.lower(),
                        )
                    )
                except Exception:
                    pass

        return FileListResponse(
            directory=str(canon),
            total_items=len(items),
            items=items,
        )

    def read_file(
        self,
        file_path: str,
        offset_lines: int = 0,
        max_lines: int = 500,
    ) -> FileReadResponse:
        """Read textual content from a sandboxed file."""
        canon = self.sandbox.validate_path(file_path, must_exist=True)
        if canon.is_dir():
            raise IsADirectoryError(f"Target path is a directory, not a file: '{file_path}'")

        ext = canon.suffix.lower()
        stat = canon.stat()

        try:
            with open(canon, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as exc:
            raise RuntimeError(f"Failed to read file '{file_path}': {exc}") from exc

        total_lines = len(lines)
        selected_lines = lines[offset_lines : offset_lines + max_lines]
        truncated = (offset_lines + max_lines) < total_lines

        return FileReadResponse(
            path=str(canon),
            file_type=ext.lstrip(".") or "text",
            size_bytes=stat.st_size,
            content="".join(selected_lines),
            truncated=truncated,
            lines_count=total_lines,
        )

    def write_file(
        self,
        file_path: str,
        content: str,
        overwrite: bool = True,
    ) -> FileWriteResponse:
        """Write content to a file inside the authorized sandbox."""
        canon = self.sandbox.validate_path(file_path, must_exist=False)

        if canon.exists() and not overwrite:
            raise FileExistsError(f"File already exists and overwrite is False: '{file_path}'")

        canon.parent.mkdir(parents=True, exist_ok=True)
        created = not canon.exists()

        with open(canon, "w", encoding="utf-8") as f:
            f.write(content)

        return FileWriteResponse(
            path=str(canon),
            size_bytes=len(content.encode("utf-8")),
            created=created,
            success=True,
            message=f"File successfully {'created' if created else 'updated'}.",
        )

    def edit_file(
        self,
        file_path: str,
        target_snippet: str,
        replacement_snippet: str,
    ) -> FileWriteResponse:
        """Surgically replace a target snippet within a sandboxed file."""
        canon = self.sandbox.validate_path(file_path, must_exist=True)

        with open(canon, "r", encoding="utf-8") as f:
            original = f.read()

        if target_snippet not in original:
            raise ValueError(f"Target snippet not found in '{file_path}'.")

        occurrences = original.count(target_snippet)
        if occurrences > 1:
            raise ValueError(f"Target snippet appears {occurrences} times. Must be a unique substring.")

        updated = original.replace(target_snippet, replacement_snippet, 1)

        with open(canon, "w", encoding="utf-8") as f:
            f.write(updated)

        return FileWriteResponse(
            path=str(canon),
            size_bytes=len(updated.encode("utf-8")),
            created=False,
            success=True,
            message="Snippet replaced successfully.",
        )

    def search_files(
        self,
        content_query: str,
        directory_path: str = ".",
        max_matches: int = 50,
    ) -> FileSearchResponse:
        """Search text contents across sandboxed files."""
        canon = self.sandbox.validate_path(directory_path, must_exist=True)
        matches: list[FileSearchResultItem] = []
        root_path = self.sandbox.allowed_roots[0]

        query_lower = content_query.lower()

        for root, dirs, files in os.walk(canon):
            # Skip hidden and cache dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "dist", ".venv")]

            for f in files:
                if f.startswith(".") or f.endswith((".pyc", ".png", ".jpg", ".exe", ".dll", ".zip")):
                    continue

                full_p = Path(root) / f
                try:
                    # Quick size check: skip files > 2MB for fast scanning
                    if full_p.stat().st_size > 2 * 1024 * 1024:
                        continue

                    rel_p = str(full_p.relative_to(root_path))
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as fh:
                        for line_no, line in enumerate(fh, start=1):
                            if query_lower in line.lower():
                                matches.append(
                                    FileSearchResultItem(
                                        file_path=rel_p,
                                        line_number=line_no,
                                        snippet=line.strip()[:200],
                                    )
                                )
                                if len(matches) >= max_matches:
                                    return FileSearchResponse(
                                        query=content_query,
                                        total_matches=len(matches),
                                        matches=matches,
                                    )
                except Exception:
                    pass

        return FileSearchResponse(
            query=content_query,
            total_matches=len(matches),
            matches=matches,
        )

    def analyze_folder(
        self,
        folder_path: str = ".",
        max_depth: int = 3,
    ) -> FolderAnalysisReport:
        """Analyze project folder structure, detect technology stack, entrypoints, and provide context."""
        canon = self.sandbox.validate_path(folder_path, must_exist=True)
        if not canon.is_dir():
            raise NotADirectoryError(f"Target is not a directory: '{folder_path}'")

        extensions_count: dict[str, int] = {}
        total_files = 0
        total_dirs = 0
        entrypoints: list[str] = []
        key_structure: list[str] = []

        root_path = self.sandbox.allowed_roots[0]

        for root, dirs, files in os.walk(canon):
            depth = len(Path(root).relative_to(canon).parts)
            if depth >= max_depth:
                dirs.clear()
                continue

            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", ".venv", "__pycache__", "dist")]
            total_dirs += len(dirs)

            for d in dirs:
                if depth <= 1:
                    key_structure.append(str((Path(root) / d).relative_to(canon)) + "/")

            for f in files:
                if f.startswith("."):
                    continue
                total_files += 1
                full_f = Path(root) / f
                ext = full_f.suffix.lower()
                if ext:
                    extensions_count[ext] = extensions_count.get(ext, 0) + 1

                # Detect entrypoints
                fname_lower = f.lower()
                if fname_lower in ("main.py", "app.py", "index.ts", "index.js", "app.tsx", "server.js", "manage.py", "main.go"):
                    entrypoints.append(str(full_f.relative_to(root_path)))

        # Categorize primary languages
        lang_map = {
            ".py": "Python",
            ".ts": "TypeScript",
            ".tsx": "TypeScript (React)",
            ".js": "JavaScript",
            ".jsx": "JavaScript (React)",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".cpp": "C++",
            ".c": "C",
            ".html": "HTML",
            ".css": "CSS",
            ".json": "JSON",
            ".md": "Markdown",
        }
        sorted_exts = sorted(extensions_count.items(), key=lambda x: x[1], reverse=True)
        primary_langs = [lang_map[ext] for ext, _ in sorted_exts if ext in lang_map][:5]

        # Determine project type
        proj_type = "general"
        if "Python" in primary_langs and any("main.py" in ep or "app.py" in ep for ep in entrypoints):
            proj_type = "Python Backend / API Service"
        elif "TypeScript (React)" in primary_langs or any("index.html" in f for f in key_structure):
            proj_type = "Frontend Web Application"
        elif "TypeScript" in primary_langs or "JavaScript" in primary_langs:
            proj_type = "Node.js / Full-Stack Service"

        summary = (
            f"Project contains {total_files} files across {total_dirs} directories. "
            f"Primary languages: {', '.join(primary_langs) or 'None'}. "
            f"Identified as: {proj_type}."
        )

        return FolderAnalysisReport(
            folder_path=str(canon),
            total_files=total_files,
            total_directories=total_dirs,
            primary_languages=primary_langs,
            project_type=proj_type,
            entrypoints=entrypoints,
            summary=summary,
            key_structure=key_structure[:15],
        )

    def create_directory(self, directory_path: str) -> FileWriteResponse:
        """Create a new directory within the authorized workspace sandbox."""
        canon = self.sandbox.validate_path(directory_path, must_exist=False)
        created = not canon.exists()
        canon.mkdir(parents=True, exist_ok=True)
        return FileWriteResponse(
            path=str(canon),
            size_bytes=0,
            created=created,
            success=True,
            message="Directory created successfully.",
        )

    def delete_path(self, target_path: str, recursive: bool = True) -> FileWriteResponse:
        """Delete a file or directory within the authorized workspace sandbox."""
        canon = self.sandbox.validate_path(target_path, must_exist=True)
        # Prevent deletion of workspace root
        for root in self.sandbox.allowed_roots:
            if canon == root:
                raise PermissionError("Deleting the workspace root directory is forbidden.")

        if canon.is_dir():
            import shutil
            if recursive:
                shutil.rmtree(canon)
            else:
                canon.rmdir()
        else:
            canon.unlink()

        return FileWriteResponse(
            path=str(canon),
            size_bytes=0,
            created=False,
            success=True,
            message=f"Successfully deleted '{canon.name}'.",
        )

    def rename_path(self, old_path: str, new_path: str) -> FileWriteResponse:
        """Rename or move a file or folder within the authorized workspace sandbox."""
        canon_old = self.sandbox.validate_path(old_path, must_exist=True)
        canon_new = self.sandbox.validate_path(new_path, must_exist=False)
        canon_new.parent.mkdir(parents=True, exist_ok=True)
        canon_old.replace(canon_new)
        return FileWriteResponse(
            path=str(canon_new),
            size_bytes=canon_new.stat().st_size if canon_new.is_file() else 0,
            created=False,
            success=True,
            message=f"Renamed '{canon_old.name}' to '{canon_new.name}'.",
        )

    def get_workspace_tree(
        self,
        root_dir: str = ".",
        max_depth: int = 4,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        """Build a hierarchical tree structure of the workspace."""
        canon = self.sandbox.validate_path(root_dir, must_exist=True)
        root_path = self.sandbox.allowed_roots[0]

        def _build_node(current_path: Path, current_depth: int) -> dict[str, Any]:
            rel_path = str(current_path.relative_to(root_path)).replace("\\", "/")
            if current_path.is_file():
                return {
                    "name": current_path.name,
                    "path": rel_path,
                    "is_directory": False,
                    "size": current_path.stat().st_size,
                    "extension": current_path.suffix.lower(),
                }

            children: list[dict[str, Any]] = []
            if current_depth < max_depth:
                try:
                    entries = sorted(
                        list(current_path.iterdir()),
                        key=lambda p: (not p.is_dir(), p.name.lower()),
                    )
                    for entry in entries:
                        if not include_hidden and entry.name.startswith("."):
                            continue
                        if entry.name in ("__pycache__", "node_modules", ".venv", "dist", ".git", ".pytest_cache", ".mypy_cache"):
                            continue
                        children.append(_build_node(entry, current_depth + 1))
                except Exception:
                    pass

            return {
                "name": current_path.name or "workspace",
                "path": rel_path or ".",
                "is_directory": True,
                "children": children,
            }

        return _build_node(canon, 0)

    async def run_terminal_command(
        self,
        command: str,
        cwd: str = ".",
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        """Run shell command in sandboxed directory with output capture and timeout."""
        import asyncio
        import time

        canon_cwd = self.sandbox.validate_path(cwd, must_exist=True)
        if not canon_cwd.is_dir():
            canon_cwd = canon_cwd.parent

        # Dangerous pattern blocking
        danger_patterns = [
            "rm -rf /", "rm -rf /*", ":(){ :|:& };:", "mkfs", "dd if=/dev",
            "format c:", "del /f /s /q c:\\", "rd /s /q c:\\"
        ]
        cmd_lower = command.lower().strip()
        for dp in danger_patterns:
            if dp in cmd_lower:
                raise PermissionError(f"Command rejected: matches destructive pattern '{dp}'.")

        start_t = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(canon_cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=float(timeout_seconds),
            )
            duration_ms = round((time.perf_counter() - start_t) * 1000)
            stdout_str = stdout_b.decode("utf-8", errors="replace")
            stderr_str = stderr_b.decode("utf-8", errors="replace")
            exit_code = proc.returncode if proc.returncode is not None else 0

            return {
                "command": command,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "success": exit_code == 0,
            }
        except asyncio.TimeoutError:
            return {
                "command": command,
                "stdout": "",
                "stderr": f"Command timed out after {timeout_seconds} seconds.",
                "exit_code": 124,
                "duration_ms": round((time.perf_counter() - start_t) * 1000),
                "success": False,
            }
        except Exception as exc:
            return {
                "command": command,
                "stdout": "",
                "stderr": f"Terminal execution failed: {exc}",
                "exit_code": 1,
                "duration_ms": round((time.perf_counter() - start_t) * 1000),
                "success": False,
            }

    async def get_git_status(self, repo_path: str = ".") -> dict[str, Any]:
        """Fetch git status, branch, and staged/unstaged changes."""
        canon = self.sandbox.validate_path(repo_path, must_exist=True)
        if not canon.is_dir():
            canon = canon.parent

        branch_res = await self.run_terminal_command("git branch --show-current", cwd=str(canon), timeout_seconds=5)
        branch = branch_res.get("stdout", "").strip() or "main"

        status_res = await self.run_terminal_command("git status --porcelain -b", cwd=str(canon), timeout_seconds=5)
        lines = status_res.get("stdout", "").strip().splitlines()

        staged: list[str] = []
        unstaged: list[str] = []
        untracked: list[str] = []

        for line in lines:
            if line.startswith("##"):
                continue
            if len(line) >= 3:
                x = line[0]
                y = line[1]
                path_str = line[3:].strip()
                if x in ("M", "A", "D", "R", "C"):
                    staged.append(path_str)
                if y in ("M", "D"):
                    unstaged.append(path_str)
                if x == "?" and y == "?":
                    untracked.append(path_str)

        return {
            "branch": branch,
            "is_repo": status_res.get("exit_code") == 0,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "clean": len(staged) == 0 and len(unstaged) == 0 and len(untracked) == 0,
            "raw": status_res.get("stdout", ""),
        }

    async def get_git_diff(
        self,
        repo_path: str = ".",
        file_path: str | None = None,
        staged: bool = False,
    ) -> dict[str, Any]:
        """Get git diff for the repo or a specific file."""
        canon = self.sandbox.validate_path(repo_path, must_exist=True)
        if not canon.is_dir():
            canon = canon.parent

        flag = "--staged" if staged else ""
        target = f"-- {file_path}" if file_path else ""
        cmd = f"git diff {flag} {target}".strip()
        res = await self.run_terminal_command(cmd, cwd=str(canon), timeout_seconds=10)
        return {
            "diff": res.get("stdout", ""),
            "success": res.get("success", False),
            "file": file_path,
            "staged": staged,
        }

    async def git_commit(
        self,
        repo_path: str = ".",
        message: str = "",
        stage_all: bool = True,
        add_all: bool = True,
    ) -> dict[str, Any]:
        """Stage files and create a git commit."""
        canon = self.sandbox.validate_path(repo_path, must_exist=True)
        if not canon.is_dir():
            canon = canon.parent

        if not message.strip():
            message = "Update workspace files via Roxy Code Studio"

        if stage_all or add_all:
            await self.run_terminal_command("git add -A", cwd=str(canon), timeout_seconds=10)

        safe_msg = message.replace('"', '\\"')
        res = await self.run_terminal_command(f'git commit -m "{safe_msg}"', cwd=str(canon), timeout_seconds=10)
        return {
            "success": res.get("exit_code") == 0,
            "output": res.get("stdout", "") or res.get("stderr", ""),
            "message": message,
        }

    async def run_project_tests(self, project_path: str = ".", test_path: str = "") -> dict[str, Any]:
        """Run automated test suite for the project."""
        import sys
        canon = self.sandbox.validate_path(project_path, must_exist=True)
        if not canon.is_dir():
            canon = canon.parent

        # Detect test command
        cmd = f"{sys.executable} -m pytest"
        if (canon / "pyproject.toml").exists() or (canon / "pytest.ini").exists():
            cmd = f"{sys.executable} -m pytest {test_path}".strip()
        elif (canon / "package.json").exists():
            cmd = "npm test"

        res = await self.run_terminal_command(cmd, cwd=str(canon), timeout_seconds=60)
        raw_out = (res.get("stdout", "") + "\n" + res.get("stderr", "")).strip()

        # Parse basic passed/failed metrics
        import re
        passed_m = re.search(r"(\d+)\s+passed", raw_out)
        failed_m = re.search(r"(\d+)\s+failed", raw_out)
        passed_count = int(passed_m.group(1)) if passed_m else (1 if res.get("exit_code") == 0 else 0)
        failed_count = int(failed_m.group(1)) if failed_m else (1 if res.get("exit_code") != 0 else 0)

        return {
            "command": cmd,
            "exit_code": res.get("exit_code"),
            "success": res.get("exit_code") == 0,
            "passed": passed_count,
            "failed": failed_count,
            "output": raw_out,
            "duration_ms": res.get("duration_ms"),
        }

    def register_file_tools(self, registry: ToolRegistry | None = None) -> None:
        """Register sandboxed filesystem tools into the central ToolRegistry."""
        reg = registry or ToolRegistry.get_instance()

        # 1. file_list
        async def _tool_file_list(directory_path: str = ".", max_depth: int = 2) -> dict[str, Any]:
            res = self.list_files(directory_path=directory_path, max_depth=max_depth)
            return res.model_dump()

        reg.register(
            AgentTool(
                id="file_list",
                name="List Files",
                description="List files and directories within authorized workspace sandbox.",
                source=ToolSource.SYSTEM,
                capabilities=["files", "list", "directory", "filesystem"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "directory_path": {"type": "string", "default": "."},
                        "max_depth": {"type": "integer", "default": 2},
                    },
                },
                permissions=[],
                risk_level=RiskLevel.LOW,
            ),
            _tool_file_list,
        )

        # 2. file_read
        async def _tool_file_read(file_path: str, offset_lines: int = 0, max_lines: int = 500) -> dict[str, Any]:
            res = self.read_file(file_path=file_path, offset_lines=offset_lines, max_lines=max_lines)
            return res.model_dump()

        reg.register(
            AgentTool(
                id="file_read",
                name="Read File",
                description="Read contents of a source code or text file within workspace sandbox.",
                source=ToolSource.SYSTEM,
                capabilities=["files", "read", "view", "source"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Relative or absolute path to file"},
                        "offset_lines": {"type": "integer", "default": 0},
                        "max_lines": {"type": "integer", "default": 500},
                    },
                    "required": ["file_path"],
                },
                permissions=[],
                risk_level=RiskLevel.LOW,
            ),
            _tool_file_read,
        )

        # 3. file_write
        async def _tool_file_write(file_path: str, content: str, overwrite: bool = True) -> dict[str, Any]:
            res = self.write_file(file_path=file_path, content=content, overwrite=overwrite)
            return res.model_dump()

        reg.register(
            AgentTool(
                id="file_write",
                name="Write File",
                description="Create or overwrite a file within workspace sandbox.",
                source=ToolSource.SYSTEM,
                capabilities=["files", "write", "create", "save"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"},
                        "overwrite": {"type": "boolean", "default": True},
                    },
                    "required": ["file_path", "content"],
                },
                permissions=["write:filesystem"],
                risk_level=RiskLevel.MEDIUM,
            ),
            _tool_file_write,
        )

        # 4. file_edit
        async def _tool_file_edit(file_path: str, target_snippet: str, replacement_snippet: str) -> dict[str, Any]:
            res = self.edit_file(file_path=file_path, target_snippet=target_snippet, replacement_snippet=replacement_snippet)
            return res.model_dump()

        reg.register(
            AgentTool(
                id="file_edit",
                name="Edit File",
                description="Surgically replace unique text block within a sandboxed file.",
                source=ToolSource.SYSTEM,
                capabilities=["files", "edit", "patch", "modify"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "target_snippet": {"type": "string"},
                        "replacement_snippet": {"type": "string"},
                    },
                    "required": ["file_path", "target_snippet", "replacement_snippet"],
                },
                permissions=["write:filesystem"],
                risk_level=RiskLevel.MEDIUM,
            ),
            _tool_file_edit,
        )

        # 5. file_search
        async def _tool_file_search(content_query: str, directory_path: str = ".", max_matches: int = 50) -> dict[str, Any]:
            res = self.search_files(content_query=content_query, directory_path=directory_path, max_matches=max_matches)
            return res.model_dump()

        reg.register(
            AgentTool(
                id="file_search",
                name="Search Files",
                description="Search for exact or case-insensitive text across workspace files.",
                source=ToolSource.SYSTEM,
                capabilities=["files", "search", "grep", "find"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "content_query": {"type": "string"},
                        "directory_path": {"type": "string", "default": "."},
                        "max_matches": {"type": "integer", "default": 50},
                    },
                    "required": ["content_query"],
                },
                permissions=[],
                risk_level=RiskLevel.LOW,
            ),
            _tool_file_search,
        )

        # 6. folder_analyze
        async def _tool_folder_analyze(folder_path: str = ".", max_depth: int = 3) -> dict[str, Any]:
            res = self.analyze_folder(folder_path=folder_path, max_depth=max_depth)
            return res.model_dump()

        reg.register(
            AgentTool(
                id="folder_analyze",
                name="Analyze Folder Context",
                description="Examine a project folder to discover languages, entrypoints, and architecture.",
                source=ToolSource.SYSTEM,
                capabilities=["files", "folder", "project", "architecture", "analyze"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "folder_path": {"type": "string", "default": "."},
                        "max_depth": {"type": "integer", "default": 3},
                    },
                },
                permissions=[],
                risk_level=RiskLevel.LOW,
            ),
            _tool_folder_analyze,
        )
        log.info("files.tools_registered", tools=["file_list", "file_read", "file_write", "file_edit", "file_search", "folder_analyze"])
