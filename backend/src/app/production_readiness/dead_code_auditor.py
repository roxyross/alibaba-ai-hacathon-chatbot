"""Dead Code & Syntax Auditor — AST analysis for unreachable code and syntax hygiene."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import structlog

from app.production_readiness.schemas import DeadCodeAuditResult

log = structlog.get_logger()


class DeadCodeAuditor:
    """Analyzes production ASTs to detect unreachable statements and dead code blocks."""

    @classmethod
    def audit_directory(cls, target_dir: str | Path | None = None) -> DeadCodeAuditResult:
        """Audit Python modules for unreachable blocks and syntax correctness."""
        if target_dir is None:
            target_dir = Path(__file__).resolve().parent.parent

        target_path = Path(target_dir)
        modules_analyzed = 0
        unreachable_blocks = 0
        syntax_errors = 0

        for root, dirs, files in os.walk(target_path):
            dirs[:] = [
                d for d in dirs
                if d not in ("tests", "__tests__", ".venv", "venv", ".pytest_cache", "__pycache__")
            ]

            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = Path(root) / file
                modules_analyzed += 1

                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        code = f.read()

                    tree = ast.parse(code, filename=str(file_path))
                    unreachable_blocks += cls._count_unreachable_blocks(tree)
                except SyntaxError:
                    syntax_errors += 1
                except Exception as ex:
                    log.warning("dead_code_audit_error", file=str(file_path), error=str(ex))

        is_clean = unreachable_blocks == 0 and syntax_errors == 0
        summary = (
            f"Codebase verified clean: {modules_analyzed} modules analyzed with 0 unreachable blocks and 0 syntax errors."
            if is_clean
            else f"Dead code detected: {unreachable_blocks} unreachable blocks, {syntax_errors} syntax errors across {modules_analyzed} modules."
        )

        return DeadCodeAuditResult(
            modules_analyzed=modules_analyzed,
            unreachable_blocks_found=unreachable_blocks,
            syntax_errors_found=syntax_errors,
            is_clean=is_clean,
            summary=summary,
        )

    @classmethod
    def _count_unreachable_blocks(cls, tree: ast.AST) -> int:
        """Count unreachable blocks such as if False: or code following unconditional return."""
        count = 0
        for node in ast.walk(tree):
            # Check for if False: or if 0:
            if isinstance(node, ast.If):
                if isinstance(node.test, ast.Constant) and (node.test.value is False or node.test.value == 0):
                    count += 1

            # Check for unreachable statements in function/method bodies
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = node.body
                for i, stmt in enumerate(body[:-1]):
                    if isinstance(stmt, (ast.Return, ast.Raise)):
                        # Any non-empty statement after return is unreachable
                        count += len(body) - (i + 1)
                        break

        return count
