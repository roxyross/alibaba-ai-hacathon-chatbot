"""Autonomous Browser Agent & Web Automation Studio API router (Phase 15).

Provides multi-tenant endpoints for headless web navigation, DOM inspection,
structured table and link extraction, screenshot captures, and multi-step browser tasks.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.browser.repository import BrowserRepository
from app.browser.schemas import (
    BrowserDOMInspectRequest,
    BrowserDOMInspectResponse,
    BrowserDownloadRequest,
    BrowserDownloadResponse,
    BrowserElementInteractRequest,
    BrowserElementInteractResponse,
    BrowserExecuteFlowRequest,
    BrowserExecuteFlowResponse,
    BrowserExtractRequest,
    BrowserExtractResponse,
    BrowserLaunchRequest,
    BrowserLaunchResponse,
    BrowserNavigateHardenedRequest,
    BrowserNavigateHardenedResponse,
    BrowserNavigateRequest,
    BrowserNavigateResponse,
    BrowserPageStateResponse,
    BrowserScreenshotHardenedRequest,
    BrowserScreenshotHardenedResponse,
    BrowserScreenshotRequest,
    BrowserScreenshotResponse,
    BrowserScrollRequest,
    BrowserScrollResponse,
    BrowserSessionModel,
    BrowserTabManageRequest,
    BrowserTabManageResponse,
    BrowserTaskCreate,
    BrowserTaskListResponse,
    BrowserTaskResponse,
    BrowserTaskUpdate,
    BrowserUploadRequest,
    BrowserUploadResponse,
    BrowserWaitRequest,
    BrowserWaitResponse,
)
from app.browser.service import BrowserService

log = structlog.get_logger()

router = APIRouter(prefix="/browser", tags=["Browser Automation"])


@router.get("/tasks", response_model=BrowserTaskListResponse)
@router.get("", response_model=BrowserTaskListResponse)
@router.get("/", response_model=BrowserTaskListResponse)
async def list_browser_tasks(
    limit: int = Query(default=50, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> BrowserTaskListResponse:
    """List authenticated user's browser automation tasks with search and filtering."""
    user_id = str(current_user.id)
    repo = BrowserRepository()
    items = await repo.list_tasks(
        user_id=user_id,
        limit=limit,
        search=search,
        status=status,
        action_type=action_type,
    )
    return BrowserTaskListResponse(tasks=items, total=len(items))


@router.post("/tasks", response_model=BrowserTaskResponse, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=BrowserTaskResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=BrowserTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_browser_task(
    payload: BrowserTaskCreate,
    current_user: User = Depends(get_current_user),
) -> BrowserTaskResponse:
    """Manually persist a new browser task for the authenticated user."""
    user_id = str(current_user.id)
    repo = BrowserRepository()
    created = await repo.create_task(
        user_id=user_id,
        data={
            "url": payload.url,
            "title": payload.title or f"Browse {payload.url[:50]}",
            "action_type": payload.action_type,
            "actions": payload.actions,
            "result_data": payload.result_data,
            "status": payload.status,
            "requires_confirmation": payload.requires_confirmation,
            "is_sensitive": payload.is_sensitive,
            "tags": payload.tags,
        },
    )
    return BrowserTaskResponse(task=created)


@router.get("/tasks/{task_id}", response_model=BrowserTaskResponse)
async def get_browser_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> BrowserTaskResponse:
    """Retrieve a single browser task, strictly checking tenant ownership."""
    user_id = str(current_user.id)
    repo = BrowserRepository()
    task = await repo.get_task(user_id=user_id, task_id=task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Browser task '{task_id}' not found.",
        )
    return BrowserTaskResponse(task=task)


@router.patch("/tasks/{task_id}", response_model=BrowserTaskResponse)
async def update_browser_task(
    task_id: str,
    payload: BrowserTaskUpdate,
    current_user: User = Depends(get_current_user),
) -> BrowserTaskResponse:
    """Update title, status, result data, or tags of an existing browser task."""
    user_id = str(current_user.id)
    repo = BrowserRepository()
    data: dict[str, Any] = {}
    if payload.title is not None:
        data["title"] = payload.title
    if payload.status is not None:
        data["status"] = payload.status
    if payload.result_data is not None:
        data["result_data"] = payload.result_data
    if payload.error_message is not None:
        data["error_message"] = payload.error_message
    if payload.tags is not None:
        data["tags"] = payload.tags

    updated = await repo.update_task(user_id=user_id, task_id=task_id, data=data)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Browser task '{task_id}' not found.",
        )
    return BrowserTaskResponse(task=updated)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_browser_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Delete a browser task, enforcing strict tenant isolation."""
    user_id = str(current_user.id)
    repo = BrowserRepository()
    deleted = await repo.delete_task(user_id=user_id, task_id=task_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Browser task '{task_id}' not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/navigate", response_model=BrowserNavigateResponse)
async def navigate_inspect_endpoint(
    payload: BrowserNavigateRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserNavigateResponse:
    """Navigate to target URL, inspect DOM structure, and return semantic components."""
    service = BrowserService.get_instance()
    res = await service.navigate_and_inspect(
        url=payload.url,
        wait_for=payload.wait_for,
        timeout_seconds=payload.timeout_seconds,
        js_enabled=payload.js_enabled,
    )
    return BrowserNavigateResponse(
        url=res["url"],
        title=res.get("title"),
        final_url=res.get("final_url"),
        status=res.get("status", "success"),
        content_preview=res.get("content_preview", ""),
        headings=res.get("headings", []),
        links=res.get("links", []),
        forms=res.get("forms", []),
        meta=res.get("meta", {}),
        error=res.get("error"),
    )


@router.post("/extract", response_model=BrowserExtractResponse)
async def extract_data_endpoint(
    payload: BrowserExtractRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserExtractResponse:
    """Extract structured tables, links, headings, or text from web HTML."""
    service = BrowserService.get_instance()
    res = await service.extract_data(
        url=payload.url,
        extract_type=payload.extract_type,
        selectors=payload.selectors,
        max_items=payload.max_items,
    )
    return BrowserExtractResponse(
        url=res["url"],
        title=res.get("title"),
        tables=res.get("tables", []),
        links=res.get("links", []),
        headings=res.get("headings", []),
        text_excerpt=res.get("text_excerpt", ""),
        status=res.get("status", "success"),
        error=res.get("error"),
    )


@router.post("/screenshot", response_model=BrowserScreenshotResponse)
async def screenshot_endpoint(
    payload: BrowserScreenshotRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserScreenshotResponse:
    """Capture a visual snapshot representation of a web page."""
    service = BrowserService.get_instance()
    res = await service.capture_screenshot(
        url=payload.url, width=payload.width, height=payload.height
    )
    return BrowserScreenshotResponse(
        url=res["url"],
        title=res.get("title"),
        screenshot_url=res["screenshot_url"],
        width=res["width"],
        height=res["height"],
        status=res.get("status", "success"),
        timestamp=res["timestamp"],
    )


@router.post("/execute", response_model=BrowserExecuteFlowResponse)
async def execute_browser_flow_endpoint(
    payload: BrowserExecuteFlowRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserExecuteFlowResponse:
    """Execute an autonomous multi-step browser flow and optionally persist the task."""
    user_id = str(current_user.id)
    service = BrowserService.get_instance()
    res = await service.execute_browser_flow(
        user_id=user_id,
        url=payload.url,
        actions=payload.actions,
        title=payload.title,
        save_task=payload.save_task,
        tags=payload.tags,
    )
    return BrowserExecuteFlowResponse(
        task_id=res.get("task_id"),
        url=res["url"],
        title=res["title"],
        status=res["status"],
        steps_executed=res.get("steps_executed", []),
        result_data=res.get("result_data", {}),
        error=res.get("error"),
    )


# =============================================================================
# Phase 10: Hardened Persistent Browser Session Endpoints
# =============================================================================

@router.post("/sessions/launch", response_model=BrowserLaunchResponse, status_code=status.HTTP_201_CREATED)
async def launch_browser_session_endpoint(
    payload: BrowserLaunchRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserLaunchResponse:
    """Launch or attach to a persistent browser profile session."""
    service = BrowserService.get_instance()
    res = await service.launch_session(
        profile_name=payload.profile_name,
        headless=payload.headless,
        browser_type=payload.browser_type,
        viewport_width=payload.viewport_width,
        viewport_height=payload.viewport_height,
        user_agent=payload.user_agent,
    )
    return BrowserLaunchResponse(session=BrowserSessionModel(**res))


@router.get("/sessions/{session_id}", response_model=BrowserSessionModel)
async def get_browser_session_endpoint(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> BrowserSessionModel:
    """Retrieve telemetry, active tab, and status for a persistent browser session."""
    service = BrowserService.get_instance()
    sess = await service.get_session(session_id=session_id)
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Browser session '{session_id}' not found or has been closed.",
        )
    return BrowserSessionModel(**sess)


@router.post("/sessions/{session_id}/close")
async def close_browser_session_endpoint(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Gracefully terminate a persistent browser session and release process resources."""
    service = BrowserService.get_instance()
    closed = await service.close_session(session_id=session_id)
    return {"session_id": session_id, "closed": closed}


@router.post("/sessions/{session_id}/navigate", response_model=BrowserNavigateHardenedResponse)
async def navigate_browser_session_endpoint(
    session_id: str,
    payload: BrowserNavigateHardenedRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserNavigateHardenedResponse:
    """Navigate a persistent browser session tab to a URL and inspect DOM elements."""
    service = BrowserService.get_instance()
    res = await service.navigate_session(
        session_id=session_id,
        url=payload.url,
        tab_id=payload.tab_id,
        wait_for=payload.wait_for,
        timeout_seconds=payload.timeout_seconds,
    )
    return BrowserNavigateHardenedResponse(**res)


@router.post("/sessions/{session_id}/dom/inspect", response_model=BrowserDOMInspectResponse)
async def inspect_dom_endpoint(
    session_id: str,
    payload: BrowserDOMInspectRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserDOMInspectResponse:
    """Inspect interactive DOM buttons, inputs, links, forms, and accessibility roles."""
    service = BrowserService.get_instance()
    res = await service.inspect_dom(
        session_id=session_id,
        tab_id=payload.tab_id,
        selector=payload.selector,
        max_depth=payload.max_depth,
    )
    return BrowserDOMInspectResponse(**res)


@router.post("/sessions/{session_id}/interact", response_model=BrowserElementInteractResponse)
async def interact_element_endpoint(
    session_id: str,
    payload: BrowserElementInteractRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserElementInteractResponse:
    """Perform real DOM click, typing, select, or hover with live state verification."""
    service = BrowserService.get_instance()
    res = await service.interact_element(
        session_id=session_id,
        selector=payload.selector,
        action=payload.action,
        tab_id=payload.tab_id,
        text=payload.text,
        value=payload.value,
        clear_first=payload.clear_first,
        delay_ms=payload.delay_ms,
        timeout_ms=payload.timeout_ms,
    )
    return BrowserElementInteractResponse(**res)


@router.post("/sessions/{session_id}/scroll", response_model=BrowserScrollResponse)
async def scroll_page_endpoint(
    session_id: str,
    payload: BrowserScrollRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserScrollResponse:
    """Scroll webpage or container and retrieve post-scroll coordinates."""
    service = BrowserService.get_instance()
    res = await service.scroll_page(
        session_id=session_id,
        direction=payload.direction,
        amount=payload.amount,
        tab_id=payload.tab_id,
        selector=payload.selector,
    )
    return BrowserScrollResponse(**res)


@router.post("/sessions/{session_id}/screenshot", response_model=BrowserScreenshotHardenedResponse)
async def screenshot_session_endpoint(
    session_id: str,
    payload: BrowserScreenshotHardenedRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserScreenshotHardenedResponse:
    """Capture a real PNG screenshot of the session's active page or a targeted element."""
    pw_manager = service = BrowserService.get_instance().pw_manager
    res = await pw_manager.capture_screenshot(
        session_id=session_id,
        tab_id=payload.tab_id,
        full_page=payload.full_page,
        selector=payload.selector,
        width=payload.width,
        height=payload.height,
    )
    return res


@router.post("/sessions/{session_id}/tabs", response_model=BrowserTabManageResponse)
async def manage_tabs_endpoint(
    session_id: str,
    payload: BrowserTabManageRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserTabManageResponse:
    """Create, switch, or close tabs in an active browser session."""
    service = BrowserService.get_instance()
    res = await service.manage_session_tabs(
        session_id=session_id,
        action=payload.action,
        tab_id=payload.tab_id,
        url=payload.url,
    )
    return BrowserTabManageResponse(**res)


@router.get("/sessions/{session_id}/state", response_model=BrowserPageStateResponse)
async def get_page_state_endpoint(
    session_id: str,
    tab_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> BrowserPageStateResponse:
    """Retrieve comprehensive page state and telemetry without leaking secrets."""
    service = BrowserService.get_instance()
    res = await service.get_session_page_state(session_id=session_id, tab_id=tab_id)
    return BrowserPageStateResponse(**res)


@router.post("/sessions/{session_id}/wait", response_model=BrowserWaitResponse)
async def wait_for_endpoint(
    session_id: str,
    payload: BrowserWaitRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserWaitResponse:
    """Wait for selector visibility, network idle, or timeout in active session."""
    service = BrowserService.get_instance()
    res = await service.wait_for_condition(
        session_id=session_id,
        tab_id=payload.tab_id,
        state=payload.state,
        selector=payload.selector,
        timeout_ms=payload.timeout_ms,
    )
    return BrowserWaitResponse(**res)


@router.post("/sessions/{session_id}/upload", response_model=BrowserUploadResponse)
async def upload_file_endpoint(
    session_id: str,
    payload: BrowserUploadRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserUploadResponse:
    """Attach and upload one or more local files to a file input element."""
    service = BrowserService.get_instance()
    res = await service.upload_file(
        session_id=session_id,
        selector=payload.selector,
        file_paths=payload.file_paths,
        tab_id=payload.tab_id,
        timeout_ms=payload.timeout_ms,
    )
    return BrowserUploadResponse(**res)


@router.post("/sessions/{session_id}/download", response_model=BrowserDownloadResponse)
async def download_file_endpoint(
    session_id: str,
    payload: BrowserDownloadRequest,
    current_user: User = Depends(get_current_user),
) -> BrowserDownloadResponse:
    """Trigger and capture a file download to secure local storage."""
    service = BrowserService.get_instance()
    res = await service.download_file(
        session_id=session_id,
        selector=payload.selector,
        trigger_action=payload.trigger_action,
        tab_id=payload.tab_id,
        timeout_ms=payload.timeout_ms,
    )
    return BrowserDownloadResponse(**res)

