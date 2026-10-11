"""Unit and Security Tests for Sandboxed File & Folder Intelligence.

Verifies:
1. Sandbox boundary confinement & path traversal defense.
2. Sensitive secret protection (.env, id_rsa, credentials.json, .pem, .key).
3. Sandboxed write, read, edit (surgical patch), list, search.
4. Recursive folder analysis (language classification, entrypoints, structure).
5. ToolRegistry registration and execution.
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from app.files.sandbox import FileSecuritySandbox
from app.files.service import FileSystemService
from app.tools.registry import ToolRegistry


@pytest.fixture
def temp_workspace() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir).resolve()
        # Create some test files and folders
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
        (root / "src" / "index.ts").write_text("export const greet = () => 'hi';\n", encoding="utf-8")
        (root / "package.json").write_text('{"name": "test-project"}', encoding="utf-8")
        (root / "README.md").write_text("# Test Project\nWelcome to testing.", encoding="utf-8")
        (root / ".env").write_text("SECRET_KEY=supersecret123\n", encoding="utf-8")
        (root / "id_rsa").write_text("FAKE_PRIVATE_KEY", encoding="utf-8")
        yield root


def test_sandbox_path_confinement(temp_workspace: Path) -> None:
    sandbox = FileSecuritySandbox(allowed_roots=[temp_workspace])

    # Valid child path resolves
    valid = sandbox.validate_path(temp_workspace / "src" / "main.py")
    assert valid.exists()

    # Relative path resolves
    valid_rel = sandbox.validate_path("src/index.ts")
    assert valid_rel.exists()

    # Traversal escape is blocked
    with pytest.raises(PermissionError) as exc_info:
        sandbox.validate_path("../../../etc/passwd")
    assert "resolves outside the authorized workspace sandbox boundary" in str(exc_info.value)

    with pytest.raises(PermissionError):
        sandbox.validate_path("C:/Windows/System32/calc.exe")


def test_sandbox_sensitive_file_protection(temp_workspace: Path) -> None:
    sandbox = FileSecuritySandbox(allowed_roots=[temp_workspace])

    # .env is blocked
    with pytest.raises(PermissionError) as exc_info:
        sandbox.validate_path(".env")
    assert "protected secret file" in str(exc_info.value)

    # id_rsa is blocked
    with pytest.raises(PermissionError):
        sandbox.validate_path("id_rsa")

    # .key and .pem are blocked
    with pytest.raises(PermissionError):
        sandbox.validate_path("certificates/server.key")

    with pytest.raises(PermissionError):
        sandbox.validate_path("keys/cert.pem")


def test_filesystem_service_crud_and_edit(temp_workspace: Path) -> None:
    sandbox = FileSecuritySandbox(allowed_roots=[temp_workspace])
    service = FileSystemService(sandbox=sandbox)

    # 1. Write File
    write_res = service.write_file("src/test_write.txt", "line 1\nline 2\nline 3\n")
    assert write_res.success
    assert write_res.created

    # 2. Read File
    read_res = service.read_file("src/test_write.txt")
    assert read_res.content == "line 1\nline 2\nline 3\n"
    assert read_res.lines_count == 3

    # 3. Surgical Edit File
    edit_res = service.edit_file(
        "src/test_write.txt",
        target_snippet="line 2",
        replacement_snippet="line TWO MODIFIED",
    )
    assert edit_res.success

    # Verify edit
    read_after = service.read_file("src/test_write.txt")
    assert "line TWO MODIFIED" in read_after.content
    assert "line 2" not in read_after.content

    # Target snippet not found should raise ValueError
    with pytest.raises(ValueError):
        service.edit_file("src/test_write.txt", "nonexistent snippet", "replacement")


def test_filesystem_service_list_and_search(temp_workspace: Path) -> None:
    sandbox = FileSecuritySandbox(allowed_roots=[temp_workspace])
    service = FileSystemService(sandbox=sandbox)

    # List files
    list_res = service.list_files(directory_path=".", max_depth=3)
    assert list_res.total_items >= 4
    file_names = [item.name for item in list_res.items]
    assert "main.py" in file_names
    assert "README.md" in file_names

    # Search files
    search_res = service.search_files(content_query="hello", directory_path="src")
    assert search_res.total_matches >= 1
    assert any("main.py" in m.file_path for m in search_res.matches)
    assert any("def hello():" in m.snippet for m in search_res.matches)


def test_filesystem_service_analyze_folder(temp_workspace: Path) -> None:
    sandbox = FileSecuritySandbox(allowed_roots=[temp_workspace])
    service = FileSystemService(sandbox=sandbox)

    report = service.analyze_folder(folder_path=".", max_depth=3)
    assert report.total_files >= 3
    assert "Python" in report.primary_languages or "TypeScript" in report.primary_languages
    assert any(term in report.project_type.lower() for term in ["python", "node", "service", "general"])
    assert len(report.key_structure) > 0


@pytest.mark.asyncio
async def test_tool_registry_file_tools_integration(temp_workspace: Path) -> None:
    sandbox = FileSecuritySandbox(allowed_roots=[temp_workspace])
    service = FileSystemService(sandbox=sandbox)
    registry = ToolRegistry.get_instance()
    try:
        service.register_file_tools(registry=registry)

        # Verify tools registered
        for tool_id in ["file_list", "file_read", "file_write", "file_edit", "file_search", "folder_analyze"]:
            assert registry.get(tool_id) is not None

        # Execute file_read tool via handler
        read_handler = registry.get_handler("file_read")
        assert read_handler is not None
        read_output = await read_handler(file_path="README.md")
        assert read_output["lines_count"] == 2
        assert "Test Project" in read_output["content"]

        # Execute folder_analyze tool via handler
        analyze_handler = registry.get_handler("folder_analyze")
        assert analyze_handler is not None
        analyze_output = await analyze_handler(folder_path=".")
        assert analyze_output["total_files"] >= 3
        assert "summary" in analyze_output
    finally:
        for tool_id in ["file_list", "file_read", "file_write", "file_edit", "file_search", "folder_analyze"]:
            registry.unregister(tool_id)
