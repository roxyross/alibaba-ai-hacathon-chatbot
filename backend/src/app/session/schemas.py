"""ChatSession Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateRequest(BaseModel):
    """Create a new chat session."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(default="coordinator", min_length=0, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    session_type: str = Field(default="chat", max_length=20)
    pinned: bool = False


class SessionUpdateRequest(BaseModel):
    """Patch fields on an existing session."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=200)
    pinned: bool | None = None
    archived: bool | None = None


class SessionResponse(BaseModel):
    """Public session representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    provider: str
    model: str
    session_type: str = "chat"
    pinned: bool = False
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
