"""Email API router — Outbox, drafts, AI composing, tone polishing, and dispatch.

All operations require user authentication and enforce strict multi-tenant isolation.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.emails.repository import EmailRepository
from app.emails.service import EmailService

router = APIRouter(prefix="/emails", tags=["emails"])

_repo = EmailRepository()
_service = EmailService(_repo)


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class CreateEmailRequest(BaseModel):
    to: str = Field(..., min_length=1, max_length=500)
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(...)
    cc: list[str] | None = Field(default=None)
    bcc: list[str] | None = Field(default=None)
    status: str = Field(default="draft")


class UpdateEmailRequest(BaseModel):
    to: str | None = Field(default=None, min_length=1, max_length=500)
    subject: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = Field(default=None)
    cc: list[str] | None = Field(default=None)
    bcc: list[str] | None = Field(default=None)
    status: str | None = Field(default=None)


class ComposeAIRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    tone: str = Field(default="professional")
    recipient_name: str | None = Field(default=None)


class PolishAIRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=500)
    body: str = Field(...)
    tone: str = Field(default="professional")


class SendDraftRequest(BaseModel):
    smtp_user: str | None = Field(default=None)
    smtp_pass: str | None = Field(default=None)
    smtp_host: str | None = Field(default=None)
    smtp_port: int | None = Field(default=None)
    smtp_from: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_emails(
    status_filter: str | None = Query(default=None, alias="status", description="Filter by status (draft, sent, failed)"),
    search: str | None = Query(default=None, description="Search term in subject, body, or recipient"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List authenticated user's emails and drafts with optional status/search filters."""
    user_id = str(user.id)
    messages = await _repo.list_messages(
        user_id=user_id,
        status=status_filter,
        search=search,
        limit=limit,
        offset=offset,
    )
    return {
        "emails": messages,
        "total": len(messages),
        "limit": limit,
        "offset": offset,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_email(
    body: CreateEmailRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new draft or queued email message for the authenticated user."""
    user_id = str(user.id)
    created = await _repo.create_message(
        user_id=user_id,
        to=body.to.strip(),
        subject=body.subject.strip(),
        body=body.body.strip(),
        cc=body.cc,
        bcc=body.bcc,
        status=body.status,
    )
    return {"email": created, "message": "Email created successfully."}


@router.get("/templates")
async def get_templates(
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve the curated professional email template library."""
    templates = _service.get_templates()
    return {"templates": templates, "total": len(templates)}


@router.post("/compose-ai")
async def compose_with_ai(
    body: ComposeAIRequest,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate structured email subject and body using natural language prompt and tone."""
    result = _service.compose_with_ai(
        prompt=body.prompt,
        tone=body.tone,
        recipient_name=body.recipient_name,
    )
    return result


@router.post("/polish-ai")
async def polish_with_ai(
    body: PolishAIRequest,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Polish and rephrase draft subject and body to elevate tone and clarity."""
    result = _service.polish_email(
        subject=body.subject,
        body=body.body,
        tone=body.tone,
    )
    return result


@router.get("/{email_id}")
async def get_email(
    email_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve details for a single email or draft (strict tenant isolation)."""
    user_id = str(user.id)
    msg = await _repo.get_message(user_id, email_id)
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email with ID '{email_id}' not found.",
        )
    return {"email": msg}


@router.patch("/{email_id}")
async def update_email(
    email_id: str,
    body: UpdateEmailRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update a draft email with strict user ownership verification."""
    user_id = str(user.id)
    updated = await _repo.update_message(
        user_id=user_id,
        message_id=email_id,
        to=body.to.strip() if body.to is not None else None,
        subject=body.subject.strip() if body.subject is not None else None,
        body=body.body.strip() if body.body is not None else None,
        cc=body.cc,
        bcc=body.bcc,
        status=body.status,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email with ID '{email_id}' not found or unauthorized.",
        )
    return {"email": updated, "message": "Email updated successfully."}


@router.delete("/{email_id}")
async def delete_email(
    email_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete an email message or draft (strict tenant isolation)."""
    user_id = str(user.id)
    deleted = await _repo.delete_message(user_id, email_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Email with ID '{email_id}' not found or unauthorized.",
        )
    return {"success": True, "message": "Email deleted successfully."}


@router.post("/{email_id}/send")
async def send_draft_email(
    email_id: str,
    body: SendDraftRequest | None = None,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Dispatch a saved draft email message through the email delivery pipeline."""
    user_id = str(user.id)
    try:
        result = await _service.send_email_message(
            user_id=user_id,
            message_id=email_id,
            smtp_user=body.smtp_user if body else None,
            smtp_pass=body.smtp_pass if body else None,
            smtp_host=body.smtp_host if body else None,
            smtp_port=body.smtp_port if body else None,
            smtp_from=body.smtp_from if body else None,
        )
        return result
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
