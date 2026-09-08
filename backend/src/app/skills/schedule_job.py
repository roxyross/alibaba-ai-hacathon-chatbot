"""schedule_job skill — create, list, update, cancel scheduled jobs.

Uses an in-memory job store with JSON persistence.
Fires jobs by calling the CronCreate/CronDelete/CronList tools at runtime.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any

import structlog

from app.skills.base import SkillExecutor
from app.skills.schemas import (
    JobAction,
    JobEntry,
    ScheduleJobOp,
    ScheduleJobRequest,
    ScheduleJobResponse,
)


log = structlog.get_logger()

# Minimum interval: 1 minute
MIN_INTERVAL_SECONDS = 60

# Known agents and their valid skills (guardrail: reject unknown agents/skills)
VALID_AGENTS = {"research", "files", "coding", "planner", "browser", "study", "voice", "automation", "email", "web_search"}
VALID_SKILLS = {
    "web_search", "document_rag_query", "store_memory", "retrieve_memory",
    "email_draft", "browser_navigate", "flashcard_generate", "quiz_generate",
    "schedule_job", "calendar_read", "calculator", "speech_to_text", "text_to_speech",
}


def normalize_timezone(tz: str | None) -> str:
    """Safely normalizes user-provided timezone strings to standard IANA identifiers."""
    if not tz or not tz.strip():
        return "UTC"
    raw = tz.strip()
    lower = raw.lower()
    mapping = {
        "karachi": "Asia/Karachi",
        "islamabad": "Asia/Karachi",
        "lahore": "Asia/Karachi",
        "pakistan": "Asia/Karachi",
        "pkt": "Asia/Karachi",
        "gmt+5": "Asia/Karachi",
        "utc+5": "Asia/Karachi",
        "india": "Asia/Kolkata",
        "delhi": "Asia/Kolkata",
        "mumbai": "Asia/Kolkata",
        "kolkata": "Asia/Kolkata",
        "ist": "Asia/Kolkata",
        "gmt+5:30": "Asia/Kolkata",
        "utc+5:30": "Asia/Kolkata",
        "dubai": "Asia/Dubai",
        "uae": "Asia/Dubai",
        "gst": "Asia/Dubai",
        "est": "America/New_York",
        "edt": "America/New_York",
        "new york": "America/New_York",
        "new_york": "America/New_York",
        "eastern": "America/New_York",
        "cst": "America/Chicago",
        "cdt": "America/Chicago",
        "chicago": "America/Chicago",
        "central": "America/Chicago",
        "pst": "America/Los_Angeles",
        "pdt": "America/Los_Angeles",
        "los angeles": "America/Los_Angeles",
        "pacific": "America/Los_Angeles",
        "gmt": "Europe/London",
        "bst": "Europe/London",
        "london": "Europe/London",
        "cet": "Europe/Paris",
        "cest": "Europe/Paris",
        "paris": "Europe/Paris",
        "berlin": "Europe/Berlin",
        "tokyo": "Asia/Tokyo",
        "jst": "Asia/Tokyo",
        "japan": "Asia/Tokyo",
        "sydney": "Australia/Sydney",
        "aest": "Australia/Sydney",
        "utc": "UTC",
    }
    if lower in mapping:
        return mapping[lower]
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(raw)
        return raw
    except Exception:
        for candidate in (raw.title(), f"America/{raw.title()}", f"Europe/{raw.title()}", f"Asia/{raw.title()}"):
            try:
                import zoneinfo
                zoneinfo.ZoneInfo(candidate)
                return candidate
            except Exception:
                pass
        return "UTC"


class JobStore:
    """In-memory + JSON-persisted job store, partitioned by user_id."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, dict[str, Any]]] = {}  # user_id -> job_id -> job dict
        self._path = self._resolve_path()

    def _resolve_path(self) -> Path:
        import os
        raw = os.environ.get("JOB_STORE_PATH", "").strip()
        if raw:
            p = Path(raw)
        else:
            p = Path(__file__).resolve().parents[3] / "data" / "job_store.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for user_id, jobs in raw.items():
                self._jobs[user_id] = {}
                for job_id, job in jobs.items():
                    self._jobs[user_id][job_id] = job
        except Exception:
            pass

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._jobs, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            log.warning("job_store.save_failed", error=str(exc))

    def _ensure_user(self, user_id: str) -> None:
        if user_id not in self._jobs:
            self._jobs[user_id] = {}

    def _job_to_entry(self, job_id: str, job: dict[str, Any]) -> JobEntry:
        return JobEntry(
            job_id=job_id,
            name=job["name"],
            schedule=job["schedule"],
            timezone=job["timezone"],
            action=JobAction(**job["action"]),
            confirm_on_fire=job.get("confirm_on_fire", False),
            status=job.get("status", "active"),
            created_at=datetime.fromisoformat(job["created_at"]),
            next_fire_at=datetime.fromisoformat(job["next_fire_at"]) if job.get("next_fire_at") else None,
            tag=job.get("tag"),
        )

    def create(self, user_id: str, name: str, schedule: str, timezone: str, action: JobAction, confirm_on_fire: bool, tag: str | None = None) -> tuple[str, str | None]:
        """Create a job. Returns (job_id, error)."""
        self._load()
        self._ensure_user(user_id)

        norm_tz = normalize_timezone(timezone)
        # Validate cron / natural language / timestamp with normalized timezone
        parsed, resolved_schedule = self._parse_schedule(schedule, norm_tz)
        if parsed is None:
            return "", f"Invalid schedule: '{schedule}'. Try natural language like 'Every day at 9am' or a cron expression (e.g. '0 8 * * 1-5')."
        next_fire = parsed

        # Validate agent
        if action.agent_slug not in VALID_AGENTS:
            return "", f"Unknown agent: '{action.agent_slug}'. Valid agents: {', '.join(sorted(VALID_AGENTS))}."
        if action.skill_slug and action.skill_slug not in VALID_SKILLS:
            return "", f"Unknown skill: '{action.skill_slug}'. Valid skills: {', '.join(sorted(VALID_SKILLS))}."

        # Sensitive guardrail
        sensitive_skills = {"email_draft", "browser_fill_form", "bank_connect"}
        if action.skill_slug in sensitive_skills and not confirm_on_fire:
            return "", f"Job action uses a sensitive skill ('{action.skill_slug}'). Set confirm_on_fire: true to allow."

        job_id = str(uuid.uuid4())
        now = datetime.now(dt_timezone.utc)
        job = {
            "name": name,
            "schedule": resolved_schedule,
            "timezone": norm_tz,
            "action": action.model_dump(),
            "confirm_on_fire": confirm_on_fire,
            "status": "active",
            "created_at": now.isoformat(),
            "next_fire_at": next_fire.isoformat() if next_fire else None,
            "tag": tag,
        }
        self._jobs[user_id][job_id] = job
        self._save()
        return job_id, None

    def list(self, user_id: str, tag: str | None = None) -> list[JobEntry]:
        self._load()
        self._ensure_user(user_id)
        entries = []
        for job_id, job in self._jobs[user_id].items():
            if tag and job.get("tag") != tag:
                continue
            entries.append(self._job_to_entry(job_id, job))
        # If user partition has no jobs, display all available jobs (e.g. from demo session)
        if not entries:
            for uid, user_jobs in self._jobs.items():
                if uid != user_id:
                    for job_id, job in user_jobs.items():
                        if tag and job.get("tag") != tag:
                            continue
                        entries.append(self._job_to_entry(job_id, job))
        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def cancel(self, user_id: str, job_id: str) -> tuple[bool, str | None]:
        self._load()
        if job_id in self._jobs.get(user_id, {}):
            del self._jobs[user_id][job_id]
            self._save()
            return True, None
        # Cross-partition fallback: locate in any user partition
        for uid, user_jobs in self._jobs.items():
            if job_id in user_jobs:
                del self._jobs[uid][job_id]
                self._save()
                return True, None
        return False, f"Job not found: {job_id}"

    def pause(self, user_id: str, job_id: str) -> tuple[bool, str | None]:
        self._load()
        job = self._jobs.get(user_id, {}).get(job_id)
        if job is None:
            # Cross-partition search
            for uid, user_jobs in self._jobs.items():
                if job_id in user_jobs:
                    job = user_jobs[job_id]
                    break
        if job is None:
            return False, f"Job not found: {job_id}"
        job["status"] = "paused"
        self._save()
        return True, None

    def resume(self, user_id: str, job_id: str) -> tuple[bool, str | None]:
        self._load()
        job = self._jobs.get(user_id, {}).get(job_id)
        if job is None:
            # Cross-partition search
            for uid, user_jobs in self._jobs.items():
                if job_id in user_jobs:
                    job = user_jobs[job_id]
                    break
        if job is None:
            return False, f"Job not found: {job_id}"
        job["status"] = "active"
        self._save()
        return True, None

    def update(self, user_id: str, job_id: str, name: str | None, schedule: str | None, timezone: str | None, action: JobAction | None, confirm_on_fire: bool | None, tag: str | None) -> tuple[bool, str | None]:
        self._load()
        job = self._jobs.get(user_id, {}).get(job_id)
        if job is None:
            return False, f"Job not found: {job_id}"
        if name is not None:
            job["name"] = name
        if schedule is not None:
            parsed, resolved_schedule = self._parse_schedule(schedule)
            if parsed is None:
                return False, f"Invalid schedule: '{schedule}'. Try e.g. 'Every day at 9am' or '0 8 * * 1-5'."
            job["schedule"] = resolved_schedule
            job["next_fire_at"] = parsed.isoformat()
        if timezone is not None:
            job["timezone"] = timezone
        if action is not None:
            if action.agent_slug not in VALID_AGENTS:
                return False, f"Unknown agent: '{action.agent_slug}'"
            if action.skill_slug and action.skill_slug not in VALID_SKILLS:
                return False, f"Unknown skill: '{action.skill_slug}'"
            job["action"] = action.model_dump()
        if confirm_on_fire is not None:
            job["confirm_on_fire"] = confirm_on_fire
        if tag is not None:
            job["tag"] = tag
        self._save()
        return True, None

    @staticmethod
    def _natural_to_cron(text: str) -> str | None:
        """Translates human-readable natural expressions into a 5-segment cron string."""
        t = text.strip().lower()
        # "every N minutes"
        m_min = re.match(r"^every\s+(\d+)\s*(?:min|minute)s?$", t)
        if m_min:
            mins = int(m_min.group(1))
            if 1 <= mins <= 59:
                return f"*/{mins} * * * *"
        if t == "every minute":
            return "* * * * *"
        if t in ("every hour", "hourly"):
            return "0 * * * *"
        m_hr = re.match(r"^every\s+(\d+)\s*(?:hour|hr)s?$", t)
        if m_hr:
            hrs = int(m_hr.group(1))
            if 1 <= hrs <= 23:
                return f"0 */{hrs} * * *"

        # Time extraction: e.g. "at 9am", "at 9:30 pm", "at 14:00"
        tm = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
        hour = 9
        minute = 0
        if tm:
            h = int(tm.group(1))
            mn = int(tm.group(2)) if tm.group(2) else 0
            mer = (tm.group(3) or "").lower()
            if mer == "pm" and h < 12:
                h += 12
            elif mer == "am" and h == 12:
                h = 0
            hour, minute = h, mn

        if any(k in t for k in ("weekday", "monday to friday", "mon-fri")):
            return f"{minute} {hour} * * 1-5"
        if "weekend" in t:
            return f"{minute} {hour} * * 0,6"

        days = {
            "sunday": 0, "sun": 0, "monday": 1, "mon": 1, "tuesday": 2, "tue": 2,
            "wednesday": 3, "wed": 3, "thursday": 4, "thu": 4, "friday": 5, "fri": 5,
            "saturday": 6, "sat": 6,
        }
        for day, num in days.items():
            if day in t:
                return f"{minute} {hour} * * {num}"

        if any(k in t for k in ("every day", "daily", "at ", "morning", "night", "evening")):
            return f"{minute} {hour} * * *"
        if any(k in t for k in ("monthly", "every month")):
            return f"{minute} {hour} 1 * *"

        return None

    @classmethod
    def _parse_schedule(cls, schedule: str, timezone_str: str = "UTC") -> tuple[datetime | None, str]:
        """Parse natural language, cron, or ISO-8601. Returns (next_fire, resolved_schedule)."""
        schedule = schedule.strip()
        from datetime import timedelta
        import zoneinfo

        try:
            tz = zoneinfo.ZoneInfo(timezone_str)
        except Exception:
            tz = dt_timezone.utc

        # ISO-8601 datetime
        if re.match(r"^\d{4}-\d{2}-\d{2}", schedule):
            try:
                dt = datetime.fromisoformat(schedule.replace("Z", "+00:00"))
                return (dt.astimezone(dt_timezone.utc) if dt.tzinfo is None else dt, schedule)
            except Exception:
                return (None, schedule)

        # Standard 5-field Cron
        cron_pattern = re.compile(
            r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+(\S+))?$"
        )
        if cron_pattern.match(schedule):
            now_tz = datetime.now(tz)
            return ((now_tz + timedelta(days=1)).astimezone(dt_timezone.utc), schedule)

        # Natural Language Cron resolution
        resolved = cls._natural_to_cron(schedule)
        if resolved:
            now_tz = datetime.now(tz)
            return ((now_tz + timedelta(days=1)).astimezone(dt_timezone.utc), resolved)

        return (None, schedule)


_job_store: JobStore | None = None


def get_job_store() -> JobStore:
    global _job_store
    if _job_store is None:
        _job_store = JobStore()
    return _job_store


class ScheduleJobSkill(SkillExecutor[ScheduleJobRequest, ScheduleJobResponse]):
    slug = "schedule_job"

    async def execute(self, input_data: ScheduleJobRequest) -> ScheduleJobResponse:
        user_id = input_data.user_id or "anonymous"
        store = get_job_store()
        op = input_data.op

        if op == ScheduleJobOp.CREATE:
            if not input_data.name or not input_data.schedule or not input_data.timezone or not input_data.action:
                return ScheduleJobResponse(
                    op="create", success=False, error="name, schedule, timezone, and action are required for create"
                )
            job_id, err = store.create(
                user_id=user_id,
                name=input_data.name,
                schedule=input_data.schedule,
                timezone=input_data.timezone,
                action=input_data.action,
                confirm_on_fire=input_data.confirm_on_fire,
                tag=input_data.tag,
            )
            if err:
                return ScheduleJobResponse(op="create", success=False, error=err)
            # Wire into APScheduler using resolved schedule and normalized timezone
            job_record = store._jobs.get(user_id, {}).get(job_id)
            effective_schedule = job_record.get("schedule") if job_record else input_data.schedule
            effective_tz = job_record.get("timezone") if job_record else input_data.timezone
            _reschedule_if_running(
                job_id=job_id,
                user_id=user_id,
                schedule=effective_schedule,
                timezone=effective_tz,
                action=input_data.action,
                confirm_on_fire=input_data.confirm_on_fire,
            )
            return ScheduleJobResponse(op="create", success=True, job_id=job_id)

        elif op == ScheduleJobOp.LIST:
            jobs = store.list(user_id=user_id, tag=input_data.tag)
            return ScheduleJobResponse(op="list", success=True, jobs=jobs)

        elif op == ScheduleJobOp.CANCEL:
            if not input_data.job_id:
                return ScheduleJobResponse(op="cancel", success=False, error="job_id is required")
            ok, err = store.cancel(user_id=user_id, job_id=input_data.job_id)
            if ok:
                _cancel_if_running(input_data.job_id)
            return ScheduleJobResponse(op="cancel", success=ok, error=err, job_id=input_data.job_id)

        elif op == ScheduleJobOp.PAUSE:
            if not input_data.job_id:
                return ScheduleJobResponse(op="pause", success=False, error="job_id is required")
            ok, err = store.pause(user_id=user_id, job_id=input_data.job_id)
            if ok:
                _cancel_if_running(input_data.job_id)
            return ScheduleJobResponse(op="pause", success=ok, error=err, job_id=input_data.job_id)

        elif op == ScheduleJobOp.RESUME:
            if not input_data.job_id:
                return ScheduleJobResponse(op="resume", success=False, error="job_id is required")
            ok, err = store.resume(user_id=user_id, job_id=input_data.job_id)
            # Re-register with APScheduler if resume was successful
            if ok:
                job = None
                for uid, user_jobs in store._jobs.items():
                    if input_data.job_id in user_jobs:
                        job = user_jobs[input_data.job_id]
                        break
                if job:
                    _reschedule_if_running(
                        job_id=input_data.job_id,
                        user_id=user_id,
                        schedule=job["schedule"],
                        timezone=job.get("timezone"),
                        action=JobAction(**job["action"]),
                        confirm_on_fire=job.get("confirm_on_fire", False),
                    )
            return ScheduleJobResponse(op="resume", success=ok, error=err, job_id=input_data.job_id)

        elif op == ScheduleJobOp.UPDATE:
            if not input_data.job_id:
                return ScheduleJobResponse(op="update", success=False, error="job_id is required")
            ok, err = store.update(
                user_id=user_id,
                job_id=input_data.job_id,
                name=input_data.name,
                schedule=input_data.schedule,
                timezone=input_data.timezone,
                action=input_data.action,
                confirm_on_fire=input_data.confirm_on_fire,
                tag=input_data.tag,
            )
            if ok and input_data.action:
                _reschedule_if_running(
                    job_id=input_data.job_id,
                    user_id=user_id,
                    schedule=input_data.schedule or "",
                    timezone=input_data.timezone,
                    action=input_data.action,
                    confirm_on_fire=input_data.confirm_on_fire or False,
                )
            return ScheduleJobResponse(op="update", success=ok, error=err, job_id=input_data.job_id)

        return ScheduleJobResponse(op=op.value, success=False, error=f"Unknown op: {op}")


def _cancel_if_running(job_id: str):
    """Remove a job from APScheduler if it is running."""
    try:
        from app.job_scheduler import cancel_scheduled_job
        cancel_scheduled_job(job_id)
    except Exception:
        pass  # Scheduler may not be running


def _reschedule_if_running(job_id: str, user_id: str, schedule: str, timezone: str | None, action: JobAction, confirm_on_fire: bool):
    """If APScheduler is running, update the scheduled firing."""
    try:
        from app.job_scheduler import reschedule_job, cancel_scheduled_job
        cancel_scheduled_job(job_id)
        reschedule_job(
            job_id=job_id,
            user_id=user_id,
            schedule=schedule,
            timezone=timezone,
            agent_slug=action.agent_slug,
            skill_slug=action.skill_slug,
            inputs=action.inputs,
            confirm_on_fire=confirm_on_fire,
        )
    except Exception:
        pass  # Scheduler may not be running (e.g., in test env)


def get_executor() -> ScheduleJobSkill:
    return ScheduleJobSkill()
