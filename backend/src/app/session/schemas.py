"""ChatSession Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateRequest(BaseModel):
    """Create a new chat session."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(default="coordinator", min_length=0, max_length=100)
    title: Optional[str] = Field(default=None, max_length=200)


class SessionUpdateRequest(BaseModel):
    """Patch fields on an existing session (currently just title)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(default=None, max_length=200)


class SessionResponse(BaseModel):
    """Public session representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str]
    provider: str
    model: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
