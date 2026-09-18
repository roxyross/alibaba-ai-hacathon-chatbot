"""Calendar API endpoints — Event scheduling, filtering, AI parsing, and RFC 5545 ICS export/import.

All operations strictly require authentication and enforce user tenant isolation.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.calendar.repository import CalendarRepository
from app.calendar.service import CalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])

_repo = CalendarRepository()
_service = CalendarService(_repo)


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

class CreateEventRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    start_time: str = Field(..., description="ISO 8601 start timestamp")
    end_time: str | None = Field(default=None, description="ISO 8601 end timestamp")
    description: str = Field(default="")
    location: str | None = Field(default=None, max_length=255)
    category: str = Field(default="meeting")
    is_all_day: bool = Field(default=False)
    recurrence_rule: str | None = Field(default=None)
    remind_minutes_before: int | None = Field(default=15)


class UpdateEventRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    start_time: str | None = Field(default=None)
    end_time: str | None = Field(default=None)
    description: str | None = Field(default=None)
    location: str | None = Field(default=None)
    category: str | None = Field(default=None)
    is_all_day: bool | None = Field(default=None)
    recurrence_rule: str | None = Field(default=None)
    remind_minutes_before: int | None = Field(default=None)


class ParsePromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/events")
async def list_events(
    start_date: str | None = Query(default=None, description="Filter events starting on or after (ISO)"),
    end_date: str | None = Query(default=None, description="Filter events starting on or before (ISO)"),
    category: str | None = Query(default=None, description="Filter by category"),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List authenticated user's calendar events with optional date and category filters."""
    user_id = str(user.id)
    s_dt = None
    e_dt = None
    if start_date:
        with contextlib.suppress(ValueError):
            s_dt = datetime.fromisoformat(start_date)
    if end_date:
        with contextlib.suppress(ValueError):
            e_dt = datetime.fromisoformat(end_date)

    events = await _repo.list_events(user_id, start_date=s_dt, end_date=e_dt, category=category)
    return {"events": events, "total": len(events)}


@router.post("/events")
async def create_event(
    body: CreateEventRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new calendar event for the authenticated user."""
    user_id = str(user.id)
    try:
        start_dt = datetime.fromisoformat(body.start_time)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid start_time format: {exc}",
        ) from exc

    end_dt = None
    if body.end_time:
        try:
            end_dt = datetime.fromisoformat(body.end_time)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid end_time format: {exc}",
            ) from exc

    ev = await _repo.create_event(
        user_id=user_id,
        title=body.title,
        start_time=start_dt,
        end_time=end_dt,
        description=body.description,
        location=body.location,
        category=body.category,
        is_all_day=body.is_all_day,
        recurrence_rule=body.recurrence_rule,
        remind_minutes_before=body.remind_minutes_before,
    )
    return {"event": ev}


@router.post("/parse-ai")
async def parse_event_prompt(
    body: ParsePromptRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Parse a natural language scheduling prompt into a draft calendar event."""
    draft = _service.parse_event_from_prompt(body.prompt)
    return {"draft_event": draft}


@router.get("/upcoming")
async def get_upcoming_events(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get user's upcoming events for the next 7 days."""
    user_id = str(user.id)
    now = datetime.now(UTC)
    week_later = now + timedelta(days=7)
    events = await _repo.list_events(user_id, start_date=now, end_date=week_later)
    return {"events": events, "total": len(events)}


@router.get("/export/ics")
async def export_ics(
    user: User = Depends(get_current_user),
) -> Response:
    """Export the user's complete schedule as an RFC 5545 iCalendar (.ics) file."""
    user_id = str(user.id)
    events = await _repo.list_events(user_id)
    ics_text = _service.generate_ics(events, calendar_name=f"{user.email}'s ROXY Calendar")
    return Response(
        content=ics_text,
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="roxy_calendar.ics"'},
    )


@router.post("/import/ics")
async def import_ics(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Import events from an uploaded .ics file into the user's calendar."""
    user_id = str(user.id)
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    parsed_events = _service.parse_ics(text)

    created_events = []
    for p in parsed_events:
        try:
            start_dt = datetime.fromisoformat(p["start_time"])
            end_dt = datetime.fromisoformat(p["end_time"]) if p.get("end_time") else None
            created = await _repo.create_event(
                user_id=user_id,
                title=p["title"],
                start_time=start_dt,
                end_time=end_dt,
                description=p.get("description", ""),
                location=p.get("location"),
                category=p.get("category", "meeting"),
            )
            created_events.append(created)
        except Exception:
            continue

    return {
        "imported_count": len(created_events),
        "events": created_events,
        "message": f"Successfully imported {len(created_events)} events.",
    }


@router.get("/events/{event_id}")
async def get_event(
    event_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve a single event owned by authenticated user."""
    user_id = str(user.id)
    ev = await _repo.get_event(user_id, event_id)
    if not ev:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar event not found.",
        )
    return {"event": ev}


@router.patch("/events/{event_id}")
async def update_event(
    event_id: str,
    body: UpdateEventRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update event fields for authenticated user."""
    user_id = str(user.id)
    updates = body.model_dump(exclude_unset=True)

    if "start_time" in updates and updates["start_time"]:
        try:
            updates["start_time"] = datetime.fromisoformat(updates["start_time"])
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid start_time format: {exc}",
            ) from exc

    if "end_time" in updates and updates["end_time"]:
        try:
            updates["end_time"] = datetime.fromisoformat(updates["end_time"])
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid end_time format: {exc}",
            ) from exc

    updated = await _repo.update_event(user_id, event_id, **updates)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar event not found or unauthorized.",
        )
    return {"event": updated}


@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete an event owned by the authenticated user."""
    user_id = str(user.id)
    deleted = await _repo.delete_event(user_id, event_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Calendar event not found or unauthorized.",
        )
    return {"success": True, "message": "Event deleted successfully."}
