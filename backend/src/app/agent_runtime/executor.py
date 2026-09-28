"""Agent Runtime Executor for ROXY-AI 2.0.

Manages task lifecycles, step execution loops, permission checkpoints,
confirmation pauses, safe retries, deliverables generation, and event streaming.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any, AsyncGenerator

import structlog
from sqlalchemy import select

from app.actions.schemas import ActionCreateRequest
from app.actions.service import ActionService
from app.agent_runtime.planner import AgentPlanner
from app.agent_runtime.schemas import (
    StepStatusEnum,
    TaskCreateRequest,
    TaskProgressEvent,
    TaskResponse,
    TaskStatusEnum,
    TaskStepResponse,
)
from app.db import get_session_factory
from app.models.agent_runtime import AgentAction, AgentStep, AgentTask
from app.permissions.service import PermissionService
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest

log = structlog.get_logger()

# In-memory stores for testing and database-offline resilience
_MEM_TASKS: dict[str, dict[str, Any]] = {}
_MEM_STEPS: dict[str, list[dict[str, Any]]] = {}

# Active event queues for SSE streaming keyed by task_id
_EVENT_QUEUES: dict[str, list[asyncio.Queue[TaskProgressEvent]]] = {}


def clear_in_memory_tasks() -> None:
    """Clear in-memory tasks (for test isolation)."""
    _MEM_TASKS.clear()
    _MEM_STEPS.clear()
    _EVENT_QUEUES.clear()


class AgentExecutor:
    """Orchestrates end-to-end task execution with strict permission enforcement."""

    def __init__(self) -> None:
        self._planner = AgentPlanner()
        self._permission_service = PermissionService()
        self._action_service = ActionService()
        self._tool_registry = ToolRegistry.get_instance()
        self._mem_tasks = _MEM_TASKS
        self._mem_steps = _MEM_STEPS

    def _emit_event(
        self,
        task_id: str,
        status: str,
        milestone: str,
        message: str,
        step_number: int | None = None,
        tool_id: str | None = None,
        action_id: str | None = None,
    ) -> None:
        """Publish an action-level milestone progress event to active SSE streams."""
        evt = TaskProgressEvent(
            task_id=task_id,
            status=status,
            milestone=milestone,
            step_number=step_number,
            tool_id=tool_id,
            action_id=action_id,
            message=message,
            timestamp=datetime.now(UTC).isoformat(),
        )
        queues = _EVENT_QUEUES.get(task_id, [])
        for q in queues:
            try:
                q.put_nowait(evt)
            except Exception:
                pass

    async def subscribe_events(self, task_id: str) -> AsyncGenerator[TaskProgressEvent, None]:
        """Subscribe to real-time execution milestone events for a task."""
        q: asyncio.Queue[TaskProgressEvent] = asyncio.Queue()
        if task_id not in _EVENT_QUEUES:
            _EVENT_QUEUES[task_id] = []
        _EVENT_QUEUES[task_id].append(q)

        try:
            while True:
                evt = await q.get()
                yield evt
                if evt.status in (
                    TaskStatusEnum.COMPLETED.value,
                    TaskStatusEnum.FAILED.value,
                    TaskStatusEnum.CANCELLED.value,
                ):
                    break
        finally:
            if task_id in _EVENT_QUEUES and q in _EVENT_QUEUES[task_id]:
                _EVENT_QUEUES[task_id].remove(q)
                if not _EVENT_QUEUES[task_id]:
                    del _EVENT_QUEUES[task_id]

    async def create_task(self, user_id: str, req: TaskCreateRequest) -> TaskResponse:
        """Initialize an AgentTask with objective, context, and default status."""
        now = datetime.now(UTC)
        task_id = str(uuid.uuid4())
        title = req.title or (req.objective[:50] + "..." if len(req.objective) > 50 else req.objective)

        record_dict = {
            "id": task_id,
            "user_id": user_id,
            "workspace_id": req.workspace_id,
            "title": title,
            "objective": req.objective,
            "status": TaskStatusEnum.DRAFT.value,
            "plan": [],
            "context": req.context,
            "deliverables": [],
            "error": None,
            "steps": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": None,
        }

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    db_task = AgentTask(
                        id=task_id,
                        user_id=user_id,
                        workspace_id=req.workspace_id,
                        title=title,
                        objective=req.objective,
                        status=TaskStatusEnum.DRAFT.value,
                        created_at=now,
                        updated_at=now,
                    )
                    db_task.set_context(req.context)
                    session.add(db_task)
                    await session.commit()
            except Exception as exc:
                log.warning("agent_executor.db_create_failed", error=str(exc))

        self._mem_tasks[task_id] = record_dict
        self._mem_steps[task_id] = []

        if req.auto_run:
            return await self.run_task(user_id=user_id, task_id=task_id)

        return await self.get_task(user_id=user_id, task_id=task_id) or TaskResponse(**record_dict)

    async def get_task(self, user_id: str, task_id: str) -> TaskResponse | None:
        """Retrieve task details and associated execution steps."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(AgentTask).where(
                        AgentTask.id == task_id,
                        AgentTask.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    task = res.scalars().first()
                    if task:
                        # Fetch steps
                        steps_stmt = (
                            select(AgentStep)
                            .where(AgentStep.task_id == task_id)
                            .order_by(AgentStep.step_number.asc())
                        )
                        s_res = await session.execute(steps_stmt)
                        steps = s_res.scalars().all()
                        d = task.to_dict()
                        d["steps"] = [s.to_dict() for s in steps]
                        return TaskResponse(**d)
            except Exception as exc:
                log.warning("agent_executor.db_get_failed", error=str(exc))

        mem_task = self._mem_tasks.get(task_id)
        if mem_task and mem_task.get("user_id") == user_id:
            steps = self._mem_steps.get(task_id, [])
            d = dict(mem_task)
            d["steps"] = [TaskStepResponse(**s) for s in steps]
            return TaskResponse(**d)

        return None

    async def list_tasks(self, user_id: str, limit: int = 50) -> list[TaskResponse]:
        """List tasks for authenticated user."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = (
                        select(AgentTask)
                        .where(AgentTask.user_id == user_id)
                        .order_by(AgentTask.created_at.desc())
                        .limit(limit)
                    )
                    res = await session.execute(stmt)
                    tasks = res.scalars().all()
                    if tasks:
                        return [TaskResponse(**t.to_dict()) for t in tasks]
            except Exception as exc:
                log.warning("agent_executor.db_list_failed", error=str(exc))

        user_tasks = [t for t in self._mem_tasks.values() if t.get("user_id") == user_id]
        user_tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        results: list[TaskResponse] = []
        for t in user_tasks[:limit]:
            d = dict(t)
            d["steps"] = [TaskStepResponse(**s) for s in self._mem_steps.get(t["id"], [])]
            results.append(TaskResponse(**d))
        return results

    async def run_task(self, user_id: str, task_id: str) -> TaskResponse:
        """Run or resume an AgentTask through the verified operational flow."""
        task = await self.get_task(user_id=user_id, task_id=task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        # Ignore if cancelled
        if task.status == TaskStatusEnum.CANCELLED.value:
            return task

        now = datetime.now(UTC)

        # Phase 1: Planning (if not planned yet or draft)
        if task.status in (TaskStatusEnum.DRAFT.value, TaskStatusEnum.PLANNING.value) or not task.plan:
            self._update_task_state(task_id, TaskStatusEnum.PLANNING.value)
            self._emit_event(
                task_id=task_id,
                status=TaskStatusEnum.PLANNING.value,
                milestone="Understanding request",
                message="Analyzing objective and discovering available tools...",
            )

            plan = await self._planner.create_plan(
                objective=task.objective,
                context=task.context,
                user_id=user_id,
            )

            # Store plan and initialize step records
            steps_list: list[dict[str, Any]] = []
            for item in plan:
                step_id = str(uuid.uuid4())
                s_dict = {
                    "id": step_id,
                    "task_id": task_id,
                    "step_number": item["step_number"],
                    "description": item["description"],
                    "tool_id": item.get("tool_id"),
                    "tool_input": item.get("tool_input", {}),
                    "tool_output": None,
                    "status": StepStatusEnum.PENDING.value,
                    "error": None,
                    "created_at": now.isoformat(),
                    "started_at": None,
                    "finished_at": None,
                }
                steps_list.append(s_dict)

            self._save_plan_and_steps(task_id, plan, steps_list)
            task = await self.get_task(user_id=user_id, task_id=task_id)
            if not task:
                raise ValueError("Failed to retrieve updated task.")

        # Phase 2: Execution loop
        self._update_task_state(task_id, TaskStatusEnum.RUNNING.value)
        self._emit_event(
            task_id=task_id,
            status=TaskStatusEnum.RUNNING.value,
            milestone="Execution started",
            message=f"Beginning execution of {len(task.steps)} planned milestones.",
        )

        deliverables: list[dict[str, Any]] = list(task.deliverables)

        for step in task.steps:
            # Check if task was paused or cancelled by external call
            current_task = await self.get_task(user_id, task_id)
            if current_task and current_task.status in (TaskStatusEnum.PAUSED.value, TaskStatusEnum.CANCELLED.value):
                return current_task

            # Skip completed steps
            if step.status == StepStatusEnum.COMPLETED.value:
                continue

            # Step execution start
            self._update_step_state(task_id, step.id, StepStatusEnum.RUNNING.value, started_at=datetime.now(UTC))
            self._emit_event(
                task_id=task_id,
                status=TaskStatusEnum.RUNNING.value,
                milestone=f"Step {step.step_number}: In progress",
                step_number=step.step_number,
                tool_id=step.tool_id,
                message=f"Executing: {step.description}",
            )

            # If step uses a tool, run permission gate
            if step.tool_id:
                tool = self._tool_registry.get(step.tool_id)
                if not tool:
                    err = f"Tool '{step.tool_id}' is not registered."
                    self._update_step_state(task_id, step.id, StepStatusEnum.FAILED.value, error=err)
                    self._update_task_state(task_id, TaskStatusEnum.FAILED.value, error=err)
                    self._emit_event(
                        task_id=task_id,
                        status=TaskStatusEnum.FAILED.value,
                        milestone="Execution failed",
                        step_number=step.step_number,
                        message=err,
                    )
                    return await self.get_task(user_id, task_id)  # type: ignore

                # Permission evaluation
                perm_result = await self._permission_service.check_permission(
                    user_id=user_id,
                    tool_id=tool.id,
                )

                # Permission gate requires confirmation
                if perm_result.requires_confirmation:
                    # Enqueue an Action for user confirmation
                    action = await self._action_service.create_action(
                        user_id=user_id,
                        action_in=ActionCreateRequest(
                            tool_id=tool.id,
                            description=f"Run tool '{tool.name}' for step: {step.description}",
                            input_parameters=step.tool_input,
                            risk_level=tool.risk_level.value,
                            required_permission=tool.permissions[0] if tool.permissions else "execute",
                            task_id=task_id,
                            step_id=step.id,
                        ),
                    )
                    self._update_step_state(task_id, step.id, StepStatusEnum.WAITING_FOR_APPROVAL.value)
                    self._update_task_state(task_id, TaskStatusEnum.WAITING_FOR_PERMISSION.value)
                    self._emit_event(
                        task_id=task_id,
                        status=TaskStatusEnum.WAITING_FOR_PERMISSION.value,
                        milestone="Waiting for approval",
                        step_number=step.step_number,
                        tool_id=tool.id,
                        action_id=action.id,
                        message=f"Action '{tool.name}' requires user confirmation before proceeding.",
                    )
                    # Pause execution until approval card is acted upon
                    return await self.get_task(user_id, task_id)  # type: ignore

                # Permission denied
                if not perm_result.granted:
                    err = f"Permission denied: {perm_result.reason}"
                    self._update_step_state(task_id, step.id, StepStatusEnum.FAILED.value, error=err)
                    self._update_task_state(task_id, TaskStatusEnum.FAILED.value, error=err)
                    self._emit_event(
                        task_id=task_id,
                        status=TaskStatusEnum.FAILED.value,
                        milestone="Permission denied",
                        step_number=step.step_number,
                        message=err,
                    )
                    return await self.get_task(user_id, task_id)  # type: ignore

                # Permission granted -> Execute tool
                exec_req = ToolExecutionRequest(
                    tool_id=tool.id,
                    arguments=step.tool_input,
                    user_id=user_id,
                    task_id=task_id,
                    step_id=step.id,
                )
                exec_res = await self._tool_registry.execute(exec_req)

                if not exec_res.success:
                    err = f"Tool execution failed: {exec_res.error}"
                    self._update_step_state(task_id, step.id, StepStatusEnum.FAILED.value, error=err)
                    self._update_task_state(task_id, TaskStatusEnum.FAILED.value, error=err)
                    self._emit_event(
                        task_id=task_id,
                        status=TaskStatusEnum.FAILED.value,
                        milestone="Tool execution failed",
                        step_number=step.step_number,
                        message=err,
                    )
                    return await self.get_task(user_id, task_id)  # type: ignore

                # Verified execution success
                self._update_step_state(
                    task_id=task_id,
                    step_id=step.id,
                    status=StepStatusEnum.COMPLETED.value,
                    output=exec_res.output,
                    finished_at=datetime.now(UTC),
                )
                self._emit_event(
                    task_id=task_id,
                    status=TaskStatusEnum.RUNNING.value,
                    milestone=f"Step {step.step_number}: Completed",
                    step_number=step.step_number,
                    tool_id=tool.id,
                    message=f"Verified output received for '{tool.name}' ({exec_res.duration_ms}ms).",
                )
                deliverables.append({
                    "step_number": step.step_number,
                    "tool_id": tool.id,
                    "title": f"Result of {step.description}",
                    "data": exec_res.output,
                })
            else:
                # Step without tool (analysis/reasoning step)
                output = {"analysis": f"Completed analysis for: {step.description}"}
                self._update_step_state(
                    task_id=task_id,
                    step_id=step.id,
                    status=StepStatusEnum.COMPLETED.value,
                    output=output,
                    finished_at=datetime.now(UTC),
                )
                deliverables.append({
                    "step_number": step.step_number,
                    "title": step.description,
                    "data": output,
                })

        # All steps completed successfully
        self._update_task_state(
            task_id,
            TaskStatusEnum.COMPLETED.value,
            deliverables=deliverables,
            completed_at=datetime.now(UTC),
        )
        self._emit_event(
            task_id=task_id,
            status=TaskStatusEnum.COMPLETED.value,
            milestone="Task completed",
            message="All planned milestones executed and verified successfully.",
        )

        return await self.get_task(user_id, task_id)  # type: ignore

    async def pause_task(self, user_id: str, task_id: str) -> TaskResponse:
        """Pause a running task."""
        task = await self.get_task(user_id, task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")
        self._update_task_state(task_id, TaskStatusEnum.PAUSED.value)
        self._emit_event(
            task_id=task_id,
            status=TaskStatusEnum.PAUSED.value,
            milestone="Task paused",
            message="Task execution paused by user.",
        )
        return await self.get_task(user_id, task_id)  # type: ignore

    async def resume_task(self, user_id: str, task_id: str) -> TaskResponse:
        """Resume execution of a paused or waiting task."""
        task = await self.get_task(user_id, task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")
        return await self.run_task(user_id, task_id)

    async def cancel_task(self, user_id: str, task_id: str) -> TaskResponse:
        """Cancel a task and mark pending steps as skipped."""
        task = await self.get_task(user_id, task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        self._update_task_state(task_id, TaskStatusEnum.CANCELLED.value)
        for s in task.steps:
            if s.status in (StepStatusEnum.PENDING.value, StepStatusEnum.RUNNING.value, StepStatusEnum.WAITING_FOR_APPROVAL.value):
                self._update_step_state(task_id, s.id, StepStatusEnum.SKIPPED.value)

        self._emit_event(
            task_id=task_id,
            status=TaskStatusEnum.CANCELLED.value,
            milestone="Task cancelled",
            message="Task was cancelled by user.",
        )
        return await self.get_task(user_id, task_id)  # type: ignore

    async def retry_task(self, user_id: str, task_id: str) -> TaskResponse:
        """Reset failed or skipped steps and re-run task."""
        task = await self.get_task(user_id, task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        # Reset failed steps to pending
        for s in task.steps:
            if s.status in (StepStatusEnum.FAILED.value, StepStatusEnum.SKIPPED.value):
                self._update_step_state(task_id, s.id, StepStatusEnum.PENDING.value, error=None)

        self._update_task_state(task_id, TaskStatusEnum.RUNNING.value, error=None)
        return await self.run_task(user_id, task_id)

    def _save_plan_and_steps(
        self,
        task_id: str,
        plan: list[dict[str, Any]],
        steps: list[dict[str, Any]],
    ) -> None:
        """Persist plan and step models to database and in-memory cache."""
        factory = get_session_factory()
        if factory is not None:
            try:
                # We perform an async background or direct sync write if loop allows
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._async_db_save_plan(task_id, plan, steps))
            except Exception as exc:
                log.warning("agent_executor.db_plan_save_async_err", error=str(exc))

        if task_id in self._mem_tasks:
            self._mem_tasks[task_id]["plan"] = plan
            self._mem_tasks[task_id]["updated_at"] = datetime.now(UTC).isoformat()
        self._mem_steps[task_id] = steps

    async def _async_db_save_plan(
        self,
        task_id: str,
        plan: list[dict[str, Any]],
        steps: list[dict[str, Any]],
    ) -> None:
        factory = get_session_factory()
        if factory is None:
            return
        try:
            async with factory() as session:
                stmt = select(AgentTask).where(AgentTask.id == task_id)
                res = await session.execute(stmt)
                db_task = res.scalars().first()
                if db_task:
                    db_task.set_plan(plan)
                    for s in steps:
                        db_step = AgentStep(
                            id=s["id"],
                            task_id=task_id,
                            step_number=s["step_number"],
                            description=s["description"],
                            tool_id=s["tool_id"],
                            status=s["status"],
                        )
                        db_step.set_tool_input(s.get("tool_input", {}))
                        session.add(db_step)
                    await session.commit()
        except Exception as exc:
            log.warning("agent_executor.async_db_save_plan_failed", error=str(exc))

    def _update_task_state(
        self,
        task_id: str,
        status: str,
        error: str | None = None,
        deliverables: list[dict[str, Any]] | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        """Update task status in DB and memory."""
        now_iso = datetime.now(UTC).isoformat()
        if task_id in self._mem_tasks:
            self._mem_tasks[task_id]["status"] = status
            self._mem_tasks[task_id]["updated_at"] = now_iso
            if error is not None:
                self._mem_tasks[task_id]["error"] = error
            if deliverables is not None:
                self._mem_tasks[task_id]["deliverables"] = deliverables
            if completed_at is not None:
                self._mem_tasks[task_id]["completed_at"] = completed_at.isoformat()

        factory = get_session_factory()
        if factory is not None:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(
                        self._async_db_update_task(task_id, status, error, deliverables, completed_at)
                    )
            except Exception:
                pass

    async def _async_db_update_task(
        self,
        task_id: str,
        status: str,
        error: str | None,
        deliverables: list[dict[str, Any]] | None,
        completed_at: datetime | None,
    ) -> None:
        factory = get_session_factory()
        if not factory:
            return
        try:
            async with factory() as session:
                stmt = select(AgentTask).where(AgentTask.id == task_id)
                res = await session.execute(stmt)
                db_task = res.scalars().first()
                if db_task:
                    db_task.status = status
                    db_task.updated_at = datetime.now(UTC)
                    if error is not None:
                        db_task.error = error
                    if deliverables is not None:
                        db_task.set_deliverables(deliverables)
                    if completed_at is not None:
                        db_task.completed_at = completed_at
                    await session.commit()
        except Exception as exc:
            log.warning("agent_executor.async_update_task_failed", error=str(exc))

    def _update_step_state(
        self,
        task_id: str,
        step_id: str,
        status: str,
        output: Any = None,
        error: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        """Update step status in memory and DB."""
        if task_id in self._mem_steps:
            for s in self._mem_steps[task_id]:
                if s["id"] == step_id:
                    s["status"] = status
                    if output is not None:
                        s["tool_output"] = output
                    if error is not None:
                        s["error"] = error
                    if started_at is not None:
                        s["started_at"] = started_at.isoformat()
                    if finished_at is not None:
                        s["finished_at"] = finished_at.isoformat()
                    break

        factory = get_session_factory()
        if factory is not None:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(
                        self._async_db_update_step(step_id, status, output, error, started_at, finished_at)
                    )
            except Exception:
                pass

    async def _async_db_update_step(
        self,
        step_id: str,
        status: str,
        output: Any,
        error: str | None,
        started_at: datetime | None,
        finished_at: datetime | None,
    ) -> None:
        factory = get_session_factory()
        if not factory:
            return
        try:
            async with factory() as session:
                stmt = select(AgentStep).where(AgentStep.id == step_id)
                res = await session.execute(stmt)
                db_step = res.scalars().first()
                if db_step:
                    db_step.status = status
                    if output is not None:
                        db_step.set_tool_output(output)
                    if error is not None:
                        db_step.error = error
                    if started_at is not None:
                        db_step.started_at = started_at
                    if finished_at is not None:
                        db_step.finished_at = finished_at
                    await session.commit()
        except Exception as exc:
            log.warning("agent_executor.async_update_step_failed", error=str(exc))
