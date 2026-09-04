"""Auth Pydantic v2 request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    """Public user representation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    created_at: datetime


class RequestLinkRequest(BaseModel):
    """Request a magic link for the given email."""

    email: EmailStr


class RequestLinkResponse(BaseModel):
    """Always 200 to avoid email-enumeration leakage."""

    ok: bool = True


class VerifyTokenRequest(BaseModel):
    """Exchange a magic-link token for a session JWT."""

    token: str = Field(min_length=8, max_length=128)


class SessionResponse(BaseModel):
    """Returned by /auth/verify on success."""

    user: UserResponse
    access_token: str
    token_type: str = "bearer"
    expires_in: int
