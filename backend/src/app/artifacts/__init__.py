"""Artifacts & Cowork Workspace Package for ROXY-AI 2.0.

Provides multi-artifact canvas, live preview, version tracking, diff computation,
document/diagram generators, and human-in-the-loop iterative refinement.
"""

from __future__ import annotations

from app.artifacts.repository import ArtifactRepository
from app.artifacts.service import CoworkService

__all__ = ["ArtifactRepository", "CoworkService"]
