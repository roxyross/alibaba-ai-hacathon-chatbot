"""CalendarService — AI natural language parsing, RFC 5545 ICS generation and parsing, and conflict detection."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.calendar.repository import CalendarRepository

log = structlog.get_logger()


class CalendarService:
    """Service providing calendar intelligence, ICS serialization, and conflict checking."""

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
        # Strip common command prefixes
        for prefix in (
            "schedule a", "schedule an", "schedule",
            "set a reminder for", "set a reminder to", "set reminder for", "set reminder",
            "add a meeting with", "add meeting with", "add an event", "add event", "create event",
            "remind me to", "remind me about",
        ):
            if prompt_lower.startswith(prefix):
                title = prompt[len(prefix):].strip()
                break

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
