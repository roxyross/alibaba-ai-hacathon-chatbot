"""Zero-Mock Auditor — Validates the Zero Simulation Doctrine across production code."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any
import structlog

from app.production_readiness.schemas import ZeroMockAuditResult

log = structlog.get_logger()


class ZeroMockAuditor:
    """Statically inspects production codebase ASTs to ensure zero mocks or simulations exist."""

    PROHIBITED_IMPORT_MODULES = {
        "unittest.mock",
        "mock",
        "pytest_mock",
        "faker",
    }

    PROHIBITED_SYMBOLS = {
        "MagicMock",
        "AsyncMock",
        "PropertyMock",
        "create_autospec",
    }

    PROHIBITED_FLAGS = {
        "simulation_mode",
        "use_mock",
        "dummy_mode",
        "mock_database",
    }

    @classmethod
    def scan_directory(cls, target_dir: str | Path | None = None) -> ZeroMockAuditResult:
        """Scan all Python files in the target directory for mock frameworks and simulation flags."""
        if target_dir is None:
            # Default to backend/src/app
            target_dir = Path(__file__).resolve().parent.parent

        target_path = Path(target_dir)
        files_scanned = 0
        violations: list[dict[str, Any]] = []

        for root, dirs, files in os.walk(target_path):
            # Skip test directories, virtual environments, and caches
            dirs[:] = [
                d for d in dirs
                if d not in ("tests", "__tests__", ".venv", "venv", ".pytest_cache", "__pycache__")
            ]

            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = Path(root) / file
                # Skip test files if any slip through
                if file.startswith("test_") or file.endswith("_test.py"):
                    continue

                files_scanned += 1
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        code = f.read()

                    tree = ast.parse(code, filename=str(file_path))
                    cls._inspect_ast(tree, file_path, violations)
                except SyntaxError as e:
                    violations.append({
                        "file": str(file_path),
                        "line": e.lineno or 0,
                        "type": "syntax_error",
                        "detail": f"Syntax error during scan: {e}",
                    })
                except Exception as ex:
                    log.warning("zero_mock_scan_error", file=str(file_path), error=str(ex))

        is_compliant = len(violations) == 0
        summary = (
            f"Zero-Mock Doctrine strictly upheld: 0 violations found across {files_scanned} production modules."
            if is_compliant
            else f"Zero-Mock Doctrine violated: {len(violations)} mock/simulation occurrences found."
        )

        return ZeroMockAuditResult(
            files_scanned=files_scanned,
            violations_found=len(violations),
            prohibited_patterns_checked=list(cls.PROHIBITED_IMPORT_MODULES | cls.PROHIBITED_SYMBOLS | cls.PROHIBITED_FLAGS),
            mock_occurrences=violations,
            is_zero_mock_compliant=is_compliant,
            summary=summary,
        )

    @classmethod
    def _inspect_ast(
        cls, tree: ast.AST, file_path: Path, violations: list[dict[str, Any]]
    ) -> None:
        """Inspect an individual AST tree for prohibited imports and simulation tokens."""
        for node in ast.walk(tree):
            # 1. Check Import statements
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in cls.PROHIBITED_IMPORT_MODULES or alias.name.startswith("unittest.mock"):
                        violations.append({
                            "file": str(file_path),
                            "line": node.lineno,
                            "type": "prohibited_import",
                            "detail": f"Prohibited import statement: 'import {alias.name}'",
                        })

            # 2. Check ImportFrom statements
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod in cls.PROHIBITED_IMPORT_MODULES or mod.startswith("unittest.mock"):
                    violations.append({
                        "file": str(file_path),
                        "line": node.lineno,
                        "type": "prohibited_import",
                        "detail": f"Prohibited import from: 'from {mod} import ...'",
                    })
                for alias in node.names:
                    if alias.name in cls.PROHIBITED_SYMBOLS:
                        violations.append({
                            "file": str(file_path),
                            "line": node.lineno,
                            "type": "prohibited_symbol",
                            "detail": f"Prohibited mock symbol imported: '{alias.name}'",
                        })

            # 3. Check variable assignments for simulation flags
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.lower() in cls.PROHIBITED_FLAGS:
                        # Check if assigned True
                        if isinstance(node.value, ast.Constant) and node.value.value is True:
                            violations.append({
                                "file": str(file_path),
                                "line": node.lineno,
                                "type": "prohibited_flag",
                                "detail": f"Simulation flag enabled: '{target.id} = True'",
                            })
