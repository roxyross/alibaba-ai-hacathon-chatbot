"""ProjectRepository — SQLAlchemy async persistence with in-memory fallback for projects, tasks, and documents."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session_factory
from app.models.project import Project, ProjectDocument, ProjectTask

logger = logging.getLogger(__name__)

# Thread-safe in-memory stores for dev and test environments without DB connection
_MEM_PROJECTS: dict[str, list[dict[str, Any]]] = {}  # user_id -> list of project dicts
_MEM_TASKS: dict[str, list[dict[str, Any]]] = {}     # project_id -> list of task dicts
_MEM_DOCS: dict[str, list[dict[str, Any]]] = {}      # project_id -> list of doc link dicts


def clear_in_memory_stores() -> None:
    """Reset in-memory storage for test isolation."""
    _MEM_PROJECTS.clear()
    _MEM_TASKS.clear()
    _MEM_DOCS.clear()


class ProjectRepository:
    """Repository handling multi-tenant projects, tasks, and linked documents."""

    def __init__(self, session: AsyncSession | None = None) -> None:
        self._session = session

    def _get_factory(self) -> async_sessionmaker[AsyncSession] | None:
        if not os.environ.get("DATABASE_URL"):
            return None
        return get_session_factory()

    # -------------------------------------------------------------------------
    # Projects
    # -------------------------------------------------------------------------

    async def list_projects(
        self,
        user_id: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all workspace projects for user with computed task counts."""
        db_projects: list[dict[str, Any]] = []
        factory = self._get_factory()

        if factory is not None:
            try:
                async with factory() as db:
                    query = select(Project).where(Project.user_id == user_id)
                    if status and status != "all":
                        query = query.where(Project.status == status)
                    query = query.order_by(Project.updated_at.desc())

                    res = await db.execute(query)
                    orms = res.scalars().all()

                    for p in orms:
                        # Count tasks for this project
                        task_stmt = select(ProjectTask).where(
                            ProjectTask.project_id == p.id,
                            ProjectTask.user_id == user_id,
                        )
                        t_res = await db.execute(task_stmt)
                        tasks = t_res.scalars().all()
                        tasks_count = len(tasks)
                        completed_count = sum(1 for t in tasks if t.status == "done")

                        db_projects.append({
                            "id": p.id,
                            "name": p.name,
                            "description": p.description or "",
                            "status": p.status,
                            "last_updated": p.updated_at.strftime("%b %d, %Y") if p.updated_at else "Recently",
                            "tasks_count": tasks_count,
                            "completed_count": completed_count,
                        })
                    if db_projects or orms:
                        return db_projects
            except Exception as exc:
                logger.warning(f"DB list_projects failed: {exc}")

        # In-memory fallback
        user_projects = _MEM_PROJECTS.get(user_id, [])
        result = []
        for mem_p in user_projects:
            if status and status != "all" and mem_p["status"] != status:
                continue
            p_tasks = _MEM_TASKS.get(mem_p["id"], [])
            t_count = len(p_tasks)
            c_count = sum(1 for t in p_tasks if t["status"] == "done")
            result.append({
                **mem_p,
                "tasks_count": t_count,
                "completed_count": c_count,
            })
        return result

    async def get_project(
        self,
        user_id: str,
        project_id: str,
    ) -> dict[str, Any] | None:
        """Get full project details including tasks and linked documents."""
        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(Project).where(
                        Project.id == project_id,
                        Project.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    p = res.scalars().first()
                    if p:
                        # Fetch tasks
                        t_stmt = select(ProjectTask).where(
                            ProjectTask.project_id == project_id,
                            ProjectTask.user_id == user_id,
                        ).order_by(ProjectTask.created_at.asc())
                        t_res = await db.execute(t_stmt)
                        tasks = [
                            {
                                "id": t.id,
                                "project_id": t.project_id,
                                "title": t.title,
                                "description": t.description or "",
                                "status": t.status,
                                "priority": t.priority,
                                "assigned_agent": t.assigned_agent,
                                "due_date": t.due_date.isoformat() if t.due_date else None,
                                "created_at": t.created_at.isoformat() if t.created_at else None,
                            }
                            for t in t_res.scalars().all()
                        ]

                        # Fetch linked documents
                        d_stmt = select(ProjectDocument).where(
                            ProjectDocument.project_id == project_id,
                            ProjectDocument.user_id == user_id,
                        )
                        d_res = await db.execute(d_stmt)
                        docs = [
                            {
                                "id": d.id,
                                "project_id": d.project_id,
                                "document_id": d.document_id,
                                "title": d.title,
                                "file_type": d.file_type,
                                "created_at": d.created_at.isoformat() if d.created_at else None,
                            }
                            for d in d_res.scalars().all()
                        ]

                        tasks_count = len(tasks)
                        completed_count = sum(1 for t in tasks if t["status"] == "done")

                        return {
                            "id": p.id,
                            "name": p.name,
                            "description": p.description or "",
                            "status": p.status,
                            "last_updated": p.updated_at.strftime("%b %d, %Y") if p.updated_at else "Recently",
                            "tasks_count": tasks_count,
                            "completed_count": completed_count,
                            "tasks": tasks,
                            "documents": docs,
                        }
            except Exception as exc:
                logger.warning(f"DB get_project failed: {exc}")

        # In-memory store fallback
        user_projects = _MEM_PROJECTS.get(user_id, [])
        p_mem = next((p for p in user_projects if p["id"] == project_id), None)
        if not p_mem:
            return None

        p_tasks = _MEM_TASKS.get(project_id, [])
        p_docs = _MEM_DOCS.get(project_id, [])

        return {
            **p_mem,
            "tasks_count": len(p_tasks),
            "completed_count": sum(1 for t in p_tasks if t["status"] == "done"),
            "tasks": p_tasks,
            "documents": p_docs,
        }

    async def create_project(
        self,
        user_id: str,
        name: str,
        description: str = "",
        status: str = "active",
    ) -> dict[str, Any]:
        """Create a new workspace project."""
        proj_id = f"proj-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)

        proj_data = {
            "id": proj_id,
            "name": name,
            "description": description,
            "status": status,
            "last_updated": now.strftime("%b %d, %Y"),
            "tasks_count": 0,
            "completed_count": 0,
        }

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    orm_proj = Project(
                        id=proj_id,
                        user_id=user_id,
                        name=name,
                        description=description,
                        status=status,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(orm_proj)
                    await db.commit()
            except Exception as exc:
                logger.warning(f"DB create_project failed: {exc}")

        if user_id not in _MEM_PROJECTS:
            _MEM_PROJECTS[user_id] = []
        _MEM_PROJECTS[user_id].insert(0, proj_data)
        return proj_data

    async def update_project(
        self,
        user_id: str,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        """Update existing project details."""
        now = datetime.now(UTC)
        updated: dict[str, Any] | None = None

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(Project).where(
                        Project.id == project_id,
                        Project.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    orm_proj = res.scalars().first()
                    if orm_proj:
                        if name is not None:
                            orm_proj.name = name
                        if description is not None:
                            orm_proj.description = description
                        if status is not None:
                            orm_proj.status = status
                        orm_proj.updated_at = now
                        await db.commit()
                        updated = {
                            "id": orm_proj.id,
                            "name": orm_proj.name,
                            "description": orm_proj.description or "",
                            "status": orm_proj.status,
                            "last_updated": now.strftime("%b %d, %Y"),
                        }
            except Exception as exc:
                logger.warning(f"DB update_project failed: {exc}")

        user_projects = _MEM_PROJECTS.get(user_id, [])
        mem_proj = next((p for p in user_projects if p["id"] == project_id), None)
        if not mem_proj and not updated:
            return None

        if mem_proj:
            if name is not None:
                mem_proj["name"] = name
            if description is not None:
                mem_proj["description"] = description
            if status is not None:
                mem_proj["status"] = status
            mem_proj["last_updated"] = now.strftime("%b %d, %Y")
            if not updated:
                updated = mem_proj

        return updated

    async def delete_project(
        self,
        user_id: str,
        project_id: str,
    ) -> bool:
        """Delete project and cascade its tasks and documents."""
        deleted = False
        factory = self._get_factory()

        if factory is not None:
            try:
                async with factory() as db:
                    # Check ownership
                    stmt = select(Project).where(
                        Project.id == project_id,
                        Project.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    orm_proj = res.scalars().first()
                    if orm_proj:
                        # Cascade tasks
                        await db.execute(
                            delete(ProjectTask).where(ProjectTask.project_id == project_id)
                        )
                        # Cascade documents
                        await db.execute(
                            delete(ProjectDocument).where(ProjectDocument.project_id == project_id)
                        )
                        await db.delete(orm_proj)
                        await db.commit()
                        deleted = True
            except Exception as exc:
                logger.warning(f"DB delete_project failed: {exc}")

        user_projects = _MEM_PROJECTS.get(user_id, [])
        before = len(user_projects)
        _MEM_PROJECTS[user_id] = [p for p in user_projects if p["id"] != project_id]
        if len(_MEM_PROJECTS[user_id]) < before:
            deleted = True

        # Clean up associated memory stores
        _MEM_TASKS.pop(project_id, None)
        _MEM_DOCS.pop(project_id, None)

        return deleted

    # -------------------------------------------------------------------------
    # Tasks
    # -------------------------------------------------------------------------

    async def list_tasks(
        self,
        user_id: str,
        project_id: str,
    ) -> list[dict[str, Any]] | None:
        """List tasks for a project. Returns None if project not found or not owned."""
        proj = await self.get_project(user_id, project_id)
        if not proj:
            return None

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(ProjectTask).where(
                        ProjectTask.project_id == project_id,
                        ProjectTask.user_id == user_id,
                    ).order_by(ProjectTask.created_at.asc())
                    res = await db.execute(stmt)
                    return [
                        {
                            "id": t.id,
                            "project_id": t.project_id,
                            "title": t.title,
                            "description": t.description or "",
                            "status": t.status,
                            "priority": t.priority,
                            "assigned_agent": t.assigned_agent,
                            "due_date": t.due_date.isoformat() if t.due_date else None,
                            "created_at": t.created_at.isoformat() if t.created_at else None,
                        }
                        for t in res.scalars().all()
                    ]
            except Exception as exc:
                logger.warning(f"DB list_tasks failed: {exc}")

        return _MEM_TASKS.get(project_id, [])

    async def create_task(
        self,
        user_id: str,
        project_id: str,
        title: str,
        description: str = "",
        status: str = "todo",
        priority: str = "medium",
        assigned_agent: str | None = None,
        due_date: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Create a task for a project."""
        proj = await self.get_project(user_id, project_id)
        if not proj:
            return None

        task_id = f"task-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)

        task_data = {
            "id": task_id,
            "project_id": project_id,
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "assigned_agent": assigned_agent,
            "due_date": due_date.isoformat() if due_date else None,
            "created_at": now.isoformat(),
        }

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    orm_task = ProjectTask(
                        id=task_id,
                        project_id=project_id,
                        user_id=user_id,
                        title=title,
                        description=description,
                        status=status,
                        priority=priority,
                        assigned_agent=assigned_agent,
                        due_date=due_date,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(orm_task)
                    # Touch project updated_at
                    p_stmt = select(Project).where(Project.id == project_id)
                    p_res = await db.execute(p_stmt)
                    p = p_res.scalars().first()
                    if p:
                        p.updated_at = now
                    await db.commit()
            except Exception as exc:
                logger.warning(f"DB create_task failed: {exc}")

        if project_id not in _MEM_TASKS:
            _MEM_TASKS[project_id] = []
        _MEM_TASKS[project_id].append(task_data)

        # Update in-memory project timestamp
        user_projects = _MEM_PROJECTS.get(user_id, [])
        for mem_p in user_projects:
            if mem_p["id"] == project_id:
                mem_p["last_updated"] = now.strftime("%b %d, %Y")
                break

        return task_data

    async def update_task(
        self,
        user_id: str,
        project_id: str,
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        assigned_agent: str | None = None,
    ) -> dict[str, Any] | None:
        """Update task in project."""
        proj = await self.get_project(user_id, project_id)
        if not proj:
            return None

        now = datetime.now(UTC)
        updated: dict[str, Any] | None = None

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(ProjectTask).where(
                        ProjectTask.id == task_id,
                        ProjectTask.project_id == project_id,
                        ProjectTask.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    orm_task = res.scalars().first()
                    if orm_task:
                        if title is not None:
                            orm_task.title = title
                        if description is not None:
                            orm_task.description = description
                        if status is not None:
                            orm_task.status = status
                        if priority is not None:
                            orm_task.priority = priority
                        if assigned_agent is not None:
                            orm_task.assigned_agent = assigned_agent
                        orm_task.updated_at = now
                        await db.commit()
                        updated = {
                            "id": orm_task.id,
                            "project_id": orm_task.project_id,
                            "title": orm_task.title,
                            "description": orm_task.description or "",
                            "status": orm_task.status,
                            "priority": orm_task.priority,
                            "assigned_agent": orm_task.assigned_agent,
                            "due_date": orm_task.due_date.isoformat() if orm_task.due_date else None,
                            "created_at": orm_task.created_at.isoformat() if orm_task.created_at else None,
                        }
            except Exception as exc:
                logger.warning(f"DB update_task failed: {exc}")

        # In-memory store
        tasks = _MEM_TASKS.get(project_id, [])
        mem_task = next((t for t in tasks if t["id"] == task_id), None)
        if not mem_task and not updated:
            return None

        if mem_task:
            if title is not None:
                mem_task["title"] = title
            if description is not None:
                mem_task["description"] = description
            if status is not None:
                mem_task["status"] = status
            if priority is not None:
                mem_task["priority"] = priority
            if assigned_agent is not None:
                mem_task["assigned_agent"] = assigned_agent
            if not updated:
                updated = mem_task

        return updated

    async def delete_task(
        self,
        user_id: str,
        project_id: str,
        task_id: str,
    ) -> bool:
        """Delete task from project."""
        proj = await self.get_project(user_id, project_id)
        if not proj:
            return False

        deleted = False
        factory = self._get_factory()

        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(ProjectTask).where(
                        ProjectTask.id == task_id,
                        ProjectTask.project_id == project_id,
                        ProjectTask.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    t = res.scalars().first()
                    if t:
                        await db.delete(t)
                        await db.commit()
                        deleted = True
            except Exception as exc:
                logger.warning(f"DB delete_task failed: {exc}")

        tasks = _MEM_TASKS.get(project_id, [])
        before = len(tasks)
        _MEM_TASKS[project_id] = [t for t in tasks if t["id"] != task_id]
        if len(_MEM_TASKS[project_id]) < before:
            deleted = True

        return deleted

    # -------------------------------------------------------------------------
    # Documents
    # -------------------------------------------------------------------------

    async def list_documents(
        self,
        user_id: str,
        project_id: str,
    ) -> list[dict[str, Any]] | None:
        """List linked documents for project."""
        proj = await self.get_project(user_id, project_id)
        if not proj:
            return None

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(ProjectDocument).where(
                        ProjectDocument.project_id == project_id,
                        ProjectDocument.user_id == user_id,
                    ).order_by(ProjectDocument.created_at.desc())
                    res = await db.execute(stmt)
                    return [
                        {
                            "id": d.id,
                            "project_id": d.project_id,
                            "document_id": d.document_id,
                            "title": d.title,
                            "file_type": d.file_type,
                            "created_at": d.created_at.isoformat() if d.created_at else None,
                        }
                        for d in res.scalars().all()
                    ]
            except Exception as exc:
                logger.warning(f"DB list_documents failed: {exc}")

        return _MEM_DOCS.get(project_id, [])

    async def link_document(
        self,
        user_id: str,
        project_id: str,
        document_id: str,
        title: str,
        file_type: str = "document",
    ) -> dict[str, Any] | None:
        """Link a document to a project."""
        proj = await self.get_project(user_id, project_id)
        if not proj:
            return None

        doc_link_id = f"doclink-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)

        doc_data = {
            "id": doc_link_id,
            "project_id": project_id,
            "document_id": document_id,
            "title": title,
            "file_type": file_type,
            "created_at": now.isoformat(),
        }

        factory = self._get_factory()
        if factory is not None:
            try:
                async with factory() as db:
                    orm_doc = ProjectDocument(
                        id=doc_link_id,
                        project_id=project_id,
                        user_id=user_id,
                        document_id=document_id,
                        title=title,
                        file_type=file_type,
                        created_at=now,
                    )
                    db.add(orm_doc)
                    await db.commit()
            except Exception as exc:
                logger.warning(f"DB link_document failed: {exc}")

        if project_id not in _MEM_DOCS:
            _MEM_DOCS[project_id] = []
        _MEM_DOCS[project_id].append(doc_data)

        return doc_data

    async def unlink_document(
        self,
        user_id: str,
        project_id: str,
        doc_link_id: str,
    ) -> bool:
        """Unlink document from project."""
        proj = await self.get_project(user_id, project_id)
        if not proj:
            return False

        deleted = False
        factory = self._get_factory()

        if factory is not None:
            try:
                async with factory() as db:
                    stmt = select(ProjectDocument).where(
                        ProjectDocument.id == doc_link_id,
                        ProjectDocument.project_id == project_id,
                        ProjectDocument.user_id == user_id,
                    )
                    res = await db.execute(stmt)
                    d = res.scalars().first()
                    if d:
                        await db.delete(d)
                        await db.commit()
                        deleted = True
            except Exception as exc:
                logger.warning(f"DB unlink_document failed: {exc}")

        docs = _MEM_DOCS.get(project_id, [])
        before = len(docs)
        _MEM_DOCS[project_id] = [d for d in docs if d["id"] != doc_link_id]
        if len(_MEM_DOCS[project_id]) < before:
            deleted = True

        return deleted
