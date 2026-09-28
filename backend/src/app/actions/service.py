"""Action Center service for ROXY-AI 2.0.

Manages confirmation queues, approvals, rejections, parameter adjustments,
and verified post-approval tool execution.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.actions.schemas import (
    ActionCreateRequest,
    ActionResponse,
    ActionStatus,
)
from app.db import get_session_factory
from app.models.agent_runtime import AgentAction, AgentStep, AgentTask
from app.tools.registry import ToolRegistry
from app.tools.schemas import ToolExecutionRequest

log = structlog.get_logger()

# Thread-safe in-memory cache / fallback store keyed by action_id
_MEM_ACTIONS: dict[str, dict[str, Any]] = {}


def clear_in_memory_actions() -> None:
    """Clear in-memory actions (for test isolation)."""
    _MEM_ACTIONS.clear()


class ActionService:
    """Coordinates confirmation lifecycle and executing approved system actions."""

    def __init__(self) -> None:
        self._mem = _MEM_ACTIONS
        self._tool_registry = ToolRegistry.get_instance()

    async def create_action(
        self,
        user_id: str,
        action_in: ActionCreateRequest,
    ) -> ActionResponse:
        """Enqueue a new action requiring user approval."""
        now = datetime.now(UTC)
        action_id = str(uuid.uuid4())
        record_dict = {
            "id": action_id,
            "user_id": user_id,
            "task_id": action_in.task_id,
            "step_id": action_in.step_id,
            "tool_id": action_in.tool_id,
            "description": action_in.description,
            "input_parameters": action_in.input_parameters,
            "risk_level": action_in.risk_level,
            "required_permission": action_in.required_permission,
            "status": ActionStatus.PENDING.value,
            "result": None,
            "error": None,
            "created_at": now.isoformat(),
            "resolved_at": None,
        }

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    db_action = AgentAction(
                        id=action_id,
                        user_id=user_id,
                        task_id=action_in.task_id,
                        step_id=action_in.step_id,
                        tool_id=action_in.tool_id,
                        description=action_in.description,
                        risk_level=action_in.risk_level,
                        required_permission=action_in.required_permission,
                        status=ActionStatus.PENDING.value,
                        created_at=now,
                    )
                    db_action.set_input_parameters(action_in.input_parameters)
                    session.add(db_action)
                    await session.commit()
                    return ActionResponse(**db_action.to_dict())
            except Exception as exc:
                log.warning("action_service.db_create_failed", error=str(exc))

        self._mem[action_id] = record_dict
        return ActionResponse(**record_dict)

    async def get_action(self, user_id: str, action_id: str) -> ActionResponse | None:
        """Fetch action details ensuring multi-tenant isolation."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(AgentAction).where(
                        AgentAction.id == action_id,
                        AgentAction.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        return ActionResponse(**item.to_dict())
            except Exception as exc:
                log.warning("action_service.db_get_failed", error=str(exc))

        mem_item = self._mem.get(action_id)
        if mem_item and mem_item.get("user_id") == user_id:
            return ActionResponse(**mem_item)
        return None

    async def list_pending_actions(self, user_id: str) -> list[ActionResponse]:
        """List all pending actions waiting for confirmation."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = (
                        select(AgentAction)
                        .where(
                            AgentAction.user_id == user_id,
                            AgentAction.status == ActionStatus.PENDING.value,
                        )
                        .order_by(AgentAction.created_at.desc())
                    )
                    res = await session.execute(stmt)
                    rows = res.scalars().all()
                    if rows:
                        return [ActionResponse(**r.to_dict()) for r in rows]
            except Exception as exc:
                log.warning("action_service.db_list_pending_failed", error=str(exc))

        return [
            ActionResponse(**a)
            for a in self._mem.values()
            if a.get("user_id") == user_id and a.get("status") == ActionStatus.PENDING.value
        ]

    async def list_action_history(self, user_id: str, limit: int = 50) -> list[ActionResponse]:
        """List resolved action history."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = (
                        select(AgentAction)
                        .where(AgentAction.user_id == user_id)
                        .order_by(AgentAction.created_at.desc())
                        .limit(limit)
                    )
                    res = await session.execute(stmt)
                    rows = res.scalars().all()
                    if rows:
                        return [ActionResponse(**r.to_dict()) for r in rows]
            except Exception as exc:
                log.warning("action_service.db_list_history_failed", error=str(exc))

        user_actions = [a for a in self._mem.values() if a.get("user_id") == user_id]
        user_actions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return [ActionResponse(**a) for a in user_actions[:limit]]

    async def edit_action_params(
        self,
        user_id: str,
        action_id: str,
        new_params: dict[str, Any],
    ) -> ActionResponse:
        """Update arguments of a pending action before user approves it."""
        action = await self.get_action(user_id, action_id)
        if not action:
            raise ValueError(f"Action '{action_id}' not found.")
        if action.status != ActionStatus.PENDING.value:
            raise ValueError(f"Cannot edit action with status '{action.status}'.")

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(AgentAction).where(
                        AgentAction.id == action_id,
                        AgentAction.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        item.set_input_parameters(new_params)
                        await session.commit()
                        return ActionResponse(**item.to_dict())
            except Exception as exc:
                log.warning("action_service.db_edit_failed", error=str(exc))

        if action_id in self._mem:
            self._mem[action_id]["input_parameters"] = new_params
            return ActionResponse(**self._mem[action_id])

        raise ValueError(f"Action '{action_id}' could not be updated.")

    async def approve_action(
        self,
        user_id: str,
        action_id: str,
    ) -> ActionResponse:
        """Approve pending action and immediately trigger sandboxed execution."""
        action = await self.get_action(user_id, action_id)
        if not action:
            raise ValueError(f"Action '{action_id}' not found.")
        if action.status != ActionStatus.PENDING.value:
            raise ValueError(f"Action '{action_id}' is already {action.status}.")

        now = datetime.now(UTC)

        # Execute via central ToolRegistry
        exec_request = ToolExecutionRequest(
            tool_id=action.tool_id,
            arguments=action.input_parameters,
            user_id=user_id,
            task_id=action.task_id,
            step_id=action.step_id,
        )
        exec_result = await self._tool_registry.execute(exec_request)

        final_status = ActionStatus.EXECUTED.value if exec_result.success else ActionStatus.FAILED.value
        output_data = exec_result.output if exec_result.success else None
        err_msg = exec_result.error if not exec_result.success else None

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(AgentAction).where(
                        AgentAction.id == action_id,
                        AgentAction.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        item.status = final_status
                        item.set_result(output_data)
                        item.error = err_msg
                        item.resolved_at = now

                        # If linked to a step, update the step
                        if item.step_id:
                            step_stmt = select(AgentStep).where(AgentStep.id == item.step_id)
                            step_res = await session.execute(step_stmt)
                            step = step_res.scalars().first()
                            if step:
                                step.status = "completed" if exec_result.success else "failed"
                                step.set_tool_output(output_data or {"error": err_msg})
                                step.finished_at = now
                                if not exec_result.success:
                                    step.error = err_msg

                            if item.task_id:
                                task_stmt = select(AgentTask).where(AgentTask.id == item.task_id)
                                task_res = await session.execute(task_stmt)
                                db_t = task_res.scalars().first()
                                if db_t:
                                    all_steps_stmt = select(AgentStep).where(AgentStep.task_id == item.task_id)
                                    all_steps_res = await session.execute(all_steps_stmt)
                                    all_steps = all_steps_res.scalars().all()
                                    if all_steps and all(st.status == "completed" for st in all_steps):
                                        db_t.status = "completed"
                                        db_t.completed_at = now
                                    elif any(st.status == "failed" for st in all_steps):
                                        db_t.status = "failed"
                                    else:
                                        db_t.status = "running"

                        await session.commit()
                        return ActionResponse(**item.to_dict())
            except Exception as exc:
                log.warning("action_service.db_approve_failed", error=str(exc))

        # In-memory sync for step and task
        if action.task_id and action.step_id:
            try:
                from app.agent_runtime.executor import _MEM_STEPS, _MEM_TASKS
                if action.task_id in _MEM_STEPS:
                    for s in _MEM_STEPS[action.task_id]:
                        if s["id"] == action.step_id:
                            s["status"] = "completed" if exec_result.success else "failed"
                            s["tool_output"] = output_data or {"error": err_msg}
                            s["finished_at"] = now.isoformat()
                            if not exec_result.success:
                                s["error"] = err_msg
                            break
                    all_s = _MEM_STEPS[action.task_id]
                    if action.task_id in _MEM_TASKS:
                        if all_s and all(st.get("status") == "completed" for st in all_s):
                            _MEM_TASKS[action.task_id]["status"] = "completed"
                            _MEM_TASKS[action.task_id]["completed_at"] = now.isoformat()
                        elif any(st.get("status") == "failed" for st in all_s):
                            _MEM_TASKS[action.task_id]["status"] = "failed"
                        else:
                            _MEM_TASKS[action.task_id]["status"] = "running"
            except Exception:
                pass

        # In-memory update
        if action_id in self._mem:
            self._mem[action_id]["status"] = final_status
            self._mem[action_id]["result"] = output_data
            self._mem[action_id]["error"] = err_msg
            self._mem[action_id]["resolved_at"] = now.isoformat()
            return ActionResponse(**self._mem[action_id])

        return ActionResponse(
            id=action_id,
            user_id=user_id,
            task_id=action.task_id,
            step_id=action.step_id,
            tool_id=action.tool_id,
            description=action.description,
            input_parameters=action.input_parameters,
            risk_level=action.risk_level,
            required_permission=action.required_permission,
            status=final_status,
            result=output_data,
            error=err_msg,
            created_at=action.created_at,
            resolved_at=now.isoformat(),
        )

    async def reject_action(
        self,
        user_id: str,
        action_id: str,
        reason: str | None = None,
    ) -> ActionResponse:
        """Reject a pending action request."""
        action = await self.get_action(user_id, action_id)
        if not action:
            raise ValueError(f"Action '{action_id}' not found.")
        if action.status != ActionStatus.PENDING.value:
            raise ValueError(f"Cannot reject action with status '{action.status}'.")

        now = datetime.now(UTC)
        err_msg = reason or "Action was rejected by user."

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(AgentAction).where(
                        AgentAction.id == action_id,
                        AgentAction.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    item = res.scalars().first()
                    if item:
                        item.status = ActionStatus.REJECTED.value
                        item.error = err_msg
                        item.resolved_at = now

                        if item.step_id:
                            step_stmt = select(AgentStep).where(AgentStep.id == item.step_id)
                            step_res = await session.execute(step_stmt)
                            step = step_res.scalars().first()
                            if step:
                                step.status = "skipped"
                                step.error = err_msg
                                step.finished_at = now

                        await session.commit()
                        return ActionResponse(**item.to_dict())
            except Exception as exc:
                log.warning("action_service.db_reject_failed", error=str(exc))

        if action_id in self._mem:
            self._mem[action_id]["status"] = ActionStatus.REJECTED.value
            self._mem[action_id]["error"] = err_msg
            self._mem[action_id]["resolved_at"] = now.isoformat()
            return ActionResponse(**self._mem[action_id])

        return ActionResponse(
            id=action_id,
            user_id=user_id,
            task_id=action.task_id,
            step_id=action.step_id,
            tool_id=action.tool_id,
            description=action.description,
            input_parameters=action.input_parameters,
            risk_level=action.risk_level,
            required_permission=action.required_permission,
            status=ActionStatus.REJECTED.value,
            result=None,
            error=err_msg,
            created_at=action.created_at,
            resolved_at=now.isoformat(),
        )
