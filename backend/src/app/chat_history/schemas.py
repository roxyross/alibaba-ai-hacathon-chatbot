"""Chat-history Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    """A single persisted chat message."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    provider: Optional[str] = None
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime


class MessageListResponse(BaseModel):
    """Paginated message list for a session."""

    messages: list[MessageResponse]
    session_id: str
    has_more: bool = False
