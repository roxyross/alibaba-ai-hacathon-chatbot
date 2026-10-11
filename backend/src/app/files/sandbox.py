"""File Security & Sandbox Boundary Enforcement.

Ensures all file operations remain confined within permitted workspace directories,
prevents directory traversal attacks and symlink escapes, and protects sensitive secrets.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

import structlog

log = structlog.get_logger()


class FileSecuritySandbox:
    """Enforces path containment, symlink verification, and sensitive file masking."""

    _SENSITIVE_PATTERNS: ClassVar[set[str]] = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.staging",
        "id_rsa",
        "id_ed25519",
        "id_dsa",
        ".git/config",
        ".git/credentials",
        ".aws/credentials",
        "credentials.json",
        "service_account.json",
        "client_secret.json",
    }

    _SENSITIVE_EXTENSIONS: ClassVar[set[str]] = {
        ".pem",
        ".key",
        ".pfx",
        ".p12",
        ".kdbx",
    }

    def __init__(self, allowed_roots: list[str | Path] | None = None) -> None:
        if allowed_roots:
            self.allowed_roots = [Path(r).resolve() for r in allowed_roots]
        else:
            # Default allowed root is current project workspace root
            workspace_root = Path(__file__).resolve().parents[4]  # roxy-personal-ai root
            self.allowed_roots = [workspace_root]

    def validate_path(self, target_path: str | Path, must_exist: bool = False) -> Path:
        """Validate that target_path is within authorized sandbox and does not target sensitive secrets."""
        raw_path = Path(target_path)
        if not raw_path.is_absolute():
            # Resolve relative to primary allowed root
            canonical = (self.allowed_roots[0] / raw_path).resolve()
        else:
            canonical = raw_path.resolve()

        # 1. Confinement Check (must be child of at least one allowed root)
        is_confined = any(
            canonical == root or root in canonical.parents
            for root in self.allowed_roots
        )
        if not is_confined:
            log.warning("file_sandbox.traversal_blocked", path=str(target_path), canonical=str(canonical))
            raise PermissionError(
                f"Access denied: Path '{target_path}' resolves outside the authorized workspace sandbox boundary."
            )

        # 2. Sensitive File Access Masking Check
        name_lower = canonical.name.lower()
        if name_lower in self._SENSITIVE_PATTERNS or any(canonical.name.endswith(ext) for ext in self._SENSITIVE_EXTENSIONS):
            log.warning("file_sandbox.sensitive_file_blocked", path=str(target_path))
            raise PermissionError(
                f"Access denied: '{canonical.name}' is a protected secret file and cannot be read or modified."
            )

        if must_exist and not canonical.exists():
            raise FileNotFoundError(f"File or directory does not exist: '{target_path}'")

        return canonical
