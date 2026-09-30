"""Workspace Hub and Project Management Service.

Orchestrates multi-tenant project lifecycles, task decomposition, document
attachments from Knowledge Vault, workspace metrics, and Central Tool Registry integration.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from app.projects.repository import ProjectRepository
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

logger = logging.getLogger(__name__)


class ProjectService:
    """Unified service for Workspace Hub projects, tasks, document links, and metrics."""

    _instance: ClassVar[ProjectService | None] = None

    def __init__(self, repository: ProjectRepository | None = None) -> None:
        self.repo = repository or ProjectRepository()

    @classmethod
    def get_instance(cls, repository: ProjectRepository | None = None) -> ProjectService:
        """Get or initialize singleton instance of ProjectService."""
        if cls._instance is None:
            cls._instance = cls(repository=repository)
        return cls._instance

    # -------------------------------------------------------------------------
    # Core Domain Delegations
    # -------------------------------------------------------------------------

    async def list_projects(
        self, user_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        """List all workspace projects for user with computed task counts."""
        return await self.repo.list_projects(user_id=user_id, status=status)

    async def get_project(
        self, user_id: str, project_id: str
    ) -> dict[str, Any] | None:
        """Get project details with associated tasks and document links."""
        return await self.repo.get_project(user_id=user_id, project_id=project_id)

    async def create_project(
        self, user_id: str, name: str, description: str = "", status: str = "active"
    ) -> dict[str, Any]:
        """Create a new project in the user's workspace."""
        return await self.repo.create_project(
            user_id=user_id,
            name=name,
            description=description,
            status=status,
        )

    async def update_project(
        self,
        user_id: str,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        """Update project metadata or status."""
        return await self.repo.update_project(
            user_id=user_id,
            project_id=project_id,
            name=name,
            description=description,
            status=status,
        )

    async def delete_project(self, user_id: str, project_id: str) -> bool:
        """Delete project with cascading purge of tasks and document attachments."""
        return await self.repo.delete_project(user_id=user_id, project_id=project_id)

    async def list_tasks(
        self,
        user_id: str,
        project_id: str,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[dict[str, Any]] | None:
        """List tasks belonging to a specific project with optional filtering."""
        tasks = await self.repo.list_tasks(user_id=user_id, project_id=project_id)
        if tasks is None:
            return None
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        if priority:
            tasks = [t for t in tasks if t.get("priority") == priority]
        return tasks

    async def create_task(
        self,
        user_id: str,
        project_id: str,
        title: str,
        description: str = "",
        status: str = "todo",
        priority: str = "medium",
        assigned_agent: str | None = None,
    ) -> dict[str, Any] | None:
        """Add a new task to a project."""
        return await self.repo.create_task(
            user_id=user_id,
            project_id=project_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assigned_agent=assigned_agent,
        )

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
        """Update a task's status, priority, or content."""
        return await self.repo.update_task(
            user_id=user_id,
            project_id=project_id,
            task_id=task_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assigned_agent=assigned_agent,
        )

    async def delete_task(
        self, user_id: str, project_id: str, task_id: str
    ) -> bool:
        """Delete a single task from a project."""
        return await self.repo.delete_task(
            user_id=user_id,
            project_id=project_id,
            task_id=task_id,
        )

    async def link_document(
        self,
        user_id: str,
        project_id: str,
        document_id: str,
        title: str,
        file_type: str = "document",
    ) -> dict[str, Any] | None:
        """Link a document from Knowledge Vault to a project."""
        return await self.repo.link_document(
            user_id=user_id,
            project_id=project_id,
            document_id=document_id,
            title=title,
            file_type=file_type,
        )

    async def unlink_document(
        self, user_id: str, project_id: str, doc_link_id: str
    ) -> bool:
        """Unlink a document from a project."""
        return await self.repo.unlink_document(
            user_id=user_id,
            project_id=project_id,
            doc_link_id=doc_link_id,
        )

    async def list_documents(
        self, user_id: str, project_id: str
    ) -> list[dict[str, Any]] | None:
        """List all documents attached to a project."""
        return await self.repo.list_documents(user_id=user_id, project_id=project_id)

    async def get_workspace_summary(self, user_id: str) -> dict[str, Any]:
        """Aggregate workspace progress, total projects, and task completion metrics."""
        projects = await self.repo.list_projects(user_id=user_id)
        total_projects = len(projects)
        active_projects = sum(1 for p in projects if p.get("status") == "active")
        completed_projects = sum(1 for p in projects if p.get("status") == "completed")
        total_tasks = sum(int(p.get("tasks_count", 0)) for p in projects)
        completed_tasks = sum(int(p.get("completed_count", 0)) for p in projects)
        completion_pct = round((completed_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0.0

        return {
            "user_id": user_id,
            "total_projects": total_projects,
            "active_projects": active_projects,
            "completed_projects": completed_projects,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "completion_percentage": completion_pct,
            "projects": projects,
            "summary": (
                f"Workspace overview: {total_projects} projects ({active_projects} active), "
                f"{completed_tasks}/{total_tasks} tasks completed ({completion_pct}%)."
            ),
        }

    # -------------------------------------------------------------------------
    # Central Tool Registry Registration
    # -------------------------------------------------------------------------

    def register_workspace_tools(self) -> None:
        """Register Workspace Hub and project management tools into the Central ToolRegistry."""
        reg = ToolRegistry.get_instance()

        async def _tool_workspace_list_projects(
            status: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            projects = await self.list_projects(user_id=uid, status=status)
            summary = await self.get_workspace_summary(user_id=uid)
            return {
                "user_id": uid,
                "total_projects": len(projects),
                "projects": projects,
                "summary": summary["summary"],
            }

        async def _tool_workspace_get_project(
            project_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            proj = await self.get_project(user_id=uid, project_id=project_id)
            if not proj:
                return {
                    "project_id": project_id,
                    "status": "not_found",
                    "error": f"Project '{project_id}' not found.",
                }
            return {
                "project_id": project_id,
                "status": "success",
                "project": proj,
            }

        async def _tool_workspace_create_project(
            name: str,
            description: str = "",
            status: str = "active",
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            new_proj = await self.create_project(
                user_id=uid,
                name=name.strip(),
                description=description.strip(),
                status=status.strip().lower(),
            )
            return {
                "status": "success",
                "project": new_proj,
                "summary": f"Created workspace project '{new_proj['name']}' (ID: {new_proj['id']}).",
            }

        async def _tool_workspace_create_task(
            project_id: str,
            title: str,
            description: str = "",
            status: str = "todo",
            priority: str = "medium",
            assigned_agent: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            task = await self.create_task(
                user_id=uid,
                project_id=project_id,
                title=title.strip(),
                description=description.strip(),
                status=status.strip().lower(),
                priority=priority.strip().lower(),
                assigned_agent=assigned_agent,
            )
            if not task:
                return {
                    "status": "error",
                    "error": f"Project '{project_id}' not found. Cannot add task.",
                }
            return {
                "status": "success",
                "task": task,
                "summary": f"Added task '{task['title']}' to project '{project_id}'.",
            }

        async def _tool_workspace_update_task(
            project_id: str,
            task_id: str,
            status: str | None = None,
            priority: str | None = None,
            title: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            updated = await self.update_task(
                user_id=uid,
                project_id=project_id,
                task_id=task_id,
                title=title,
                status=status,
                priority=priority,
            )
            if not updated:
                return {
                    "status": "error",
                    "error": f"Task '{task_id}' not found in project '{project_id}'.",
                }
            return {
                "status": "success",
                "task": updated,
                "summary": f"Updated task '{task_id}' status to '{updated.get('status')}'.",
            }

        async def _tool_workspace_link_document(
            project_id: str,
            document_id: str,
            title: str,
            file_type: str = "document",
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            doc_link = await self.link_document(
                user_id=uid,
                project_id=project_id,
                document_id=document_id,
                title=title,
                file_type=file_type,
            )
            if not doc_link:
                return {
                    "status": "error",
                    "error": f"Project '{project_id}' not found.",
                }
            return {
                "status": "success",
                "document": doc_link,
                "summary": f"Linked document '{title}' to project '{project_id}'.",
            }

        async def _tool_workspace_delete_project(
            project_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            deleted = await self.delete_project(user_id=uid, project_id=project_id)
            return {
                "project_id": project_id,
                "deleted": deleted,
                "status": "deleted" if deleted else "not_found",
                "message": (
                    f"Project '{project_id}' and all associated tasks deleted."
                    if deleted
                    else f"Project '{project_id}' not found."
                ),
            }

        # 1. workspace_list_projects
        reg.register(
            AgentTool(
                id="workspace_list_projects",
                name="List Workspace Projects",
                description=(
                    "List all workspace projects for the authenticated user with completion progress, "
                    "task counts, and status filtering."
                ),
                source=ToolSource.SYSTEM,
                capabilities=["workspace", "projects", "tasks", "management"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["all", "active", "completed", "archived"],
                            "description": "Optional project status filter",
                        },
                    },
                },
                permissions=["workspace:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_workspace_list_projects,
        )

        # 2. workspace_get_project
        reg.register(
            AgentTool(
                id="workspace_get_project",
                name="Get Workspace Project Details",
                description="Retrieve full details, task items, and linked documents for a specific workspace project.",
                source=ToolSource.SYSTEM,
                capabilities=["workspace", "projects", "details", "tasks"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Project ID to inspect"},
                    },
                    "required": ["project_id"],
                },
                permissions=["workspace:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_workspace_get_project,
        )

        # 3. workspace_create_project
        reg.register(
            AgentTool(
                id="workspace_create_project",
                name="Create Workspace Project",
                description="Create a new workspace project to track milestones, tasks, and deliverables.",
                source=ToolSource.SYSTEM,
                capabilities=["workspace", "projects", "create"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Project name or title"},
                        "description": {"type": "string", "description": "Project description or objective"},
                        "status": {"type": "string", "enum": ["active", "completed", "archived"], "default": "active"},
                    },
                    "required": ["name"],
                },
                permissions=["workspace:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_workspace_create_project,
        )

        # 4. workspace_create_task
        reg.register(
            AgentTool(
                id="workspace_create_task",
                name="Create Project Task",
                description="Add a new task item with status and priority to a project in the workspace hub.",
                source=ToolSource.SYSTEM,
                capabilities=["workspace", "tasks", "create", "todo"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Target project ID"},
                        "title": {"type": "string", "description": "Task title"},
                        "description": {"type": "string", "description": "Task description"},
                        "status": {"type": "string", "enum": ["todo", "in_progress", "done", "blocked"], "default": "todo"},
                        "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "default": "medium"},
                        "assigned_agent": {"type": "string", "description": "Optional assigned AI agent slug"},
                    },
                    "required": ["project_id", "title"],
                },
                permissions=["workspace:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_workspace_create_task,
        )

        # 5. workspace_update_task
        reg.register(
            AgentTool(
                id="workspace_update_task",
                name="Update Project Task Status",
                description="Update a task's status (todo, in_progress, done), priority, or title.",
                source=ToolSource.SYSTEM,
                capabilities=["workspace", "tasks", "update", "progress"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Project ID"},
                        "task_id": {"type": "string", "description": "Task ID"},
                        "status": {"type": "string", "enum": ["todo", "in_progress", "done", "blocked"]},
                        "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                        "title": {"type": "string", "description": "New task title"},
                    },
                    "required": ["project_id", "task_id"],
                },
                permissions=["workspace:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_workspace_update_task,
        )

        # 6. workspace_link_document
        reg.register(
            AgentTool(
                id="workspace_link_document",
                name="Link Document to Project",
                description="Link a Knowledge Vault research document or file to a workspace project.",
                source=ToolSource.SYSTEM,
                capabilities=["workspace", "documents", "vault", "link"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Target project ID"},
                        "document_id": {"type": "string", "description": "Document ID from Knowledge Vault"},
                        "title": {"type": "string", "description": "Document title"},
                        "file_type": {"type": "string", "default": "document"},
                    },
                    "required": ["project_id", "document_id", "title"],
                },
                permissions=["workspace:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_workspace_link_document,
        )

        # 7. workspace_delete_project
        reg.register(
            AgentTool(
                id="workspace_delete_project",
                name="Delete Workspace Project",
                description=(
                    "Permanently delete a workspace project along with all associated tasks and document links. "
                    "Requires human confirmation."
                ),
                source=ToolSource.SYSTEM,
                capabilities=["workspace", "projects", "delete"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "ID of project to delete"},
                    },
                    "required": ["project_id"],
                },
                permissions=["workspace:write"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
            ),
            _tool_workspace_delete_project,
        )
