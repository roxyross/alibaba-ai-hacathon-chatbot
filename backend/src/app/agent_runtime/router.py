"""Agent Runtime and Tool Registry API router for ROXY-AI 2.0.

Provides task lifecycle controls, execution streaming (SSE), and tool registry endpoints.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.agent_runtime.executor import AgentExecutor
from app.agent_runtime.schemas import (
    TaskCreateRequest,
    TaskResponse,
)
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.tools.registry import ToolRegistry
from app.tools.schemas import (
    RiskLevel,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolSource,
)

router = APIRouter(prefix="/agents", tags=["agents"])
_executor = AgentExecutor()
_registry = ToolRegistry.get_instance()


# -----------------------------------------------------------------------------
# Agent Task Lifecycles
# -----------------------------------------------------------------------------

@router.post("/tasks", response_model=TaskResponse)
async def create_task(
    req: TaskCreateRequest,
    user: User = Depends(get_current_user),
) -> TaskResponse:
    """Create a new autonomous task with goal objective, tool discovery, and planning."""
    return await _executor.create_task(user_id=user.id, req=req)


@router.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
) -> list[TaskResponse]:
    """Retrieve all autonomous tasks created by the authenticated user."""
    return await _executor.list_tasks(user_id=user.id, limit=limit)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    user: User = Depends(get_current_user),
) -> TaskResponse:
    """Retrieve a specific task and its operational step milestones."""
    task = await _executor.get_task(user_id=user.id, task_id=task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


@router.post("/tasks/{task_id}/run", response_model=TaskResponse)
async def run_task(
    task_id: str,
    user: User = Depends(get_current_user),
) -> TaskResponse:
    """Execute or resume an existing task."""
    try:
        return await _executor.run_task(user_id=user.id, task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/pause", response_model=TaskResponse)
async def pause_task(
    task_id: str,
    user: User = Depends(get_current_user),
) -> TaskResponse:
    """Pause execution of a running task."""
    try:
        return await _executor.pause_task(user_id=user.id, task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    user: User = Depends(get_current_user),
) -> TaskResponse:
    """Cancel a task and mark pending steps as skipped."""
    try:
        return await _executor.cancel_task(user_id=user.id, task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/retry", response_model=TaskResponse)
async def retry_task(
    task_id: str,
    user: User = Depends(get_current_user),
) -> TaskResponse:
    """Retry failed steps of a task."""
    try:
        return await _executor.retry_task(user_id=user.id, task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/stream")
async def stream_task_progress(
    task_id: str,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Server-Sent Events (SSE) stream yielding real-time action-level milestones."""
    task = await _executor.get_task(user_id=user.id, task_id=task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in _executor.subscribe_events(task_id):
            payload = event.model_dump_json()
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# -----------------------------------------------------------------------------
# Tool Registry Endpoints
# -----------------------------------------------------------------------------

tools_router = APIRouter(prefix="/tools", tags=["tools"])


@tools_router.get("", response_model=list[dict[str, Any]])
async def list_tools(
    source: ToolSource | None = None,
    capability: str | None = None,
    risk_level: RiskLevel | None = None,
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List registered capabilities and available tools with risk and confirmation specs."""
    tools = _registry.list_tools(source=source, capability=capability, risk_level=risk_level)
    return [t.to_dict() for t in tools]


@tools_router.post("/execute", response_model=ToolExecutionResult)
async def execute_tool(
    req: ToolExecutionRequest,
    user: User = Depends(get_current_user),
) -> ToolExecutionResult:
    """Directly execute a registered tool within the sandbox (for authorized callers)."""
    # Enforce caller's user_id
    req.user_id = user.id
    # CRITICAL P0: Public external callers must NEVER be able to set bypass_confirmation=True.
    req.bypass_confirmation = False
    return await _registry.execute(req, _trusted_internal=False)
