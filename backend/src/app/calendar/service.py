"""CalendarService — AI natural language parsing, RFC 5545 ICS generation and parsing, and conflict detection."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import structlog

from app.calendar.repository import CalendarRepository

log = structlog.get_logger()


class CalendarService:
    """Service providing calendar intelligence, ICS serialization, and conflict checking."""

    _instance: ClassVar[CalendarService | None] = None

    @classmethod
    def get_instance(cls, repo: CalendarRepository | None = None) -> CalendarService:
        """Thread-safe singleton accessor."""
        if cls._instance is None:
            cls._instance = cls(repo=repo)
        return cls._instance

    def __init__(self, repo: CalendarRepository | None = None) -> None:
        self._repo = repo or CalendarRepository()

    def parse_event_from_prompt(self, prompt: str) -> dict[str, Any]:
        """Parse natural language scheduling prompt into structured event fields.

        Example inputs:
        - "Schedule project sprint sync tomorrow at 3pm for 45 minutes on Google Meet"
        - "Set a deadline for Hackathon submission on October 25th at 11:59pm"
        - "Lunch meeting with Alex at 12:30pm on Friday"
        """
        now = datetime.now(UTC)
        prompt_lower = prompt.lower().strip()

        # 1. Determine category
        category = "meeting"
        if "hackathon" in prompt_lower:
            category = "hackathon"
        elif "deadline" in prompt_lower or "due" in prompt_lower:
            category = "deadline"
        elif "remind" in prompt_lower or "reminder" in prompt_lower:
            category = "reminder"
        elif "personal" in prompt_lower or "doctor" in prompt_lower or "gym" in prompt_lower:
            category = "personal"

        # 2. Determine target date
        target_date = now.date()
        if "tomorrow" in prompt_lower:
            target_date = target_date + timedelta(days=1)
        elif "day after tomorrow" in prompt_lower:
            target_date = target_date + timedelta(days=2)
        else:
            # Check for day of week (e.g., "on monday", "this friday", "next wednesday")
            weekdays = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6,
            }
            for day_name, day_idx in weekdays.items():
                if day_name in prompt_lower:
                    current_idx = target_date.weekday()
                    days_ahead = (day_idx - current_idx) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    target_date = target_date + timedelta(days=days_ahead)
                    break

        # 3. Determine time
        target_hour = 10
        target_minute = 0
        time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", prompt_lower)
        if time_match:
            hr = int(time_match.group(1))
            mn = int(time_match.group(2) or 0)
            ampm = time_match.group(3)
            if ampm == "pm" and hr < 12:
                hr += 12
            elif ampm == "am" and hr == 12:
                hr = 0
            if 0 <= hr <= 23 and 0 <= mn <= 59:
                target_hour = hr
                target_minute = mn

        start_dt = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            target_hour,
            target_minute,
            0,
            tzinfo=UTC,
        )

        # 4. Determine duration
        duration_minutes = 60
        dur_match = re.search(r"for\s+(\d+)\s*(mins?|minutes?|hours?|hrs?)", prompt_lower)
        if dur_match:
            val = int(dur_match.group(1))
            unit = dur_match.group(2) or ""
            duration_minutes = val * 60 if ("hour" in unit or "hr" in unit) else val
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        # 5. Determine location or link
        location = None
        if "zoom" in prompt_lower:
            location = "Zoom Meeting"
        elif "meet" in prompt_lower or "google meet" in prompt_lower:
            location = "Google Meet"
        elif "teams" in prompt_lower:
            location = "Microsoft Teams"
        else:
            loc_match = re.search(r"\b(?:at|in)\s+([A-Z][a-zA-Z0-9\s]+(?:Room|Building|Office|Cafe|Park|Center))", prompt)
            if loc_match:
                location = loc_match.group(1).strip()

        # 6. Extract clean title
        title = prompt
        # Strip common command prefixes safely with whitespace/word boundaries
        clean_title = re.sub(
            r"(?i)^(?:schedule\s+(?:a\s+|an\s+)?|set\s+(?:a\s+)?reminder\s+(?:for\s+|to\s+)?|add\s+(?:a\s+)?meeting\s+with\s+|add\s+(?:an\s+)?event\s+|create\s+event\s+|remind\s+me\s+(?:to\s+|about\s+)?)\s*",
            "",
            prompt,
        ).strip()
        if clean_title:
            title = clean_title

        # Trim date/time fragments from end of title if present
        title = re.sub(r"\s+(?:tomorrow|yesterday|today|on\s+[a-zA-Z]+|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|for\s+\d+\s*(?:mins?|minutes?|hours?)).*$", "", title, flags=re.IGNORECASE).strip()
        title = "Scheduled Event" if not title else title[:120].strip(" :,-")

        return {
            "title": title.title(),
            "description": f"Created via ROXY AI Assistant from prompt: \"{prompt}\"",
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "location": location,
            "category": category,
            "is_all_day": False,
            "remind_minutes_before": 15,
        }

    def generate_ics(self, events: list[dict[str, Any]], calendar_name: str = "ROXY AI Calendar") -> str:
        """Generate standard RFC 5545 iCalendar (.ics) string from event records."""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//ROXY AI//Calendar Service//EN",
            "CALSCALE:GREGORIAN",
            f"X-WR-CALNAME:{calendar_name}",
        ]

        now_str = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

        for e in events:
            uid = e.get("id") or str(uuid.uuid4())
            title = (e.get("title") or "Event").replace("\n", " ").replace(";", "\\;")
            desc = (e.get("description") or "").replace("\n", "\\n").replace(";", "\\;")
            loc = (e.get("location") or "").replace("\n", " ").replace(";", "\\;")

            start_iso = e.get("start_time")
            end_iso = e.get("end_time")

            dt_start = ""
            if start_iso:
                try:
                    dt = datetime.fromisoformat(start_iso)
                    dt_start = dt.strftime("%Y%m%dT%H%M%SZ")
                except Exception:
                    dt_start = now_str

            dt_end = ""
            if end_iso:
                try:
                    dt = datetime.fromisoformat(end_iso)
                    dt_end = dt.strftime("%Y%m%dT%H%M%SZ")
                except Exception:
                    pass

            lines.append("BEGIN:VEVENT")
            lines.append(f"UID:{uid}@roxy.ai")
            lines.append(f"DTSTAMP:{now_str}")
            if dt_start:
                lines.append(f"DTSTART:{dt_start}")
            if dt_end:
                lines.append(f"DTEND:{dt_end}")
            lines.append(f"SUMMARY:{title}")
            if desc:
                lines.append(f"DESCRIPTION:{desc}")
            if loc:
                lines.append(f"LOCATION:{loc}")
            category = e.get("category")
            if category:
                lines.append(f"CATEGORIES:{category.upper()}")
            lines.append("END:VEVENT")

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    def parse_ics(self, ics_content: str) -> list[dict[str, Any]]:
        """Parse RFC 5545 iCalendar string into structured event objects."""
        events: list[dict[str, Any]] = []
        raw_events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_content, re.DOTALL | re.IGNORECASE)

        for block in raw_events:
            summary_m = re.search(r"SUMMARY:(.*?)(?:\r?\n[A-Z]|\r?\nEND:)", block, re.DOTALL)
            summary = summary_m.group(1).replace("\r\n", "").replace("\\;", ";").strip() if summary_m else "Imported Event"

            desc_m = re.search(r"DESCRIPTION:(.*?)(?:\r?\n[A-Z]|\r?\nEND:)", block, re.DOTALL)
            desc = desc_m.group(1).replace("\r\n", "").replace("\\n", "\n").replace("\\;", ";").strip() if desc_m else ""

            loc_m = re.search(r"LOCATION:(.*?)(?:\r?\n[A-Z]|\r?\nEND:)", block, re.DOTALL)
            location = loc_m.group(1).replace("\r\n", "").replace("\\;", ";").strip() if loc_m else None

            start_m = re.search(r"DTSTART(?:;[^:]+)?:(\d{8}(?:T\d{6}Z?)?)", block)
            start_iso = datetime.now(UTC).isoformat()
            if start_m:
                raw_s = start_m.group(1)
                try:
                    if "T" in raw_s:
                        fmt = "%Y%m%dT%H%M%SZ" if raw_s.endswith("Z") else "%Y%m%dT%H%M%S"
                        start_iso = datetime.strptime(raw_s, fmt).replace(tzinfo=UTC).isoformat()
                    else:
                        start_iso = datetime.strptime(raw_s, "%Y%m%d").replace(tzinfo=UTC).isoformat()
                except Exception:
                    pass

            end_m = re.search(r"DTEND(?:;[^:]+)?:(\d{8}(?:T\d{6}Z?)?)", block)
            end_iso = None
            if end_m:
                raw_e = end_m.group(1)
                try:
                    if "T" in raw_e:
                        fmt = "%Y%m%dT%H%M%SZ" if raw_e.endswith("Z") else "%Y%m%dT%H%M%S"
                        end_iso = datetime.strptime(raw_e, fmt).replace(tzinfo=UTC).isoformat()
                    else:
                        end_iso = datetime.strptime(raw_e, "%Y%m%d").replace(tzinfo=UTC).isoformat()
                except Exception:
                    pass

            cat_m = re.search(r"CATEGORIES:(.*?)(?:\r?\n[A-Z]|\r?\nEND:)", block, re.DOTALL)
            category = cat_m.group(1).strip().lower() if cat_m else "meeting"
            if category not in ("meeting", "hackathon", "deadline", "personal", "reminder"):
                category = "meeting"

            events.append({
                "title": summary,
                "description": desc,
                "start_time": start_iso,
                "end_time": end_iso,
                "location": location,
                "category": category,
                "is_all_day": False,
            })

        return events

    async def detect_conflicts(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        exclude_event_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Identify overlapping events on the user's calendar."""
        # Query window around the candidate start/end
        window_start = start_time - timedelta(hours=1)
        window_end = end_time + timedelta(hours=1)
        existing = await self._repo.list_events(user_id, start_date=window_start, end_date=window_end)

        conflicts: list[dict[str, Any]] = []
        for e in existing:
            if exclude_event_id and e.get("id") == exclude_event_id:
                continue
            e_start_str = e.get("start_time")
            e_end_str = e.get("end_time") or e_start_str
            if not e_start_str:
                continue
            try:
                e_start = datetime.fromisoformat(e_start_str)
                e_end = datetime.fromisoformat(e_end_str) if e_end_str else e_start + timedelta(hours=1)
                # Overlap condition: max(start1, start2) < min(end1, end2)
                if max(start_time, e_start) < min(end_time, e_end):
                    conflicts.append(e)
            except Exception:
                pass

        return conflicts

    def register_calendar_tools(self) -> None:
        """Register native calendar and event scheduling tools with the central ToolRegistry."""
        import contextlib

        from app.tools.registry import ToolRegistry
        from app.tools.schemas import AgentTool, RiskLevel, ToolSource

        registry = ToolRegistry.get_instance()

        # 1. calendar_list_events
        async def _tool_calendar_list_events(
            start_date: str | None = None,
            end_date: str | None = None,
            category: str | None = None,
            limit: int = 50,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            if not user_id:
                return {"events": [], "total": 0, "error": "user_id is required"}
            s_dt: datetime | None = None
            e_dt: datetime | None = None
            if start_date:
                with contextlib.suppress(ValueError):
                    s_dt = datetime.fromisoformat(start_date)
            if end_date:
                with contextlib.suppress(ValueError):
                    e_dt = datetime.fromisoformat(end_date)
            events = await self._repo.list_events(user_id, start_date=s_dt, end_date=e_dt, category=category)
            return {"events": events[:limit], "total": len(events)}

        registry.register(
            AgentTool(
                id="calendar_list_events",
                name="List Calendar Events",
                description="List scheduled calendar events for the user with optional date range and category filtering.",
                source=ToolSource.SYSTEM,
                capabilities=["calendar", "events", "schedule", "meetings"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "description": "Filter events starting on or after this ISO 8601 date."},
                        "end_date": {"type": "string", "description": "Filter events starting on or before this ISO 8601 date."},
                        "category": {"type": "string", "description": "Filter by category ('meeting', 'hackathon', 'deadline', 'personal', 'reminder')."},
                        "limit": {"type": "integer", "default": 50, "description": "Maximum number of events to return."},
                    },
                },
                permissions=["calendar:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_calendar_list_events,
        )

        # 2. calendar_get_event
        async def _tool_calendar_get_event(
            event_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            if not user_id:
                return {"found": False, "error": "user_id is required"}
            event = await self._repo.get_event(user_id, event_id)
            if not event:
                return {"found": False, "error": f"Event '{event_id}' not found"}
            return {"found": True, "event": event}

        registry.register(
            AgentTool(
                id="calendar_get_event",
                name="Get Calendar Event Details",
                description="Retrieve full details, timing, location, and reminders for a specific calendar event.",
                source=ToolSource.SYSTEM,
                capabilities=["calendar", "events", "details"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Unique event ID to inspect"},
                    },
                    "required": ["event_id"],
                },
                permissions=["calendar:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_calendar_get_event,
        )

        # 3. calendar_create_event
        async def _tool_calendar_create_event(
            title: str,
            start_time: str,
            end_time: str | None = None,
            description: str = "",
            location: str | None = None,
            category: str = "meeting",
            is_all_day: bool = False,
            remind_minutes_before: int = 15,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            if not user_id:
                return {"success": False, "error": "user_id is required"}
            try:
                s_dt = datetime.fromisoformat(start_time)
            except ValueError as exc:
                return {"success": False, "error": f"Invalid start_time: {exc}"}

            e_dt: datetime | None = None
            if end_time:
                try:
                    e_dt = datetime.fromisoformat(end_time)
                except ValueError as exc:
                    return {"success": False, "error": f"Invalid end_time: {exc}"}
            else:
                e_dt = s_dt + timedelta(hours=1)

            conflicts = await self.detect_conflicts(user_id, s_dt, e_dt)
            created = await self._repo.create_event(
                user_id=user_id,
                title=title,
                start_time=s_dt,
                end_time=e_dt,
                description=description,
                location=location,
                category=category,
                is_all_day=is_all_day,
                remind_minutes_before=remind_minutes_before,
            )
            return {
                "success": True,
                "event": created,
                "conflicts": conflicts,
                "has_conflicts": len(conflicts) > 0,
            }

        registry.register(
            AgentTool(
                id="calendar_create_event",
                name="Schedule Calendar Event",
                description="Schedule a new calendar event, meeting, deadline, or reminder with conflict detection.",
                source=ToolSource.SYSTEM,
                capabilities=["calendar", "events", "create", "schedule"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title or subject of the event"},
                        "start_time": {"type": "string", "description": "ISO 8601 start timestamp"},
                        "end_time": {"type": "string", "description": "ISO 8601 end timestamp (optional, defaults to +1 hour)"},
                        "description": {"type": "string", "description": "Detailed description or agenda", "default": ""},
                        "location": {"type": "string", "description": "Meeting location or video call URL"},
                        "category": {"type": "string", "default": "meeting", "description": "Category ('meeting', 'hackathon', 'deadline', 'personal', 'reminder')"},
                        "is_all_day": {"type": "boolean", "default": False, "description": "Whether the event spans the entire day"},
                        "remind_minutes_before": {"type": "integer", "default": 15, "description": "Minutes before start time to trigger a reminder"},
                    },
                    "required": ["title", "start_time"],
                },
                permissions=["calendar:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_calendar_create_event,
        )

        # 4. calendar_update_event
        async def _tool_calendar_update_event(
            event_id: str,
            title: str | None = None,
            start_time: str | None = None,
            end_time: str | None = None,
            description: str | None = None,
            location: str | None = None,
            category: str | None = None,
            is_all_day: bool | None = None,
            remind_minutes_before: int | None = None,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            if not user_id:
                return {"success": False, "error": "user_id is required"}
            existing = await self._repo.get_event(user_id, event_id)
            if not existing:
                return {"success": False, "error": f"Event '{event_id}' not found"}

            updates: dict[str, Any] = {}
            if title is not None:
                updates["title"] = title
            if description is not None:
                updates["description"] = description
            if location is not None:
                updates["location"] = location
            if category is not None:
                updates["category"] = category
            if is_all_day is not None:
                updates["is_all_day"] = is_all_day
            if remind_minutes_before is not None:
                updates["remind_minutes_before"] = remind_minutes_before

            if start_time is not None:
                try:
                    updates["start_time"] = datetime.fromisoformat(start_time)
                except ValueError as exc:
                    return {"success": False, "error": f"Invalid start_time: {exc}"}
            if end_time is not None:
                try:
                    updates["end_time"] = datetime.fromisoformat(end_time)
                except ValueError as exc:
                    return {"success": False, "error": f"Invalid end_time: {exc}"}

            updated = await self._repo.update_event(user_id, event_id, **updates)
            return {"success": True, "event": updated}

        registry.register(
            AgentTool(
                id="calendar_update_event",
                name="Update Calendar Event",
                description="Update an existing calendar event's title, timing, location, or reminder settings.",
                source=ToolSource.SYSTEM,
                capabilities=["calendar", "events", "update", "modify"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Unique event ID to modify"},
                        "title": {"type": "string", "description": "Updated title of the event"},
                        "start_time": {"type": "string", "description": "Updated ISO 8601 start timestamp"},
                        "end_time": {"type": "string", "description": "Updated ISO 8601 end timestamp"},
                        "description": {"type": "string", "description": "Updated description"},
                        "location": {"type": "string", "description": "Updated location or link"},
                        "category": {"type": "string", "description": "Updated category"},
                        "is_all_day": {"type": "boolean", "description": "Updated all-day flag"},
                        "remind_minutes_before": {"type": "integer", "description": "Updated reminder offset in minutes"},
                    },
                    "required": ["event_id"],
                },
                permissions=["calendar:write"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_calendar_update_event,
        )

        # 5. calendar_parse_prompt
        async def _tool_calendar_parse_prompt(
            prompt: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            parsed = self.parse_event_from_prompt(prompt)
            return {"success": True, "parsed_event": parsed}

        registry.register(
            AgentTool(
                id="calendar_parse_prompt",
                name="Parse Natural Language Event Prompt",
                description="Parse a natural language scheduling prompt into structured calendar event fields.",
                source=ToolSource.SYSTEM,
                capabilities=["calendar", "nlp", "parse", "prompt"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Natural language scheduling request"},
                    },
                    "required": ["prompt"],
                },
                permissions=["calendar:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_calendar_parse_prompt,
        )

        # 6. calendar_get_upcoming
        async def _tool_calendar_get_upcoming(
            days_ahead: int = 7,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            if not user_id:
                return {"events": [], "count": 0, "error": "user_id is required"}
            now = datetime.now(UTC)
            end = now + timedelta(days=days_ahead)
            events = await self._repo.list_events(user_id, start_date=now, end_date=end)
            return {"events": events, "count": len(events), "window_days": days_ahead}

        registry.register(
            AgentTool(
                id="calendar_get_upcoming",
                name="Get Upcoming Calendar Events",
                description="Get upcoming calendar events and meetings scheduled within the next N days.",
                source=ToolSource.SYSTEM,
                capabilities=["calendar", "events", "upcoming"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "days_ahead": {"type": "integer", "default": 7, "description": "Number of days ahead to look for upcoming events"},
                    },
                },
                permissions=["calendar:read"],
                risk_level=RiskLevel.LOW,
                requires_confirmation=False,
            ),
            _tool_calendar_get_upcoming,
        )

        # 7. calendar_delete_event (HIGH RISK - requires confirmation)
        async def _tool_calendar_delete_event(
            event_id: str,
            user_id: str | None = None,
        ) -> dict[str, Any]:
            if not user_id:
                return {"deleted": False, "error": "user_id is required"}
            deleted = await self._repo.delete_event(user_id, event_id)
            if not deleted:
                return {"deleted": False, "error": f"Event '{event_id}' not found"}
            return {"deleted": True, "event_id": event_id}

        registry.register(
            AgentTool(
                id="calendar_delete_event",
                name="Delete Calendar Event",
                description="Permanently delete a calendar event. High-risk operation requiring explicit confirmation.",
                source=ToolSource.SYSTEM,
                capabilities=["calendar", "events", "delete", "destructive"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string", "description": "Unique event ID to delete"},
                    },
                    "required": ["event_id"],
                },
                permissions=["calendar:write"],
                risk_level=RiskLevel.HIGH,
                requires_confirmation=True,
            ),
            _tool_calendar_delete_event,
        )


