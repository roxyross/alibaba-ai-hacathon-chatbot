"""EmailRepository — SQLAlchemy async with thread-safe in-memory fallback.

Enforces strict multi-tenant isolation on all email messages, drafts,
outbox items, and delivery status updates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import delete, select

from app.db import get_session_factory
from app.models.email_message import EmailMessage

log = structlog.get_logger()

# Module-level thread-safe in-memory store keyed by user_id
_MEM_EMAIL_MESSAGES: dict[str, list[dict[str, Any]]] = {}


def clear_in_memory_stores() -> None:
    """Clear all in-memory email stores (used for test isolation)."""
    _MEM_EMAIL_MESSAGES.clear()


class EmailRepository:
    """Repository managing user EmailMessage records with multi-tenant guarantees."""

    def __init__(self) -> None:
        self._mem = _MEM_EMAIL_MESSAGES

    @staticmethod
    def _to_iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)

    @staticmethod
    def _parse_email_list(val: list[str] | str | None) -> list[str]:
        if val is None:
            return []
        if isinstance(val, list):
            return [str(item).strip() for item in val if str(item).strip()]
        if isinstance(val, str):
            return [item.strip() for item in val.split(",") if item.strip()]
        return []

    @classmethod
    def _format_email_str(cls, val: list[str] | str | None) -> str | None:
        items = cls._parse_email_list(val)
        return ", ".join(items) if items else None

    @classmethod
    def _to_dict(cls, msg: EmailMessage) -> dict[str, Any]:
        return {
            "id": msg.id,
            "user_id": msg.user_id,
            "to": msg.to,
            "subject": msg.subject,
            "body": msg.body,
            "cc": cls._parse_email_list(msg.cc),
            "bcc": cls._parse_email_list(msg.bcc),
            "status": msg.status,
            "delivery_error": msg.delivery_error,
            "message_id": msg.message_id,
            "sent_at": cls._to_iso(msg.sent_at),
            "created_at": cls._to_iso(msg.created_at),
            "updated_at": cls._to_iso(msg.updated_at),
        }


    async def list_messages(
        self,
        user_id: str,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List all emails/drafts belonging to user_id, optionally filtered by status & search."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(EmailMessage).where(EmailMessage.user_id == user_id)
                    if status is not None:
                        stmt = stmt.where(EmailMessage.status == status)
                    if search:
                        term = f"%{search.lower()}%"
                        stmt = stmt.where(
                            EmailMessage.subject.ilike(term)
                            | EmailMessage.body.ilike(term)
                            | EmailMessage.to.ilike(term)
                        )
                    stmt = stmt.order_by(EmailMessage.created_at.desc()).offset(offset).limit(limit)
                    result = await session.execute(stmt)
                    rows = result.scalars().all()
                    return [self._to_dict(r) for r in rows]
            except Exception as exc:
                log.warning("email_repo.list_db_fallback", error=str(exc))

        # In-memory fallback
        user_messages = self._mem.get(user_id, [])
        filtered: list[dict[str, Any]] = []
        for m in user_messages:
            if status and m.get("status") != status:
                continue
            if search:
                term = search.lower()
                subj = (m.get("subject") or "").lower()
                body = (m.get("body") or "").lower()
                to_addr = (m.get("to") or "").lower()
                if term not in subj and term not in body and term not in to_addr:
                    continue
            filtered.append(m)

        # Sort newest first
        filtered.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return filtered[offset : offset + limit]

    async def get_message(self, user_id: str, message_id: str) -> dict[str, Any] | None:
        """Get a single email message ensuring user ownership."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(EmailMessage).where(
                        EmailMessage.id == message_id,
                        EmailMessage.user_id == user_id,
                    )
                    result = await session.execute(stmt)
                    row = result.scalar_one_or_none()
                    if row:
                        return self._to_dict(row)
                    return None
            except Exception as exc:
                log.warning("email_repo.get_db_fallback", error=str(exc))

        # In-memory fallback
        for m in self._mem.get(user_id, []):
            if m.get("id") == message_id:
                return m
        return None

    async def create_message(
        self,
        user_id: str,
        to: str,
        subject: str,
        body: str,
        cc: list[str] | str | None = None,
        bcc: list[str] | str | None = None,
        status: str = "draft",
        delivery_error: str | None = None,
        message_id: str | None = None,
        sent_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Create and persist an EmailMessage record for user_id."""
        new_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        cc_str = self._format_email_str(cc)
        bcc_str = self._format_email_str(bcc)

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    obj = EmailMessage(
                        id=new_id,
                        user_id=user_id,
                        to=to,
                        subject=subject,
                        body=body,
                        cc=cc_str,
                        bcc=bcc_str,
                        status=status,
                        delivery_error=delivery_error,
                        message_id=message_id,
                        sent_at=sent_at,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(obj)
                    await session.commit()
                    await session.refresh(obj)
                    return self._to_dict(obj)
            except Exception as exc:
                log.warning("email_repo.create_db_fallback", error=str(exc))

        # In-memory fallback
        cc_list = self._parse_email_list(cc)
        bcc_list = self._parse_email_list(bcc)

        record: dict[str, Any] = {
            "id": new_id,
            "user_id": user_id,
            "to": to,
            "subject": subject,
            "body": body,
            "cc": cc_list,
            "bcc": bcc_list,
            "status": status,
            "delivery_error": delivery_error,
            "message_id": message_id,
            "sent_at": self._to_iso(sent_at),
            "created_at": self._to_iso(now),
            "updated_at": self._to_iso(now),
        }
        if user_id not in self._mem:
            self._mem[user_id] = []
        self._mem[user_id].append(record)
        return record

    async def update_message(
        self,
        user_id: str,
        message_id: str,
        to: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        cc: list[str] | str | None = None,
        bcc: list[str] | str | None = None,
        status: str | None = None,
        delivery_error: str | None = None,
        message_id_str: str | None = None,
        sent_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Update an existing email or draft with user ownership validation."""
        now = datetime.now(UTC)

        cc_str = self._format_email_str(cc)
        bcc_str = self._format_email_str(bcc)

        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = select(EmailMessage).where(
                        EmailMessage.id == message_id,
                        EmailMessage.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    obj = res.scalar_one_or_none()
                    if not obj:
                        return None

                    if to is not None:
                        obj.to = to
                    if subject is not None:
                        obj.subject = subject
                    if body is not None:
                        obj.body = body
                    if cc is not None:
                        obj.cc = cc_str
                    if bcc is not None:
                        obj.bcc = bcc_str
                    if status is not None:
                        obj.status = status
                    if delivery_error is not None:
                        obj.delivery_error = delivery_error
                    if message_id_str is not None:
                        obj.message_id = message_id_str
                    if sent_at is not None:
                        obj.sent_at = sent_at
                    obj.updated_at = now

                    await session.commit()
                    await session.refresh(obj)
                    return self._to_dict(obj)
            except Exception as exc:
                log.warning("email_repo.update_db_fallback", error=str(exc))

        # In-memory fallback
        for m in self._mem.get(user_id, []):
            if m.get("id") == message_id:
                if to is not None:
                    m["to"] = to
                if subject is not None:
                    m["subject"] = subject
                if body is not None:
                    m["body"] = body
                if cc is not None:
                    m["cc"] = self._parse_email_list(cc)
                if bcc is not None:
                    m["bcc"] = self._parse_email_list(bcc)
                if status is not None:
                    m["status"] = status
                if delivery_error is not None:
                    m["delivery_error"] = delivery_error
                if message_id_str is not None:
                    m["message_id"] = message_id_str
                if sent_at is not None:
                    m["sent_at"] = self._to_iso(sent_at)
                m["updated_at"] = self._to_iso(now)
                return m
        return None

    async def delete_message(self, user_id: str, message_id: str) -> bool:
        """Delete an email message or draft with strict tenant isolation."""
        factory = get_session_factory()
        if factory is not None:
            try:
                async with factory() as session:
                    stmt = delete(EmailMessage).where(
                        EmailMessage.id == message_id,
                        EmailMessage.user_id == user_id,
                    )
                    res = await session.execute(stmt)
                    await session.commit()
                    row_count = int(getattr(res, "rowcount", 0) or 0)
                    return row_count > 0
            except Exception as exc:
                log.warning("email_repo.delete_db_fallback", error=str(exc))

        # In-memory fallback
        user_messages = self._mem.get(user_id, [])
        for idx, m in enumerate(user_messages):
            if m.get("id") == message_id:
                user_messages.pop(idx)
                return True
        return False
