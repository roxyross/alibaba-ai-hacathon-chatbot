"""Settings repository — persists user preferences and settings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from app.db import get_session_factory
from app.models.user_preference import UserPreference
from app.settings.schemas import SettingsUpdateRequest


@dataclass
class _MemSettings:
    id: str
    user_id: str
    theme: str = "dark"
    custom_persona: str = ""
    stream_speed: str = "fast"
    sound_effects: bool = True
    auto_scroll: bool = True
    voice_id: str | None = "aura-asteria-en"
    preferred_provider: str | None = None
    extra_settings: dict[str, Any] = field(default_factory=dict)


class SettingsRepository:
    """Settings persistence. Falls back to in-memory if DATABASE_URL is unset."""

    def __init__(self) -> None:
        self._mem: dict[str, _MemSettings] = {}

    async def get_for_user(self, user_id: str) -> UserPreference | _MemSettings:
        factory = get_session_factory()
        if factory is None:
            if user_id not in self._mem:
                self._mem[user_id] = _MemSettings(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                )
            return self._mem[user_id]

        async with factory() as session:
            row = (
                await session.execute(
                    select(UserPreference).where(UserPreference.user_id == user_id)
                )
            ).scalar_one_or_none()
            if row is None:
                row = UserPreference(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    theme="dark",
                    custom_persona="",
                    stream_speed="fast",
                    sound_effects=True,
                    auto_scroll=True,
                    voice_id="aura-asteria-en",
                    preferred_provider=None,
                    extra_settings={},
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row

    async def update_for_user(
        self, user_id: str, payload: SettingsUpdateRequest
    ) -> UserPreference | _MemSettings:
        extra_payload = dict(payload.extra_settings or {})
        if payload.model_extra:
            extra_payload.update(payload.model_extra)

        factory = get_session_factory()
        if factory is None:
            settings = await self.get_for_user(user_id)
            if payload.theme is not None:
                settings.theme = (payload.theme or "dark")[:20]
            if payload.custom_persona is not None:
                settings.custom_persona = payload.custom_persona
            if payload.stream_speed is not None:
                settings.stream_speed = (payload.stream_speed or "fast")[:20]
            if payload.sound_effects is not None:
                settings.sound_effects = payload.sound_effects
            if payload.auto_scroll is not None:
                settings.auto_scroll = payload.auto_scroll
            if payload.voice_id is not None:
                settings.voice_id = payload.voice_id[:50] if payload.voice_id else None
            if payload.preferred_provider is not None:
                settings.preferred_provider = payload.preferred_provider[:50] if payload.preferred_provider else None
            if extra_payload:
                curr_mem = dict(settings.extra_settings or {})
                curr_mem.update(extra_payload)
                settings.extra_settings = curr_mem
            return settings

        async with factory() as session:
            try:
                row = (
                    await session.execute(
                        select(UserPreference).where(UserPreference.user_id == user_id)
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = UserPreference(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        theme=(payload.theme or "dark")[:20],
                        custom_persona=payload.custom_persona if payload.custom_persona is not None else "",
                        stream_speed=(payload.stream_speed or "fast")[:20],
                        sound_effects=payload.sound_effects if payload.sound_effects is not None else True,
                        auto_scroll=payload.auto_scroll if payload.auto_scroll is not None else True,
                        voice_id=(payload.voice_id or "aura-asteria-en")[:50],
                        preferred_provider=payload.preferred_provider[:50] if payload.preferred_provider else None,
                        extra_settings=extra_payload,
                    )
                    session.add(row)
                else:
                    if payload.theme is not None:
                        row.theme = (payload.theme or "dark")[:20]
                    if payload.custom_persona is not None:
                        row.custom_persona = payload.custom_persona
                    if payload.stream_speed is not None:
                        row.stream_speed = (payload.stream_speed or "fast")[:20]
                    if payload.sound_effects is not None:
                        row.sound_effects = payload.sound_effects
                    if payload.auto_scroll is not None:
                        row.auto_scroll = payload.auto_scroll
                    if payload.voice_id is not None:
                        row.voice_id = payload.voice_id[:50] if payload.voice_id else None
                    if payload.preferred_provider is not None:
                        row.preferred_provider = payload.preferred_provider[:50] if payload.preferred_provider else None
                    if extra_payload:
                        curr = dict(row.extra_settings or {})
                        curr.update(extra_payload)
                        row.extra_settings = curr

                await session.commit()
                await session.refresh(row)
                # Keep in-memory cache in sync
                self._mem[user_id] = _MemSettings(
                    id=row.id,
                    user_id=row.user_id,
                    theme=row.theme,
                    custom_persona=row.custom_persona or "",
                    stream_speed=row.stream_speed,
                    sound_effects=row.sound_effects,
                    auto_scroll=row.auto_scroll,
                    voice_id=row.voice_id or "aura-asteria-en",
                    preferred_provider=row.preferred_provider,
                    extra_settings=dict(row.extra_settings or {}),
                )
                return row
            except Exception as exc:
                await session.rollback()
                import structlog
                structlog.get_logger().warning("settings.update.db_error_fallback", user_id=user_id, error=str(exc))
                # Fallback to in-memory store so user preferences are preserved safely
                mem = self._mem.get(user_id)
                if mem is None:
                    mem = _MemSettings(id=str(uuid.uuid4()), user_id=user_id)
                    self._mem[user_id] = mem
                if payload.theme is not None:
                    mem.theme = (payload.theme or "dark")[:20]
                if payload.custom_persona is not None:
                    mem.custom_persona = payload.custom_persona
                if payload.stream_speed is not None:
                    mem.stream_speed = (payload.stream_speed or "fast")[:20]
                if payload.sound_effects is not None:
                    mem.sound_effects = payload.sound_effects
                if payload.auto_scroll is not None:
                    mem.auto_scroll = payload.auto_scroll
                if payload.voice_id is not None:
                    mem.voice_id = payload.voice_id[:50] if payload.voice_id else None
                if payload.preferred_provider is not None:
                    mem.preferred_provider = payload.preferred_provider[:50] if payload.preferred_provider else None
                if extra_payload:
                    curr_mem = dict(mem.extra_settings or {})
                    curr_mem.update(extra_payload)
                    mem.extra_settings = curr_mem
                return mem

