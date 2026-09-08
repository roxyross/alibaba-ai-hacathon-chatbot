"""calendar_read skill — read-only Google Calendar access.

Fetches upcoming events from Google Calendar API using a refresh token
stored in the backend (the runtime uses the backend's /api/v1/calendar endpoint
for calendar data, rather than managing its own OAuth flow).

If no calendar integration is configured, returns a clearly-labeled mock result.
"""

from __future__ import annotations

import structlog

import httpx

from runtime.config import settings
from runtime.skills.executor import SkillResult

log = structlog.get_logger()

# Google Calendar API base
_GCAL_BASE = "https://www.googleapis.com/calendar/v3"


async def calendar_read(
    start_date: str | None = None,
    end_date: str | None = None,
    max_events: int = 50,
    calendar_id: str = "primary",
    *,
    user_id: str,
) -> SkillResult:
    """Read upcoming events from Google Calendar.

    Args:
        start_date: ISO date string (YYYY-MM-DD). Defaults to today.
        end_date: ISO date string (YYYY-MM-DD). Defaults to 7 days from start.
        max_events: Maximum number of events to return (default 50).
        calendar_id: Which calendar to read (default "primary").
        user_id: for audit logging.

    Returns:
        SkillResult with a list of calendar events.
    """
    log.info(
        "calendar_read.invoked",
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Determine date range
    from datetime import date, timedelta

    today = date.today()
    start = start_date or today.isoformat()
    end = end_date or (today + timedelta(days=7)).isoformat()

    # Try to get an access token from the backend
    backend_token_url = f"{settings.backend_base_url}/api/v1/calendar/token"
    access_token: str | None = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                backend_token_url,
                headers={"Authorization": f"Bearer {user_id}"},  # user_id as proxy token lookup
            )
            if resp.is_success:
                token_data = resp.json()
                access_token = token_data.get("access_token")
    except Exception as exc:
        log.warning("calendar_read.token_fetch_failed", user_id=user_id, error=str(exc))

    if not access_token:
        # Return mock result when no calendar integration
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        mock_events = [
            {
                "id": "stub-1",
                "summary": "[Calendar not connected]",
                "start": now.isoformat(),
                "end": (now.replace(hour=now.hour + 1)).isoformat(),
                "attendees": [],
                "location": None,
                "description": (
                    "Connect your Google Calendar in Settings to see real events. "
                    "This is a placeholder until the calendar integration is configured."
                ),
                "is_stub": True,
            }
        ]
        return SkillResult(
            ok=True,
            data={
                "events": mock_events,
                "calendar_id": calendar_id,
                "start_date": start,
                "end_date": end,
            },
            warning="Calendar integration is not configured. Connect Google Calendar in Settings.",
        )

    # Real Google Calendar API call
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    params = {
        "calendarId": calendar_id,
        "timeMin": f"{start}T00:00:00Z",
        "timeMax": f"{end}T23:59:59Z",
        "maxResults": str(min(max_events, 100)),
        "singleEvents": "true",
        "orderBy": "startTime",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_GCAL_BASE}/calendars/{calendar_id}/events",
                headers=headers,
                params=params,
            )

        if resp.status_code == 401:
            return SkillResult(
                ok=False,
                data=None,
                error="Google Calendar access token expired. Please reconnect in Settings.",
            )

        if not resp.is_success:
            return SkillResult(
                ok=False,
                data=None,
                error=f"Google Calendar API error: {resp.status_code}",
            )

        data = resp.json()
        events = []
        for item in data.get("items", []):
            start_info = item.get("start", {})
            end_info = item.get("end", {})
            events.append({
                "id": item.get("id", ""),
                "summary": item.get("summary", "(No title)"),
                "start": start_info.get("dateTime") or start_info.get("date"),
                "end": end_info.get("dateTime") or end_info.get("date"),
                "attendees": [
                    {"email": a.get("email"), "displayName": a.get("displayName")}
                    for a in item.get("attendees", [])
                    if a.get("email")
                ],
                "location": item.get("location"),
                "description": item.get("description"),
            })

        return SkillResult(
            ok=True,
            data={
                "events": events,
                "calendar_id": calendar_id,
                "start_date": start,
                "end_date": end,
                "count": len(events),
            },
        )

    except httpx.HTTPError as exc:
        log.error("calendar_read.api_error", user_id=user_id, error=str(exc))
        return SkillResult(
            ok=False,
            data=None,
            error=f"Failed to reach Google Calendar: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        log.error("calendar_read.error", user_id=user_id, error=str(exc), exc_info=True)
        return SkillResult(ok=False, data=None, error=f"Calendar error: {exc}")
