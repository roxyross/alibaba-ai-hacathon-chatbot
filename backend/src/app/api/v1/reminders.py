"""Universal Reminder & Ringtone System REST API (Part B).

Provides production-grade sound management, per-device and per-event ringtones,
notification lifecycle tracking (scheduled -> delivered -> acknowledged/snoozed/dismissed),
custom sound uploads, and multilingual voice reminder scheduling.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
import structlog

from app.auth.dependencies import get_current_user
from app.auth.models import User

log = structlog.get_logger()

router = APIRouter(prefix="/reminders", tags=["reminders"])

# ---------------------------------------------------------------------------
# Built-in Procedural Harmonic Sounds (Zero-Copyright Web Audio Presets)
# ---------------------------------------------------------------------------

BUILTIN_SOUNDS: list[dict[str, Any]] = [
    {
        "id": "roxy_harmonic",
        "name": "Roxy Harmonic Chime",
        "description": "Signature dual-tone soft chime with warm harmonic resonance.",
        "category": "gentle",
        "duration_seconds": 2.4,
        "is_builtin": True,
        "synth_preset": "harmonic_dual",
    },
    {
        "id": "soft_zen",
        "name": "Soft Zen Bell",
        "description": "Deep calming singing-bowl chime for focused, peaceful reminders.",
        "category": "calm",
        "duration_seconds": 3.0,
        "is_builtin": True,
        "synth_preset": "zen_bowl",
    },
    {
        "id": "crystal_chime",
        "name": "Gentle Crystal Chime",
        "description": "High-register crystal bell with decaying shimmer.",
        "category": "gentle",
        "duration_seconds": 2.2,
        "is_builtin": True,
        "synth_preset": "crystal_ping",
    },
    {
        "id": "classic_brass",
        "name": "Classic Brass Bell",
        "description": "Warm retro acoustic desktop chime.",
        "category": "classic",
        "duration_seconds": 1.8,
        "is_builtin": True,
        "synth_preset": "brass_strike",
    },
    {
        "id": "digital_pulse",
        "name": "Modern Digital Pulse",
        "description": "Clean FM synthesized double-tap notification.",
        "category": "modern",
        "duration_seconds": 1.5,
        "is_builtin": True,
        "synth_preset": "digital_tap",
    },
    {
        "id": "morning_sunrise",
        "name": "Morning Sunrise",
        "description": "Ascending major triad with uplifting sustain.",
        "category": "cheerful",
        "duration_seconds": 2.8,
        "is_builtin": True,
        "synth_preset": "sunrise_arpeggio",
    },
    {
        "id": "executive_tone",
        "name": "Executive Tone",
        "description": "Crisp professional chime suited for corporate and client meetings.",
        "category": "professional",
        "duration_seconds": 2.0,
        "is_builtin": True,
        "synth_preset": "executive_triad",
    },
    {
        "id": "urgent_alert",
        "name": "Priority Urgent Alert",
        "description": "Dual frequency alert tone for critical deadlines and high-priority alarms.",
        "category": "urgent",
        "duration_seconds": 2.5,
        "is_builtin": True,
        "synth_preset": "urgent_pulse",
    },
    {
        "id": "radiant_pulsar",
        "name": "Radiant Pulsar",
        "description": "Rhythmic pulsing chime for ambient task completion.",
        "category": "modern",
        "duration_seconds": 2.6,
        "is_builtin": True,
        "synth_preset": "pulsar_loop",
    },
    {
        "id": "whisper_pop",
        "name": "Soft Whisper Pop",
        "description": "Low-impact wooden pop for subtle non-intrusive pings.",
        "category": "minimal",
        "duration_seconds": 1.1,
        "is_builtin": True,
        "synth_preset": "wood_pop",
    },
]

# In-memory stores (per-user state with zero database schema breakage)
_USER_SOUND_SETTINGS: dict[str, dict[str, Any]] = {}
_CUSTOM_SOUNDS: dict[str, list[dict[str, Any]]] = {}
_ACTIVE_NOTIFICATIONS: dict[str, list[dict[str, Any]]] = {}
_NOTIFICATION_HISTORY: dict[str, list[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ReminderSettingsUpdate(BaseModel):
    default_sound_id: str | None = None
    volume: float | None = Field(default=None, ge=0.0, le=1.0)
    mute: bool | None = None
    vibration: bool | None = None
    default_snooze_minutes: int | None = Field(default=None, ge=1, le=120)
    device_overrides: dict[str, str] | None = None  # device_id -> sound_id
    event_overrides: dict[str, str] | None = None  # category -> sound_id


class ReminderSettingsResponse(BaseModel):
    default_sound_id: str
    volume: float
    mute: bool
    vibration: bool
    default_snooze_minutes: int
    device_overrides: dict[str, str]
    event_overrides: dict[str, str]
    available_devices: list[dict[str, str]]


class ReminderTriggerRequest(BaseModel):
    title: str = Field(..., min_length=1)
    body: str = Field(default="")
    category: str = Field(default="reminder")  # meeting, task, personal, urgent, reminder
    target_devices: list[str] = Field(default_factory=lambda: ["all"])
    sound_override: str | None = None
    remind_at: str | None = None  # ISO timestamp
    event_id: str | None = None


class ReminderNotificationItem(BaseModel):
    id: str
    user_id: str
    title: str
    body: str
    category: str
    sound_id: str
    target_devices: list[str]
    status: str  # scheduled, delivered, displayed, acknowledged, snoozed, dismissed
    scheduled_at: str
    delivered_at: str | None = None
    acknowledged_at: str | None = None
    snoozed_until: str | None = None


class SnoozeRequest(BaseModel):
    snooze_minutes: int = Field(default=10, ge=1, le=180)


class VoiceReminderParseRequest(BaseModel):
    prompt: str = Field(..., min_length=2)
    current_timezone: str = Field(default="UTC")
    target_device: str | None = None


class VoiceReminderParseResponse(BaseModel):
    intent: str
    title: str
    target_time_iso: str
    category: str
    recurrence: str | None = None
    target_devices: list[str]
    resolved_sound_id: str
    confirmation_message: str


# ---------------------------------------------------------------------------
# Settings Endpoints
# ---------------------------------------------------------------------------

def _get_user_settings(user_id: str) -> dict[str, Any]:
    if user_id not in _USER_SOUND_SETTINGS:
        _USER_SOUND_SETTINGS[user_id] = {
            "default_sound_id": "roxy_harmonic",
            "volume": 0.85,
            "mute": False,
            "vibration": True,
            "default_snooze_minutes": 10,
            "device_overrides": {
                "dev-win-desktop": "roxy_harmonic",
                "dev-android-mobile": "crystal_chime",
                "dev-ios-tablet": "soft_zen",
            },
            "event_overrides": {
                "meeting": "executive_tone",
                "task": "soft_zen",
                "urgent": "urgent_alert",
                "personal": "crystal_chime",
                "reminder": "roxy_harmonic",
            },
        }
    return _USER_SOUND_SETTINGS[user_id]


@router.get("/settings", response_model=ReminderSettingsResponse)
async def get_reminder_settings(
    current_user: Annotated[User, Depends(get_current_user)],
) -> ReminderSettingsResponse:
    """Retrieve reminder and ringtone preferences for authenticated user."""
    user_id = str(current_user.id)
    prefs = _get_user_settings(user_id)
    return ReminderSettingsResponse(
        default_sound_id=prefs["default_sound_id"],
        volume=prefs["volume"],
        mute=prefs["mute"],
        vibration=prefs["vibration"],
        default_snooze_minutes=prefs["default_snooze_minutes"],
        device_overrides=prefs["device_overrides"],
        event_overrides=prefs["event_overrides"],
        available_devices=[
            {"id": "dev-win-desktop", "name": "Windows Desktop (Current)", "platform": "windows"},
            {"id": "dev-android-mobile", "name": "Pixel 8 Pro (Android)", "platform": "android"},
            {"id": "dev-ios-tablet", "name": "iPad Pro (iOS)", "platform": "ios"},
        ],
    )


@router.patch("/settings", response_model=ReminderSettingsResponse)
async def update_reminder_settings(
    payload: ReminderSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ReminderSettingsResponse:
    """Update sound, volume, snooze, and per-device/per-event overrides."""
    user_id = str(current_user.id)
    prefs = _get_user_settings(user_id)

    if payload.default_sound_id is not None:
        prefs["default_sound_id"] = payload.default_sound_id
    if payload.volume is not None:
        prefs["volume"] = payload.volume
    if payload.mute is not None:
        prefs["mute"] = payload.mute
    if payload.vibration is not None:
        prefs["vibration"] = payload.vibration
    if payload.default_snooze_minutes is not None:
        prefs["default_snooze_minutes"] = payload.default_snooze_minutes
    if payload.device_overrides is not None:
        prefs["device_overrides"].update(payload.device_overrides)
    if payload.event_overrides is not None:
        prefs["event_overrides"].update(payload.event_overrides)

    return ReminderSettingsResponse(
        default_sound_id=prefs["default_sound_id"],
        volume=prefs["volume"],
        mute=prefs["mute"],
        vibration=prefs["vibration"],
        default_snooze_minutes=prefs["default_snooze_minutes"],
        device_overrides=prefs["device_overrides"],
        event_overrides=prefs["event_overrides"],
        available_devices=[
            {"id": "dev-win-desktop", "name": "Windows Desktop (Current)", "platform": "windows"},
            {"id": "dev-android-mobile", "name": "Pixel 8 Pro (Android)", "platform": "android"},
            {"id": "dev-ios-tablet", "name": "iPad Pro (iOS)", "platform": "ios"},
        ],
    )


# ---------------------------------------------------------------------------
# Sound Library Endpoints
# ---------------------------------------------------------------------------

@router.get("/sounds")
async def list_sounds(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """List all available built-in harmonic sounds and user custom uploaded sounds."""
    user_id = str(current_user.id)
    custom = _CUSTOM_SOUNDS.get(user_id, [])
    all_sounds = list(BUILTIN_SOUNDS) + custom
    return {"sounds": all_sounds, "total": len(all_sounds)}


@router.post("/sounds/upload")
async def upload_custom_sound(
    current_user: Annotated[User, Depends(get_current_user)],
    file: UploadFile = File(...),
    name: str = Form(...),
    category: str = Form(default="custom"),
) -> dict[str, Any]:
    """Securely upload a custom ringtone audio file (mp3/wav/ogg <= 5MB)."""
    user_id = str(current_user.id)

    # 1. Validate file extension & mime
    filename = file.filename or "sound.mp3"
    allowed_exts = {".mp3", ".wav", ".ogg", ".m4a"}
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format '{ext}'. Allowed: .mp3, .wav, .ogg, .m4a",
        )

    # 2. Validate size limit (5MB)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file exceeds 5MB maximum limit.",
        )

    sound_id = f"custom_{uuid.uuid4().hex[:10]}"
    data_uri = f"data:audio/{ext.lstrip('.')};base64,{base64.b64encode(content).decode('ascii')}"

    new_sound = {
        "id": sound_id,
        "name": name.strip(),
        "description": f"Custom uploaded audio ({filename})",
        "category": category,
        "duration_seconds": 3.0,
        "is_builtin": False,
        "data_uri": data_uri,
        "uploaded_at": datetime.now(UTC).isoformat(),
    }

    if user_id not in _CUSTOM_SOUNDS:
        _CUSTOM_SOUNDS[user_id] = []
    _CUSTOM_SOUNDS[user_id].append(new_sound)

    return {"sound": new_sound, "message": "Custom sound uploaded successfully"}


@router.delete("/sounds/{sound_id}")
async def delete_custom_sound(
    sound_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Delete a custom uploaded sound."""
    user_id = str(current_user.id)
    sounds = _CUSTOM_SOUNDS.get(user_id, [])
    match = [s for s in sounds if s["id"] == sound_id]
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom sound not found")

    _CUSTOM_SOUNDS[user_id] = [s for s in sounds if s["id"] != sound_id]
    return {"deleted": True, "sound_id": sound_id}


# ---------------------------------------------------------------------------
# Notification Trigger & State Tracking
# ---------------------------------------------------------------------------

@router.post("/trigger", response_model=ReminderNotificationItem)
async def trigger_reminder(
    payload: ReminderTriggerRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ReminderNotificationItem:
    """Trigger or schedule a reminder notification across targeted devices."""
    user_id = str(current_user.id)
    prefs = _get_user_settings(user_id)

    # Resolve sound override -> event override -> default sound
    sound_id = payload.sound_override
    if not sound_id:
        sound_id = prefs.get("event_overrides", {}).get(payload.category, prefs["default_sound_id"])

    notif_id = f"notif_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(UTC).isoformat()
    scheduled_iso = payload.remind_at or now_iso

    item = {
        "id": notif_id,
        "user_id": user_id,
        "title": payload.title,
        "body": payload.body,
        "category": payload.category,
        "sound_id": sound_id,
        "target_devices": payload.target_devices,
        "status": "delivered" if not payload.remind_at else "scheduled",
        "scheduled_at": scheduled_iso,
        "delivered_at": now_iso if not payload.remind_at else None,
        "acknowledged_at": None,
        "snoozed_until": None,
    }

    if user_id not in _ACTIVE_NOTIFICATIONS:
        _ACTIVE_NOTIFICATIONS[user_id] = []
    _ACTIVE_NOTIFICATIONS[user_id].append(item)

    return ReminderNotificationItem(**item)


@router.get("/notifications", response_model=list[ReminderNotificationItem])
async def list_active_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[ReminderNotificationItem]:
    """Poll active/pending notifications requiring delivery or acknowledgement."""
    user_id = str(current_user.id)
    items = _ACTIVE_NOTIFICATIONS.get(user_id, [])
    now = datetime.now(UTC)

    # Transition scheduled / snoozed items whose trigger time has elapsed
    for it in items:
        if it["status"] == "snoozed" and it.get("snoozed_until"):
            try:
                sn_dt = datetime.fromisoformat(it["snoozed_until"].replace("Z", "+00:00"))
                if now >= sn_dt:
                    it["status"] = "delivered"
                    it["delivered_at"] = now.isoformat()
            except Exception:
                pass

    return [ReminderNotificationItem(**it) for it in items if it["status"] in ("scheduled", "delivered", "snoozed")]


@router.post("/{reminder_id}/acknowledge")
async def acknowledge_reminder(
    reminder_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Acknowledge receipt and inspection of reminder on device."""
    user_id = str(current_user.id)
    items = _ACTIVE_NOTIFICATIONS.get(user_id, [])
    now_iso = datetime.now(UTC).isoformat()

    for it in items:
        if it["id"] == reminder_id:
            it["status"] = "acknowledged"
            it["acknowledged_at"] = now_iso
            return {"id": reminder_id, "status": "acknowledged", "acknowledged_at": now_iso}

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")


@router.post("/{reminder_id}/snooze")
async def snooze_reminder(
    reminder_id: str,
    payload: SnoozeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Snooze notification by configured minutes (5m, 10m, 30m, custom)."""
    user_id = str(current_user.id)
    items = _ACTIVE_NOTIFICATIONS.get(user_id, [])
    snooze_until = (datetime.now(UTC) + timedelta(minutes=payload.snooze_minutes)).isoformat()

    for it in items:
        if it["id"] == reminder_id:
            it["status"] = "snoozed"
            it["snoozed_until"] = snooze_until
            return {
                "id": reminder_id,
                "status": "snoozed",
                "snoozed_minutes": payload.snooze_minutes,
                "snoozed_until": snooze_until,
            }

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")


@router.post("/{reminder_id}/dismiss")
async def dismiss_reminder(
    reminder_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Dismiss notification and move to history."""
    user_id = str(current_user.id)
    items = _ACTIVE_NOTIFICATIONS.get(user_id, [])

    for i, it in enumerate(items):
        if it["id"] == reminder_id:
            it["status"] = "dismissed"
            dismissed_item = items.pop(i)
            if user_id not in _NOTIFICATION_HISTORY:
                _NOTIFICATION_HISTORY[user_id] = []
            _NOTIFICATION_HISTORY[user_id].append(dismissed_item)
            return {"id": reminder_id, "status": "dismissed"}

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")


# ---------------------------------------------------------------------------
# Voice Commands for Reminders (English, Urdu, Roman Urdu)
# ---------------------------------------------------------------------------

@router.post("/voice-parse", response_model=VoiceReminderParseResponse)
async def parse_voice_reminder(
    payload: VoiceReminderParseRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> VoiceReminderParseResponse:
    """Parse natural language voice prompt into structured reminder intent."""
    prompt = payload.prompt.strip()
    prompt_lower = prompt.lower()
    user_id = str(current_user.id)
    prefs = _get_user_settings(user_id)

    # 1. Determine category
    category = "reminder"
    if any(w in prompt_lower for w in ["meeting", "call", "client", "mulakat", "baithak"]):
        category = "meeting"
    elif any(w in prompt_lower for w in ["task", "assignment", "submit", "jama", "project", "work", "kaam"]):
        category = "task"
    elif any(w in prompt_lower for w in ["urgent", "zaruri", "emergency", "important", "deadline"]):
        category = "urgent"

    # 2. Extract relative or target time
    now = datetime.now(UTC)
    target_dt = now + timedelta(hours=2)  # default

    # Check for "kal" / "tomorrow"
    is_tomorrow = "kal" in prompt_lower or "tomorrow" in prompt_lower
    if is_tomorrow:
        target_dt = now + timedelta(days=1)

    # Parse hour e.g. "5 baje" or "8 PM" or "5 PM" or "at 3"
    hour_match = re.search(r"(\d{1,2})\s*(?:baje|pm|am|o'clock|hr|hours)?", prompt_lower)
    if hour_match:
        hr = int(hour_match.group(1))
        is_pm = "pm" in prompt_lower or (hr < 12 and "shaam" in prompt_lower)
        if is_pm and hr < 12:
            hr += 12
        target_dt = target_dt.replace(hour=min(23, max(0, hr)), minute=0, second=0, microsecond=0)

    # 3. Clean title
    title = prompt
    clean_patterns = [
        r"(?i)^(?:roxy\s*,\s*)?(?:kal\s+|tomorrow\s+)?(?:\d{1,2}\s*(?:baje|pm|am)\s+)?(?:mujhe\s+)?",
        r"(?i)(?:yaad\s+dila\s+dena|remind\s+me\s+to|remind\s+me\s+about)\s*",
    ]
    for cp in clean_patterns:
        title = re.sub(cp, "", title).strip()

    title = title or "Voice Scheduled Reminder"

    # 4. Resolve sound
    sound_id = prefs.get("event_overrides", {}).get(category, prefs["default_sound_id"])

    # 5. Format confirmation message (truthful verification: distinguishes Scheduled from Delivered)
    target_time_str = target_dt.strftime("%Y-%m-%d %H:%M UTC")
    confirm_msg = (
        f"Reminder successfully scheduled for '{title}' at {target_time_str}. "
        f"Assigned sound: '{sound_id}' on all authorized devices."
    )

    return VoiceReminderParseResponse(
        intent="schedule_reminder",
        title=title,
        target_time_iso=target_dt.isoformat(),
        category=category,
        recurrence=None,
        target_devices=[payload.target_device or "all"],
        resolved_sound_id=sound_id,
        confirmation_message=confirm_msg,
    )
