"""Session routes: list, create, get, rename, delete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.chat_history.repository import ChatMessageRepository
from app.session.repository import ChatSessionRepository
from app.session.schemas import (
    SessionCreateRequest,
    SessionResponse,
    SessionUpdateRequest,
)


def _to_response(row) -> SessionResponse:
    """Convert a SQLAlchemy or in-memory session row to a SessionResponse."""
    return SessionResponse(
        id=row.id,
        title=row.title,
        provider=row.provider,
        model=row.model,
        created_at=row.created_at,
        updated_at=row.updated_at,
        message_count=getattr(row, "message_count", 0),
    )


router = APIRouter(prefix="/sessions", tags=["sessions"])
_repo = ChatSessionRepository()
_messages = ChatMessageRepository()


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    current_user: User = Depends(get_current_user),
) -> list[SessionResponse]:
    """List the current user's chat sessions, newest first."""
    rows = await _repo.list_for_user(current_user.id)
    out: list[SessionResponse] = []
    for r in rows:
        msg_count = await _messages.count_for_session(r.id, current_user.id)
        resp = _to_response(r)
        resp.message_count = msg_count
        out.append(resp)
    return out


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreateRequest,
    current_user: User = Depends(get_current_user),
) -> SessionResponse:
    """Create a new chat session with the given provider/model."""
    row = await _repo.create(
        user_id=current_user.id,
        provider=payload.provider,
        model=payload.model,
        title=payload.title,
    )
    return _to_response(row)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    row = await _repo.get(session_id, current_user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    resp = _to_response(row)
    resp.message_count = await _messages.count_for_session(session_id, current_user.id)
    return resp


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    payload: SessionUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    if payload.title is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    row = await _repo.rename(session_id, current_user.id, payload.title)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    resp = _to_response(row)
    resp.message_count = await _messages.count_for_session(session_id, current_user.id)
    return resp


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={204: {"description": "Session deleted"}},
)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    ok = await _repo.delete(session_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return None
