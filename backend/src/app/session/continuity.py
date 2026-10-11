"""Cross-Surface Context Continuity Engine for ROXY 2.0.

Provides shared, real-time context continuity across:
- Chat
- Voice
- CommandBar
- Cowork Canvas
- Open Work Agent
- Tools & File System
- Device App Control

Enables reference resolution for anaphoric pronouns across languages:
e.g. Urdu "Ab iska bug fix karo", Hindi "Is project ko run karo", English "Fix its bug".
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, ClassVar
from pydantic import BaseModel, Field

import structlog

log = structlog.get_logger()


class CrossSurfaceContext(BaseModel):
    """Shared state maintained across all interaction surfaces."""

    user_id: str
    active_surface: str = "chat"  # chat, voice, command_bar, cowork, open_work, device
    active_folder: str | None = None
    active_file: str | None = None
    active_app: str | None = None
    active_task_id: str | None = None
    active_language: str = "en"
    recent_entities: list[dict[str, Any]] = Field(default_factory=list)
    last_interaction_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ResolvedReference(BaseModel):
    original_phrase: str
    target_entity_type: str  # folder, file, app, task, unknown
    target_value: str | None
    resolved_utterance: str
    confidence: float


class CrossSurfaceContinuityEngine:
    """Singleton engine tracking cross-surface state and performing reference resolution."""

    _instance: ClassVar[CrossSurfaceContinuityEngine | None] = None

    # Multilingual anaphora patterns
    _ANAPHORA_PATTERNS: ClassVar[list[tuple[re.Pattern[str], str]]] = [
        # Urdu / Roman Urdu / Hindi: iska, iski, iske, ye, is, usko
        (re.compile(r"\b(iska|iski|iske|is|iss|ye|yeh|usko|uski|us|اس\s*کا|اس\s*کی|اس\s*کے|یہ|اس|اسے|इसका|इसकी|इसके|यह|इस)\b", re.IGNORECASE), "demonstrative"),
        # English: this, that, it, its, the project, the file
        (re.compile(r"\b(this|it|its|that|the\s+folder|the\s+project|the\s+file|the\s+app)\b", re.IGNORECASE), "demonstrative"),
        # Arabic: hatha, thalika
        (re.compile(r"\b(هذا|هذه|ذلك|تلك)\b"), "demonstrative"),
    ]

    def __init__(self) -> None:
        self._contexts: dict[str, CrossSurfaceContext] = {}

    @classmethod
    def get_instance(cls) -> CrossSurfaceContinuityEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_context(self, user_id: str) -> CrossSurfaceContext:
        """Fetch or initialize cross-surface context for a user."""
        if user_id not in self._contexts:
            self._contexts[user_id] = CrossSurfaceContext(user_id=user_id)
        return self._contexts[user_id]

    def update_context(
        self,
        user_id: str,
        surface: str | None = None,
        folder: str | None = None,
        file: str | None = None,
        app: str | None = None,
        task_id: str | None = None,
        language: str | None = None,
        entity: dict[str, Any] | None = None,
    ) -> CrossSurfaceContext:
        """Update active context entities across surfaces."""
        ctx = self.get_context(user_id)
        if surface:
            ctx.active_surface = surface
        if folder is not None:
            ctx.active_folder = folder
        if file is not None:
            ctx.active_file = file
        if app is not None:
            ctx.active_app = app
        if task_id is not None:
            ctx.active_task_id = task_id
        if language:
            ctx.active_language = language

        if entity:
            ctx.recent_entities.insert(0, entity)
            ctx.recent_entities = ctx.recent_entities[:10]  # keep top 10

        ctx.last_interaction_at = datetime.now(timezone.utc).isoformat()
        log.info(
            "context_continuity.updated",
            user_id=user_id,
            surface=ctx.active_surface,
            folder=ctx.active_folder,
            app=ctx.active_app,
        )
        return ctx

    def resolve_reference(self, user_id: str, utterance: str) -> ResolvedReference:
        """Resolve anaphoric pronouns ('iska', 'this', 'it') against active context."""
        ctx = self.get_context(user_id)
        utt = utterance.strip()

        matched = False
        for pattern, _ in self._ANAPHORA_PATTERNS:
            if pattern.search(utt):
                matched = True
                break

        if not matched:
            return ResolvedReference(
                original_phrase=utt,
                target_entity_type="none",
                target_value=None,
                resolved_utterance=utt,
                confidence=1.0,
            )

        # Context priority resolution: File -> Folder -> App -> Task
        target_type = "unknown"
        target_val = None

        # Check intent cues
        utt_lower = utt.lower()
        if any(w in utt_lower for w in ["bug", "code", "file", "test", "function"]):
            if ctx.active_file:
                target_type = "file"
                target_val = ctx.active_file
            elif ctx.active_folder:
                target_type = "folder"
                target_val = ctx.active_folder
        elif any(w in utt_lower for w in ["folder", "project", "dir", "directory", "مجلد"]):
            if ctx.active_folder:
                target_type = "folder"
                target_val = ctx.active_folder
        elif any(w in utt_lower for w in ["app", "kholo", "close", "calculate", "click"]):
            if ctx.active_app:
                target_type = "app"
                target_val = ctx.active_app

        # Fallback to most specific available context
        if not target_val:
            if ctx.active_file:
                target_type = "file"
                target_val = ctx.active_file
            elif ctx.active_folder:
                target_type = "folder"
                target_val = ctx.active_folder
            elif ctx.active_app:
                target_type = "app"
                target_val = ctx.active_app
            elif ctx.active_task_id:
                target_type = "task"
                target_val = ctx.active_task_id

        # Replace pronoun with resolved target value in utterance
        resolved_utt = utt
        if target_val:
            for pattern, _ in self._ANAPHORA_PATTERNS:
                resolved_utt = pattern.sub(f"'{target_val}'", resolved_utt, count=1)

        confidence = 0.95 if target_val else 0.3

        return ResolvedReference(
            original_phrase=utt,
            target_entity_type=target_type,
            target_value=target_val,
            resolved_utterance=resolved_utt,
            confidence=confidence,
        )
