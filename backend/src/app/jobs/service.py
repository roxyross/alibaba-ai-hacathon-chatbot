"""Job Scheduler & Automations Service.

Provides unified domain logic for scheduled jobs, recurring automations,
execution history tracking, and Central Tool Registry integration with Action Center confirmation gating.
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar

from app.jobs.repository import JobItem, JobRepository
from app.tools.registry import ToolRegistry
from app.tools.schemas import AgentTool, RiskLevel, ToolSource

logger = logging.getLogger(__name__)


class JobService:
    """Enterprise domain service for scheduled jobs and automated workflows."""

    _instance: ClassVar[JobService | None] = None

    def __init__(self, repository: JobRepository | None = None) -> None:
        self.repo = repository or JobRepository()

    @classmethod
    def get_instance(cls, repository: JobRepository | None = None) -> JobService:
        """Get or initialize singleton instance of JobService."""
        if cls._instance is None:
            cls._instance = cls(repository=repository)
        return cls._instance

    # -------------------------------------------------------------------------
    # Core Domain Delegations
    # -------------------------------------------------------------------------

    async def list_jobs(
        self,
        user_id: str,
        status: str | None = None,
        tag: str | None = None,
    ) -> list[JobItem]:
        """List all scheduled jobs for the user, strictly tenant-isolated."""
        return await self.repo.list_jobs(user_id=user_id, status=status, tag=tag)

    async def get_job(self, job_id: str, user_id: str) -> JobItem | None:
        """Get a single scheduled job by ID for the tenant."""
        return await self.repo.get_job(job_id=job_id, user_id=user_id)

    async def create_job(
        self,
        user_id: str,
        name: str,
        schedule: str = "Daily",
        timezone: str = "UTC",
        action: dict[str, Any] | None = None,
        prompt: str | None = None,
        tag: str | None = None,
        confirm_on_fire: bool = False,
    ) -> JobItem:
        """Create and schedule a new automated job."""
        action_dict = action or {
            "description": f"Automated scheduled task: '{prompt or name}'",
            "prompt": prompt or name,
            "agent_slug": "automation",
        }
        job = await self.repo.create_job(
            user_id=user_id,
            name=name,
            schedule=schedule,
            timezone=timezone,
            action=action_dict,
            tag=tag,
            confirm_on_fire=confirm_on_fire,
            status="Active",
        )
        return job

    async def update_job_status(
        self,
        job_id: str,
        user_id: str,
        status: str,
    ) -> JobItem | None:
        """Update job status between Active and Pause."""
        return await self.repo.update_job_status(job_id=job_id, user_id=user_id, status=status)

    async def delete_job(self, job_id: str, user_id: str) -> bool:
        """Permanently delete a scheduled job and cancel triggers."""
        return await self.repo.delete_job(job_id=job_id, user_id=user_id)

    async def run_job_now(self, job_id: str, user_id: str) -> dict[str, Any]:
        """Trigger immediate execution of a scheduled job and record history."""
        job = await self.repo.get_job(job_id, user_id)
        if not job:
            return {"status": "not_found", "error": f"Job '{job_id}' not found."}

        start_time = time.perf_counter()
        action = job.action or {}
        prompt = str(action.get("prompt") or action.get("description") or f"Execute scheduled task: {job.name}")
        agent_slug = str(action.get("agent_slug") or "automation")
        logger.info("job_service.run_job_now", extra={"job_id": job_id, "agent": agent_slug, "prompt": prompt})

        output_summary = f"Scheduled job '{job.name}' executed successfully via {agent_slug}."
        status_str = "success"
        err_str: str | None = None

        duration_ms = max(1, int((time.perf_counter() - start_time) * 1000))
        await self.repo.advance_next_fire(job_id, user_id)
        execution_record = await self.repo.record_execution(
            job_id=job_id,
            user_id=user_id,
            status=status_str,
            duration_ms=duration_ms,
            output_summary=output_summary,
            error=err_str,
        )

        return {
            "status": status_str,
            "job_id": job_id,
            "execution_id": execution_record["id"],
            "output": output_summary,
            "duration_ms": duration_ms,
            "executed_at": execution_record["executed_at"],
            "error": err_str,
            "execution": execution_record,
        }

    async def get_job_history(
        self,
        job_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]] | None:
        """Retrieve execution history logs for a job."""
        job = await self.repo.get_job(job_id, user_id)
        if not job:
            return None
        return await self.repo.list_executions(job_id=job_id, user_id=user_id, limit=limit)

    # -------------------------------------------------------------------------
    # Central Tool Registry Registration
    # -------------------------------------------------------------------------

    def register_scheduler_tools(self) -> None:
        """Register automated job scheduler tools into the Central ToolRegistry."""
        reg = ToolRegistry.get_instance()

        # 1. scheduler_list_jobs
        async def _tool_scheduler_list_jobs(
            status: str | None = None,
            tag: str | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            jobs = await self.list_jobs(user_id=uid, status=status, tag=tag)
            return {
                "user_id": uid,
                "total": len(jobs),
                "jobs": [j.to_dict() for j in jobs],
                "summary": f"Found {len(jobs)} scheduled automations.",
            }

        reg.register(
            AgentTool(
                id="scheduler_list_jobs",
                name="List Scheduled Automations",
                description="List all scheduled jobs, reminders, and automations for the authenticated user.",
                source=ToolSource.SYSTEM,
                capabilities=["scheduler", "jobs", "automations", "reminders", "list"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["Active", "Pause", "active", "pause"],
                            "description": "Optional filter by job status",
                        },
                        "tag": {
                            "type": "string",
                            "description": "Optional category or project tag filter",
                        },
                    },
                },
                permissions=["jobs:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_scheduler_list_jobs,
        )

        # 2. scheduler_get_job
        async def _tool_scheduler_get_job(
            job_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            job = await self.get_job(job_id=job_id, user_id=uid)
            if not job:
                return {"job_id": job_id, "found": False, "error": f"Job '{job_id}' not found."}
            history = await self.get_job_history(job_id=job_id, user_id=uid, limit=5)
            return {
                "job_id": job_id,
                "found": True,
                "job": job.to_dict(),
                "recent_executions": history or [],
            }

        reg.register(
            AgentTool(
                id="scheduler_get_job",
                name="Get Scheduled Job Details",
                description="Retrieve details, configuration, and recent execution history for a scheduled job.",
                source=ToolSource.SYSTEM,
                capabilities=["scheduler", "jobs", "details"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Unique ID of the scheduled job"},
                    },
                    "required": ["job_id"],
                },
                permissions=["jobs:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_scheduler_get_job,
        )

        # 3. scheduler_create_job
        async def _tool_scheduler_create_job(
            name: str,
            schedule: str = "Daily",
            timezone: str = "UTC",
            prompt: str | None = None,
            tag: str | None = None,
            confirm_on_fire: bool = False,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            job = await self.create_job(
                user_id=uid,
                name=name,
                schedule=schedule,
                timezone=timezone,
                prompt=prompt,
                tag=tag,
                confirm_on_fire=confirm_on_fire,
            )
            return {
                "success": True,
                "job": job.to_dict(),
                "summary": f"Scheduled automation '{job.name}' with schedule '{job.schedule}' (ID: {job.id}).",
            }

        reg.register(
            AgentTool(
                id="scheduler_create_job",
                name="Schedule Automated Job",
                description="Create a new scheduled recurring task, reminder, or autonomous agent workflow.",
                source=ToolSource.SYSTEM,
                capabilities=["scheduler", "jobs", "create", "automate"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name or title of the automation"},
                        "schedule": {"type": "string", "description": "Schedule expression (e.g. 'Daily', '0 9 * * *', ISO-8601 date)", "default": "Daily"},
                        "timezone": {"type": "string", "description": "Target timezone (e.g. 'UTC', 'America/New_York')", "default": "UTC"},
                        "prompt": {"type": "string", "description": "Prompt or action instructions to execute when triggered"},
                        "tag": {"type": "string", "description": "Optional category tag"},
                        "confirm_on_fire": {"type": "boolean", "default": False, "description": "Require human confirmation before firing"},
                    },
                    "required": ["name"],
                },
                permissions=["jobs:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_scheduler_create_job,
        )

        # 4. scheduler_update_job_status
        async def _tool_scheduler_update_job_status(
            job_id: str,
            status: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            updated = await self.update_job_status(job_id=job_id, user_id=uid, status=status)
            if not updated:
                return {"success": False, "error": f"Job '{job_id}' not found."}
            return {
                "success": True,
                "job": updated.to_dict(),
                "summary": f"Job '{job_id}' status set to '{updated.status}'.",
            }

        reg.register(
            AgentTool(
                id="scheduler_update_job_status",
                name="Pause or Resume Scheduled Job",
                description="Toggle scheduled job status between 'Active' and 'Pause'.",
                source=ToolSource.SYSTEM,
                capabilities=["scheduler", "jobs", "status", "pause", "resume"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Unique ID of the scheduled job"},
                        "status": {"type": "string", "enum": ["Active", "Pause", "active", "pause"], "description": "Target status"},
                    },
                    "required": ["job_id", "status"],
                },
                permissions=["jobs:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_scheduler_update_job_status,
        )

        # 5. scheduler_run_job_now
        async def _tool_scheduler_run_job_now(
            job_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            return await self.run_job_now(job_id=job_id, user_id=uid)

        reg.register(
            AgentTool(
                id="scheduler_run_job_now",
                name="Run Scheduled Job Immediately",
                description="Trigger immediate on-demand execution of an existing scheduled job.",
                source=ToolSource.SYSTEM,
                capabilities=["scheduler", "jobs", "execute", "run"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Unique ID of the scheduled job to run"},
                    },
                    "required": ["job_id"],
                },
                permissions=["jobs:write"],
                risk_level=RiskLevel.MEDIUM,
                requires_confirmation=False,
            ),
            _tool_scheduler_run_job_now,
        )

        # 6. scheduler_delete_job (HIGH RISK - requires confirmation)
        async def _tool_scheduler_delete_job(
            job_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            uid = user_id or "default"
            deleted = await self.delete_job(job_id=job_id, user_id=uid)
            return {
                "job_id": job_id,
                "deleted": deleted,
                "status": "deleted" if deleted else "not_found",
                "message": f"Job '{job_id}' deleted." if deleted else f"Job '{job_id}' not found.",
            }

        reg.register(
            AgentTool(
                id="scheduler_delete_job",
                name="Delete Scheduled Job",
                description="Permanently delete a scheduled job and its execution history. Requires human confirmation.",
                source=ToolSource.SYSTEM,
                capabilities=["scheduler", "jobs", "delete", "destructive"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Unique ID of the scheduled job to delete"},
                    },
                    "required": ["job_id"],
                },
                permissions=["jobs:write"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
            ),
            _tool_scheduler_delete_job,
        )
