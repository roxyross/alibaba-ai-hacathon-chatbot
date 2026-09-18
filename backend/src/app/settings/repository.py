"""Settings repository — persists user preferences and settings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

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
    voice_id: str = "aura-asteria-en"
    preferred_provider: str | None = None


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
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
            return row

    async def update_for_user(
        self, user_id: str, payload: SettingsUpdateRequest
    ) -> UserPreference | _MemSettings:
        factory = get_session_factory()
        if factory is None:
            settings = await self.get_for_user(user_id)
            if payload.theme is not None:
                settings.theme = payload.theme
            if payload.custom_persona is not None:
                settings.custom_persona = payload.custom_persona
            if payload.stream_speed is not None:
                settings.stream_speed = payload.stream_speed
            if payload.sound_effects is not None:
                settings.sound_effects = payload.sound_effects
            if payload.auto_scroll is not None:
                settings.auto_scroll = payload.auto_scroll
            if payload.voice_id is not None:
                settings.voice_id = payload.voice_id
            if payload.preferred_provider is not None:
                settings.preferred_provider = payload.preferred_provider
            return settings

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
                    theme=payload.theme or "dark",
                    custom_persona=payload.custom_persona if payload.custom_persona is not None else "",
                    stream_speed=payload.stream_speed or "fast",
                    sound_effects=payload.sound_effects if payload.sound_effects is not None else True,
                    auto_scroll=payload.auto_scroll if payload.auto_scroll is not None else True,
                    voice_id=payload.voice_id or "aura-asteria-en",
                    preferred_provider=payload.preferred_provider,
                )
                session.add(row)
            else:
                if payload.theme is not None:
                    row.theme = payload.theme
                if payload.custom_persona is not None:
                    row.custom_persona = payload.custom_persona
                if payload.stream_speed is not None:
                    row.stream_speed = payload.stream_speed
                if payload.sound_effects is not None:
                    row.sound_effects = payload.sound_effects
                if payload.auto_scroll is not None:
                    row.auto_scroll = payload.auto_scroll
                if payload.voice_id is not None:
                    row.voice_id = payload.voice_id
                if payload.preferred_provider is not None:
                    row.preferred_provider = payload.preferred_provider

            await session.commit()
            await session.refresh(row)
            return row
