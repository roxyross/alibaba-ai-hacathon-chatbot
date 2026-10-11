"""Packaging & Artifact Validator — Inspects container configurations, environments, and production bundles."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
import structlog

from app.production_readiness.schemas import PackagingAuditResult

log = structlog.get_logger()


class PackagingValidator:
    """Validates containerization assets, environment specs, and production frontend bundles."""

    @classmethod
    def validate_packaging(cls, repo_root: str | Path | None = None) -> PackagingAuditResult:
        """Inspect the repository root for production packaging artifacts."""
        if repo_root is None:
            # Default to repo root (three levels up from this file)
            repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent

        root_path = Path(repo_root)

        backend_dockerfile = (root_path / "backend" / "Dockerfile").is_file()
        frontend_dockerfile = (root_path / "frontend" / "Dockerfile").is_file()
        docker_compose = (root_path / "docker-compose.yml").is_file()
        prod_env_spec = (root_path / ".env.production.example").is_file()

        dist_index = root_path / "frontend" / "dist" / "index.html"
        frontend_bundle_built = dist_index.is_file()

        # Gather bundle metrics if built
        dist_size_kb = 0.0
        dist_files_count = 0
        dist_dir = root_path / "frontend" / "dist"
        if dist_dir.is_dir():
            for r, _, files in os.walk(dist_dir):
                for f in files:
                    fp = Path(r) / f
                    dist_size_kb += fp.stat().st_size / 1024.0
                    dist_files_count += 1

        details: dict[str, Any] = {
            "backend_dockerfile_path": str(root_path / "backend" / "Dockerfile"),
            "frontend_dockerfile_path": str(root_path / "frontend" / "Dockerfile"),
            "docker_compose_path": str(root_path / "docker-compose.yml"),
            "production_env_path": str(root_path / ".env.production.example"),
            "frontend_bundle_files": dist_files_count,
            "frontend_bundle_size_kb": round(dist_size_kb, 2),
        }

        is_packaged = (
            backend_dockerfile
            and frontend_dockerfile
            and docker_compose
            and prod_env_spec
            and frontend_bundle_built
        )

        return PackagingAuditResult(
            dockerfile_backend=backend_dockerfile,
            dockerfile_frontend=frontend_dockerfile,
            docker_compose=docker_compose,
            production_env_spec=prod_env_spec,
            frontend_bundle_built=frontend_bundle_built,
            is_packaged=is_packaged,
            details=details,
        )
