"""In-memory thread-safe repository for Cowork Workspace artifacts and versions."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.artifacts.generators import compute_unified_diff
from app.artifacts.schemas import ArtifactStatus, ArtifactType
from app.models.artifact import CoworkArtifact, CoworkArtifactVersion

_ARTIFACTS: dict[str, dict[str, Any]] = {}
_VERSIONS: dict[str, list[dict[str, Any]]] = {}
_LOCK = threading.RLock()


def _get_storage_path() -> Path:
    try:
        storage_dir = Path(os.environ.get("ROXY_STORAGE_DIR") or (Path.home() / ".roxy"))
        storage_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        import tempfile
        storage_dir = Path(tempfile.gettempdir()) / "roxy"
        storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir / "cowork_artifacts.json"


def _save_to_disk() -> None:
    try:
        path = _get_storage_path()
        tmp_path = path.with_suffix(".tmp")
        data = {
            "artifacts": _ARTIFACTS,
            "versions": _VERSIONS,
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        tmp_path.replace(path)
    except Exception:
        pass


def _load_from_disk() -> None:
    path = _get_storage_path()
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        with _LOCK:
            if not _ARTIFACTS:
                _ARTIFACTS.update(data.get("artifacts", {}))
            if not _VERSIONS:
                _VERSIONS.update(data.get("versions", {}))
    except Exception:
        pass


def clear_in_memory_stores(clear_disk: bool = False) -> None:
    """Clear in-memory stores for isolated testing."""
    with _LOCK:
        _ARTIFACTS.clear()
        _VERSIONS.clear()
    if clear_disk:
        try:
            path = _get_storage_path()
            if path.exists():
                path.unlink()
        except Exception:
            pass


class ArtifactRepository:
    """Repository handling CRUD, persistence, and version history for workspace artifacts."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session
        _load_from_disk()

    async def create_artifact(
        self,
        user_id: str,
        title: str,
        content: str,
        artifact_type: ArtifactType = ArtifactType.MARKDOWN,
        language: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new workspace artifact and record version 1."""
        now = datetime.now(UTC)
        artifact_id = f"art-{uuid.uuid4().hex[:10]}"
        v1_id = f"ver-{uuid.uuid4().hex[:8]}"

        default_lang = language or (
            "python" if artifact_type == ArtifactType.CODE else
            "mermaid" if artifact_type == ArtifactType.MERMAID else
            "svg" if artifact_type == ArtifactType.SVG else
            "markdown"
        )

        v1: dict[str, Any] = {
            "id": v1_id,
            "version_number": 1,
            "content": content,
            "diff_from_previous": None,
            "change_summary": "Initial creation",
            "created_by": "user",
            "created_at": now.isoformat(),
        }

        art: dict[str, Any] = {
            "id": artifact_id,
            "user_id": user_id,
            "task_id": task_id,
            "session_id": session_id,
            "title": title,
            "artifact_type": str(artifact_type),
            "language": default_lang,
            "content": content,
            "current_version": 1,
            "status": str(ArtifactStatus.DRAFT),
            "metadata": metadata or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        with _LOCK:
            _ARTIFACTS[artifact_id] = art
            _VERSIONS[artifact_id] = [v1]
            _save_to_disk()

        if self.session is not None:
            try:
                db_art = CoworkArtifact(
                    id=artifact_id,
                    user_id=user_id,
                    task_id=task_id,
                    session_id=session_id,
                    title=title,
                    artifact_type=str(artifact_type),
                    language=default_lang,
                    content=content,
                    current_version=1,
                    status=str(ArtifactStatus.DRAFT),
                    metadata_json=json.dumps(metadata or {}),
                    created_at=now,
                    updated_at=now,
                )
                db_ver = CoworkArtifactVersion(
                    id=v1_id,
                    artifact_id=artifact_id,
                    version_number=1,
                    content=content,
                    diff_from_previous=None,
                    change_summary="Initial creation",
                    created_by="user",
                    created_at=now,
                )
                self.session.add(db_art)
                self.session.add(db_ver)
                await self.session.commit()
            except Exception:
                await self.session.rollback()

        res = copy.deepcopy(art)
        res["versions"] = [copy.deepcopy(v1)]
        return res

    async def get_artifact(self, user_id: str, artifact_id: str) -> dict[str, Any] | None:
        """Retrieve an artifact with all historical versions and diffs."""
        with _LOCK:
            art = _ARTIFACTS.get(artifact_id)
            if not art or art["user_id"] != user_id:
                return None
            res = copy.deepcopy(art)
            res["versions"] = copy.deepcopy(_VERSIONS.get(artifact_id, []))
            return res

    async def list_artifacts(
        self,
        user_id: str,
        task_id: str | None = None,
        session_id: str | None = None,
        artifact_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List artifacts belonging to user with optional filters."""
        with _LOCK:
            results: list[dict[str, Any]] = []
            for art in _ARTIFACTS.values():
                if art["user_id"] != user_id:
                    continue
                if task_id is not None and art.get("task_id") != task_id:
                    continue
                if session_id is not None and art.get("session_id") != session_id:
                    continue
                if artifact_type is not None and art.get("artifact_type") != artifact_type:
                    continue
                if status is not None and art.get("status") != status:
                    continue

                item = copy.deepcopy(art)
                item["versions_count"] = len(_VERSIONS.get(art["id"], []))
                results.append(item)

            # Sort descending by updated_at
            results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return results[offset : offset + limit]

    async def update_artifact(
        self,
        user_id: str,
        artifact_id: str,
        title: str | None = None,
        content: str | None = None,
        status: ArtifactStatus | None = None,
        change_summary: str = "Updated artifact content",
        created_by: str = "user",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Update artifact attributes and record a new historical version with diff."""
        now = datetime.now(UTC)
        with _LOCK:
            art = _ARTIFACTS.get(artifact_id)
            if not art or art["user_id"] != user_id:
                return None

            old_content = art["content"]
            new_content = content if content is not None else old_content

            diff_str = None
            if content is not None and content != old_content:
                diff_str, _, _ = compute_unified_diff(old_content, new_content, filename=art["title"])
                new_version_num = art["current_version"] + 1
                art["current_version"] = new_version_num
                art["content"] = new_content

                new_ver: dict[str, Any] = {
                    "id": f"ver-{uuid.uuid4().hex[:8]}",
                    "version_number": new_version_num,
                    "content": new_content,
                    "diff_from_previous": diff_str,
                    "change_summary": change_summary,
                    "created_by": created_by,
                    "created_at": now.isoformat(),
                }
                _VERSIONS.setdefault(artifact_id, []).append(new_ver)

            if title is not None:
                art["title"] = title
            if status is not None:
                art["status"] = str(status)
            if metadata is not None:
                art["metadata"].update(metadata)

            art["updated_at"] = now.isoformat()
            _save_to_disk()

        if self.session is not None:
            try:
                db_res = await self.session.execute(
                    select(CoworkArtifact).where(
                        CoworkArtifact.id == artifact_id, CoworkArtifact.user_id == user_id
                    )
                )
                db_art = db_res.scalar_one_or_none()
                if db_art:
                    if title is not None:
                        db_art.title = title
                    if content is not None:
                        db_art.content = content
                        db_art.current_version = art["current_version"]
                        db_ver = CoworkArtifactVersion(
                            id=f"ver-{uuid.uuid4().hex[:8]}",
                            artifact_id=artifact_id,
                            version_number=art["current_version"],
                            content=content,
                            diff_from_previous=diff_str,
                            change_summary=change_summary,
                            created_by=created_by,
                            created_at=now,
                        )
                        self.session.add(db_ver)
                    if status is not None:
                        db_art.status = str(status)
                    if metadata is not None:
                        db_art.metadata_json = json.dumps(art["metadata"])
                    db_art.updated_at = now
                    await self.session.commit()
            except Exception:
                await self.session.rollback()

        res = copy.deepcopy(art)
        res["versions"] = copy.deepcopy(_VERSIONS.get(artifact_id, []))
        return res

    async def revert_version(
        self,
        user_id: str,
        artifact_id: str,
        version_number: int,
    ) -> dict[str, Any] | None:
        """Revert artifact content to an earlier version number."""
        now = datetime.now(UTC)
        with _LOCK:
            art = _ARTIFACTS.get(artifact_id)
            if not art or art["user_id"] != user_id:
                return None

            versions = _VERSIONS.get(artifact_id, [])
            target_ver = next((v for v in versions if v["version_number"] == version_number), None)
            if not target_ver:
                return None

            old_content = art["content"]
            reverted_content = target_ver["content"]
            diff_str, _, _ = compute_unified_diff(old_content, reverted_content, filename=art["title"])

            new_version_num = art["current_version"] + 1
            art["current_version"] = new_version_num
            art["content"] = reverted_content
            art["updated_at"] = now.isoformat()

            revert_ver: dict[str, Any] = {
                "id": f"ver-{uuid.uuid4().hex[:8]}",
                "version_number": new_version_num,
                "content": reverted_content,
                "diff_from_previous": diff_str,
                "change_summary": f"Reverted to revision v{version_number}",
                "created_by": "user",
                "created_at": now.isoformat(),
            }
            versions.append(revert_ver)
            _save_to_disk()

            res = copy.deepcopy(art)
            res["versions"] = copy.deepcopy(versions)
            return res

    async def delete_artifact(self, user_id: str, artifact_id: str) -> bool:
        """Permanently delete an artifact and its historical versions."""
        with _LOCK:
            art = _ARTIFACTS.get(artifact_id)
            if not art or art["user_id"] != user_id:
                return False
            del _ARTIFACTS[artifact_id]
            _VERSIONS.pop(artifact_id, None)
            _save_to_disk()
            return True

    async def get_version_diff(
        self,
        user_id: str,
        artifact_id: str,
        from_v: int,
        to_v: int,
    ) -> dict[str, Any] | None:
        """Compute unified diff between two historical revisions."""
        with _LOCK:
            art = _ARTIFACTS.get(artifact_id)
            if not art or art["user_id"] != user_id:
                return None

            versions = _VERSIONS.get(artifact_id, [])
            v_from = next((v for v in versions if v["version_number"] == from_v), None)
            v_to = next((v for v in versions if v["version_number"] == to_v), None)
            if not v_from or not v_to:
                return None

            diff_str, additions, deletions = compute_unified_diff(
                v_from["content"],
                v_to["content"],
                filename=f"{art['title']}_v{from_v}_to_v{to_v}",
            )
            return {
                "artifact_id": artifact_id,
                "from_version": from_v,
                "to_version": to_v,
                "unified_diff": diff_str,
                "additions": additions,
                "deletions": deletions,
            }
