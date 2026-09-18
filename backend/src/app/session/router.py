"""Session routes: list, create, get, rename, pin, archive, delete."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user, get_optional_current_user
from app.auth.models import User
from app.chat_history.repository import ChatMessageRepository
from app.session.repository import ChatSessionRepository
from app.session.schemas import (
    SessionCreateRequest,
    SessionResponse,
    SessionUpdateRequest,
)


def _to_response(row: Any) -> SessionResponse:
    """Convert a SQLAlchemy or in-memory session row to a SessionResponse."""
    return SessionResponse(
        id=row.id,
        title=row.title,
        provider=row.provider,
        model=row.model,
        session_type=getattr(row, "session_type", "chat") or "chat",
        pinned=bool(getattr(row, "pinned", False)),
        archived_at=getattr(row, "archived_at", None),
        created_at=row.created_at,
        updated_at=row.updated_at,
        message_count=getattr(row, "message_count", 0),
    )


router = APIRouter(prefix="/sessions", tags=["sessions"])
_repo = ChatSessionRepository()
_messages = ChatMessageRepository()


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    session_type: str | None = None,
    include_archived: bool = False,
    current_user: Annotated[User | None, Depends(get_optional_current_user)] = None,
) -> list[SessionResponse]:
    """List the current user's chat sessions, pinned first, newest first."""
    if current_user is None:
        return []
    rows = await _repo.list_for_user(
        current_user.id, session_type=session_type, include_archived=include_archived
    )
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
    current_user: Annotated[User, Depends(get_current_user)],
) -> SessionResponse:
    """Create a new chat session with the given provider/model and session_type."""
    row = await _repo.create(
        user_id=current_user.id,
        provider=payload.provider,
        model=payload.model,
        title=payload.title,
        session_type=payload.session_type,
        pinned=payload.pinned,
    )
    return _to_response(row)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> SessionResponse:
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
    current_user: Annotated[User, Depends(get_current_user)],
) -> SessionResponse:
    if payload.title is None and payload.pinned is None and payload.archived is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    row = await _repo.update(
        session_id,
        current_user.id,
        title=payload.title,
        pinned=payload.pinned,
        archived=payload.archived,
    )
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
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    ok = await _repo.delete(session_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return None
