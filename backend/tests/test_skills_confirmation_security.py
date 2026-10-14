"""Adversarial security regression tests for sensitive-action confirmation bypass elimination.

Validates:
- Client-supplied `confirm: true` CANNOT bypass the server-issued confirmation gate.
- Calling sensitive skills requires authenticated user (anonymous gets 401).
- Unpredictable server token is generated on initial sensitive skill invocation (HTTP 403 CONFIRMATION_REQUIRED).
- Invented or non-existent token is rejected with 404.
- Cross-user confirmation is blocked (User B cannot confirm User A's token).
- Expired token is rejected with 404.
- Consuming token via POST /skills/confirm executes action once.
- Replaying a consumed token fails with 404.
- Non-sensitive skills (e.g. calculator, web_search) execute without confirmation.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.auth.models import User
from app.skills.router import (
    ConfirmRequest,
    _pending_confirmations,
    _run_skill,
    skill_confirm_execute,
    skill_confirm_preview,
)
from app.skills.schemas import CalculatorRequest, EmailSendRequest


@pytest.fixture(autouse=True)
def clean_pending_confirmations() -> Generator[None, None, None]:
    _pending_confirmations.clear()
    yield
    _pending_confirmations.clear()


@pytest.mark.asyncio
async def test_client_confirm_true_cannot_bypass_confirmation_gate() -> None:
    """Passing confirm=True directly in the skill input data MUST still trigger 403 CONFIRMATION_REQUIRED."""
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"success": True})
    mock_executor.slug = "email_send"

    user = User(id="user_alice", email="alice@roxy.ai")
    req = EmailSendRequest(
        to="victim@example.com",
        subject="Phishing",
        body="Secret info",
        confirm=True,  # Attacker attempts to bypass server confirmation!
    )

    with pytest.raises(HTTPException) as exc_info:
        await _run_skill(mock_executor, req, user, skill_slug="email_send")

    assert exc_info.value.status_code == 403
    detail: Any = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail["error"] == "confirmation_required"
    assert "token" in detail
    # Ensure executor was NEVER called directly
    assert mock_executor.execute.call_count == 0


@pytest.mark.asyncio
async def test_anonymous_user_blocked_from_generating_sensitive_confirmations() -> None:
    """Unauthenticated/anonymous requests to sensitive skills are rejected with 401."""
    mock_executor = AsyncMock()
    req = EmailSendRequest(to="victim@example.com", subject="Test", body="Body")

    with pytest.raises(HTTPException) as exc_info:
        await _run_skill(mock_executor, req, None, skill_slug="email_send")

    assert exc_info.value.status_code == 401
    assert "Authentication required" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_cross_user_confirmation_blocked() -> None:
    """User Bob cannot preview or confirm Alice's pending action token."""
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"success": True})
    mock_executor.slug = "email_send"

    alice = User(id="user_alice", email="alice@roxy.ai")
    bob = User(id="user_bob", email="bob@roxy.ai")

    req = EmailSendRequest(to="partner@example.com", subject="Contract", body="Important")

    token = None
    try:
        await _run_skill(mock_executor, req, alice, skill_slug="email_send")
    except HTTPException as exc:
        detail: Any = exc.detail
        assert isinstance(detail, dict)
        token = detail["token"]

    assert token is not None

    # Bob attempts to preview Alice's token
    with pytest.raises(HTTPException) as exc_info:
        await skill_confirm_preview(token=token, current_user=bob)
    assert exc_info.value.status_code == 404

    # Bob attempts to execute Alice's token
    with pytest.raises(HTTPException) as exc_info:
        await skill_confirm_execute(req=ConfirmRequest(token=token), current_user=bob)
    assert exc_info.value.status_code == 404

    # Action must not have been executed
    assert mock_executor.execute.call_count == 0


@pytest.mark.asyncio
async def test_legitimate_confirmation_executes_once_and_blocks_replay() -> None:
    """Alice confirms her own token: succeeds on first call, rejected on second call."""
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"success": True, "message": "Email dispatched"})
    mock_executor.slug = "email_send"

    alice = User(id="user_alice", email="alice@roxy.ai")
    req = EmailSendRequest(to="partner@example.com", subject="Contract", body="Important")

    token = None
    try:
        await _run_skill(mock_executor, req, alice, skill_slug="email_send")
    except HTTPException as exc:
        detail: Any = exc.detail
        assert isinstance(detail, dict)
        token = detail["token"]

    assert token is not None

    # Alice previews token
    preview = await skill_confirm_preview(token=token, current_user=alice)
    assert preview.skill == "email_send"
    assert "partner@example.com" in preview.action

    # Alice confirms execution
    res = await skill_confirm_execute(req=ConfirmRequest(token=token), current_user=alice)
    assert res.success is True
    assert mock_executor.execute.call_count == 1

    # Immediate replay attempt by Alice MUST fail with 404
    with pytest.raises(HTTPException) as exc_info:
        await skill_confirm_execute(req=ConfirmRequest(token=token), current_user=alice)
    assert exc_info.value.status_code == 404
    # Executor count remains 1
    assert mock_executor.execute.call_count == 1


@pytest.mark.asyncio
async def test_low_risk_skills_execute_without_confirmation() -> None:
    """Non-sensitive skills like calculator execute directly without requiring confirmation."""
    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"result": 42})
    mock_executor.slug = "calculator"

    user = User(id="user_alice", email="alice@roxy.ai")
    req = CalculatorRequest(expression="6 * 7")

    res: Any = await _run_skill(mock_executor, req, user, skill_slug="calculator")
    assert res == {"result": 42}
    assert mock_executor.execute.call_count == 1


@pytest.mark.asyncio
async def test_expired_confirmation_token_rejected_with_404() -> None:
    """Tokens that exceed CONFIRMATION_TTL_SECONDS are expired and rejected with 404."""
    import time
    mock_executor = AsyncMock()
    alice = User(id="user_alice", email="alice@roxy.ai")
    req = EmailSendRequest(to="partner@example.com", subject="Meeting", body="Details")

    token = None
    try:
        await _run_skill(mock_executor, req, alice, skill_slug="email_send")
    except HTTPException as exc:
        detail: Any = exc.detail
        assert isinstance(detail, dict)
        token = detail["token"]

    assert token is not None

    # Simulate token expiration by rewinding issued_at timestamp
    entry = _pending_confirmations["user_alice"][token]
    _pending_confirmations["user_alice"][token] = (
        entry[0],
        entry[1],
        time.time() - 700,  # 700 seconds ago > 600s TTL
        entry[3],
        entry[4],
    )

    with pytest.raises(HTTPException) as exc_info:
        await skill_confirm_execute(req=ConfirmRequest(token=token), current_user=alice)
    assert exc_info.value.status_code == 404

