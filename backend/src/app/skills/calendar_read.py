"""calendar_read skill — parse and return events from an ICS (iCalendar) file or URL."""

from __future__ import annotations

import os
import re
import urllib.request
from datetime import datetime, timezone
from typing import Annotated

import structlog
from icalendar import Calendar, Event as ICSEvent

from app.skills.base import SkillExecutor
from app.skills.schemas import CalendarEvent, CalendarReadRequest, CalendarReadResponse


log = structlog.get_logger()


class CalendarReadSkill(SkillExecutor[CalendarReadRequest, CalendarReadResponse]):
    slug = "calendar_read"

    async def execute(self, input_data: CalendarReadRequest) -> CalendarReadResponse:
        path = input_data.calendar_path or os.environ.get("CALENDAR_PATH", "")

        if not path:
            log.warning("calendar_read.no_path")
            return CalendarReadResponse(events=[], calendar_path=None)

        # Fetch from URL or read from file
        try:
            if path.startswith(("http://", "https://")):
                with urllib.request.urlopen(path, timeout=10) as resp:
                    ics_text = resp.read().decode("utf-8", errors="replace")
            else:
                with open(path, "r", encoding="utf-8") as f:
                    ics_text = f.read()
        except Exception as exc:
            log.error("calendar_read.fetch_failed", path=path, error=str(exc))
            return CalendarReadResponse(events=[], calendar_path=path)

        events = self._parse_ics(ics_text, input_data.start_date, input_data.end_date)
        return CalendarReadResponse(events=events, calendar_path=path)

    def _parse_ics(
        self, ics_text: str, start_date: str, end_date: str
    ) -> list[CalendarEvent]:
        try:
            cal = Calendar.from_ics(ics_text)
        except Exception as exc:
            log.error("calendar_read.parse_failed", error=str(exc))
            return []

        # Parse date range
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            end = end.replace(hour=23, minute=59, second=59)
        except ValueError:
            log.error("calendar_read.invalid_dates", start=start_date, end=end_date)
            return []

        results: list[CalendarEvent] = []
        for component in cal.walk():
            if component.get("dtstart") is None:
                continue

            try:
                dtstart = component.get("dtstart").dt
                if isinstance(dtstart, datetime):
                    event_start = dtstart
                else:
                    event_start = datetime.combine(dtstart, datetime.min.time())

                if event_start.tzinfo is None:
                    event_start = event_start.replace(tzinfo=timezone.utc)

                if not (start <= event_start <= end):
                    continue

                dtend = component.get("dtend")
                event_end = None
                if dtend:
                    dtend_val = dtend.dt
                    if isinstance(dtend_val, datetime):
                        event_end = dtend_val
                    else:
                        event_end = datetime.combine(dtend_val, datetime.min.time())
                        if event_end.tzinfo is None:
                            event_end = event_end.replace(tzinfo=timezone.utc)

                all_day = not isinstance(component.get("dtstart").dt, datetime)

                results.append(
                    CalendarEvent(
                        uid=str(component.get("uid", "")),
                        summary=str(component.get("summary", "")),
                        start=event_start,
                        end=event_end,
                        description=str(component.get("description") or ""),
                        location=str(component.get("location") or "") or None,
                        all_day=all_day,
                    )
                )
            except Exception as exc:
                log.warning("calendar_read.event_skip", error=str(exc))
                continue

        results.sort(key=lambda e: e.start)
        return results


def get_executor() -> CalendarReadSkill:
    return CalendarReadSkill()
