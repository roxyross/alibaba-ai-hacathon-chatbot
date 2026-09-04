"""Chat-history routes: list messages for a session."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.chat_history.repository import ChatMessageRepository
from app.chat_history.schemas import MessageListResponse, MessageResponse
from app.session.repository import ChatSessionRepository


router = APIRouter(prefix="/sessions", tags=["chat-history"])
_sessions = ChatSessionRepository()
_messages = ChatMessageRepository()


@router.get("/{session_id}/messages", response_model=MessageListResponse)
async def list_messages(
    session_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
) -> MessageListResponse:
    """Return the persisted message history for the current user's session."""
    session = await _sessions.get(session_id, current_user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    rows = await _messages.list_for_session(session_id, current_user.id, limit=limit)
    msgs = [MessageResponse.model_validate(r) for r in rows]
    return MessageListResponse(
        messages=msgs,
        session_id=session_id,
        has_more=len(msgs) == limit,
    )
