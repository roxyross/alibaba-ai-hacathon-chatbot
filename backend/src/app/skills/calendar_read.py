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


DEFAULT_DEMO_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//ROXY AI//Personal Calendar//EN
BEGIN:VEVENT
UID:evt-hackathon-demo-01
DTSTAMP:20260908T100000Z
DTSTART:20260909T140000Z
DTEND:20260909T153000Z
SUMMARY:Alibaba AI Hackathon Demo
DESCRIPTION:Present ROXY Personal AI agent architecture and skill integrations
LOCATION:Virtual / Main Stage
END:VEVENT
BEGIN:VEVENT
UID:evt-architecture-sync-02
DTSTAMP:20260908T100000Z
DTSTART:20260910T100000Z
DTEND:20260910T110000Z
SUMMARY:Sprint Architecture Review
DESCRIPTION:Review AI agent skills and real-time telemetry
LOCATION:Meeting Room 3B
END:VEVENT
BEGIN:VEVENT
UID:evt-team-standup-03
DTSTAMP:20260908T100000Z
DTSTART:20260912T090000Z
DTEND:20260912T093000Z
SUMMARY:Weekly Engineering Standup
DESCRIPTION:Cross-agent coordination and scheduler performance
LOCATION:Google Meet
END:VEVENT
END:VCALENDAR"""


class CalendarReadSkill(SkillExecutor[CalendarReadRequest, CalendarReadResponse]):
    slug = "calendar_read"

    async def execute(self, input_data: CalendarReadRequest) -> CalendarReadResponse:
        path = input_data.calendar_path or os.environ.get("CALENDAR_PATH", "")

        if not path:
            log.info("calendar_read.using_default_demo_calendar")
            ics_text = DEFAULT_DEMO_ICS
            path = "demo://personal-calendar.ics"
        else:
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

        start_str = input_data.start_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        end_str = input_data.end_date or "2099-12-31"
        events = self._parse_ics(ics_text, start_str, end_str)
        return CalendarReadResponse(events=events, calendar_path=path)

    def _parse_ics(
        self, ics_text: str, start_date: str, end_date: str
    ) -> list[CalendarEvent]:
        try:
            cal = Calendar.from_ical(ics_text)
        except Exception as exc:
            log.error("calendar_read.parse_failed", error=str(exc))
            return []

        # Parse date range
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
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
