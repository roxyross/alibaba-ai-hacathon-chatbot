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
    from app.skills.router import (
        _CONFIRMATION_LOCK,
        InMemoryConfirmationStore,
        set_confirmation_store,
    )

    in_mem = InMemoryConfirmationStore()
    set_confirmation_store(in_mem)
    with _CONFIRMATION_LOCK:
        _pending_confirmations.clear()
    yield
    set_confirmation_store(None)
    with _CONFIRMATION_LOCK:
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


@pytest.mark.asyncio
async def test_concurrent_confirmation_consumption_strictly_executes_once() -> None:
    """When two concurrent requests attempt to consume the same token simultaneously,
    exactly one succeeds, and the other is rejected with 404.
    """
    import asyncio

    mock_executor = AsyncMock()
    mock_executor.execute = AsyncMock(return_value={"success": True})
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

    async def _try_confirm() -> int:
        try:
            res = await skill_confirm_execute(req=ConfirmRequest(token=token), current_user=alice)
            return 200 if res.success else 500
        except HTTPException as e:
            return e.status_code

    results = await asyncio.gather(_try_confirm(), _try_confirm())
    assert sorted(results) == [200, 404]
    assert mock_executor.execute.call_count == 1


@pytest.mark.asyncio
async def test_production_without_distributed_store_fails_closed() -> None:
    """In production mode with no REDIS_URL configured, confirmation generation fails closed with 503."""
    import os
    from unittest.mock import patch

    mock_executor = AsyncMock()
    alice = User(id="user_alice", email="alice@roxy.ai")
    req = EmailSendRequest(to="partner@example.com", subject="Meeting", body="Details")

    from app.skills.router import set_confirmation_store

    set_confirmation_store(None)
    with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
        os.environ.pop("REDIS_URL", None)
        with pytest.raises(HTTPException) as exc_info:
            await _run_skill(mock_executor, req, alice, skill_slug="email_send")
        assert exc_info.value.status_code == 503
        assert "Confirmation service unavailable in production mode" in str(exc_info.value.detail)


def test_multi_instance_redis_confirmation_store() -> None:
    """Simulates multi-instance deployment with mock redis:
    Instance A saves a confirmation record.
    Instance B consumes it atomically.
    Instance C attempts to replay it and gets None (rejected).
    """
    import time
    from unittest.mock import MagicMock

    from app.skills.router import ConfirmationRecord, RedisConfirmationStore

    mock_redis = MagicMock()
    stored_data: dict[str, str] = {}

    def _mock_set(key: str, val: str, **kwargs: Any) -> bool:
        stored_data[key] = val
        return True

    def _mock_getdel(key: str) -> str | None:
        return stored_data.pop(key, None)

    def _mock_get(key: str) -> str | None:
        return stored_data.get(key)

    def _mock_eval(script: str, numkeys: int, key: str, *args: Any) -> str | None:
        return stored_data.pop(key, None)

    mock_redis.set.side_effect = _mock_set
    mock_redis.getdel.side_effect = _mock_getdel
    mock_redis.get.side_effect = _mock_get
    mock_redis.eval.side_effect = _mock_eval

    store = RedisConfirmationStore.__new__(RedisConfirmationStore)
    store._client = mock_redis

    record = ConfirmationRecord(
        token="tok_12345",
        user_id="user_alice",
        skill_slug="email_send",
        input_data={"to": "ceo@example.com"},
        params_digest="abc1234",
        issued_at=time.time(),
    )

    # Instance A saves
    assert store.save(record) is True
    # Instance B previews
    preview_rec = store.get("tok_12345", "user_alice")
    assert preview_rec is not None
    assert preview_rec.skill_slug == "email_send"
    # Instance B consumes
    consumed = store.consume("tok_12345", "user_alice")
    assert consumed is not None
    assert consumed.skill_slug == "email_send"
    # Instance C replay attempt MUST return None
    replay = store.consume("tok_12345", "user_alice")
    assert replay is None


def test_wrong_user_cannot_invalidate_valid_token_in_redis_or_memory() -> None:
    """An unauthorized user (Bob) attempting to consume Alice's token MUST NOT invalidate it.
    Alice must still be able to consume her token afterwards.
    """
    import json
    import time
    from unittest.mock import MagicMock
    from app.skills.router import ConfirmationRecord, RedisConfirmationStore, InMemoryConfirmationStore

    # 1. Test InMemory store
    mem_store = InMemoryConfirmationStore()
    record = ConfirmationRecord(
        token="tok_alice_1",
        user_id="user_alice",
        skill_slug="email_send",
        input_data={"to": "recipient@example.com"},
        params_digest="digest123",
        issued_at=time.time(),
    )
    assert mem_store.save(record) is True

    # Bob attempts to consume Alice's token
    bob_consumed = mem_store.consume("tok_alice_1", "user_bob")
    assert bob_consumed is None, "Bob must not be able to consume Alice's token"

    # Alice's token must STILL be valid and consumable by Alice
    alice_consumed = mem_store.consume("tok_alice_1", "user_alice")
    assert alice_consumed is not None, "Alice's token must not be invalidated by Bob's attempt"
    assert alice_consumed.user_id == "user_alice"

    # 2. Test Redis store with atomic Lua script logic
    redis_store_data: dict[str, str] = {}
    mock_redis = MagicMock()

    def _atomic_lua_mock(script: str, numkeys: int, key: str, *args: Any) -> str | None:
        val = redis_store_data.get(key)
        if not val:
            return None
        expected_user = args[0] if args else ""
        data = json.loads(val)
        if data.get("user_id") == expected_user:
            return redis_store_data.pop(key)
        return None  # Key is NOT deleted when user_id does not match!

    mock_redis.set.side_effect = lambda k, v, **kw: redis_store_data.update({k: v}) or True
    mock_redis.get.side_effect = lambda k: redis_store_data.get(k)
    mock_redis.eval.side_effect = _atomic_lua_mock

    redis_store = RedisConfirmationStore.__new__(RedisConfirmationStore)
    redis_store._client = mock_redis

    record2 = ConfirmationRecord(
        token="tok_alice_redis",
        user_id="user_alice",
        skill_slug="email_send",
        input_data={"to": "client@example.com"},
        params_digest="digest456",
        issued_at=time.time(),
    )
    assert redis_store.save(record2) is True
    assert "roxy:confirm:tok_alice_redis" in redis_store_data

    # Bob attempts to consume Alice's token
    bob_res = redis_store.consume("tok_alice_redis", "user_bob")
    assert bob_res is None, "Bob must not be able to consume Alice's token"

    # Token must STILL be present in Redis
    assert "roxy:confirm:tok_alice_redis" in redis_store_data, "Token must not be deleted from Redis by wrong user"

    # Alice consumes her token
    alice_res = redis_store.consume("tok_alice_redis", "user_alice")
    assert alice_res is not None, "Alice must be able to consume her token"
    assert alice_res.user_id == "user_alice"

    # Key must now be deleted
    assert "roxy:confirm:tok_alice_redis" not in redis_store_data

    # Replay returns None
    assert redis_store.consume("tok_alice_redis", "user_alice") is None


def test_redis_unavailability_handled_safely() -> None:
    """When Redis client raises connection or command errors, RedisConfirmationStore fails safely."""
    from unittest.mock import MagicMock
    from app.skills.router import ConfirmationRecord, RedisConfirmationStore

    mock_redis = MagicMock()
    mock_redis.set.side_effect = ConnectionError("Redis connection refused")
    mock_redis.get.side_effect = TimeoutError("Redis timed out")
    mock_redis.eval.side_effect = ConnectionError("Redis connection dropped")

    store = RedisConfirmationStore.__new__(RedisConfirmationStore)
    store._client = mock_redis

    record = ConfirmationRecord(
        token="tok_err",
        user_id="user_alice",
        skill_slug="email_send",
        input_data={},
        params_digest="digest",
        issued_at=1000.0,
    )

    # Save, get, consume must all return False/None without crashing
    assert store.save(record) is False
    assert store.get("tok_err", "user_alice") is None
    assert store.consume("tok_err", "user_alice") is None


def test_concurrent_consume_only_one_consumer_succeeds() -> None:
    """Simulate two concurrent workers attempting to consume the exact same token simultaneously."""
    import concurrent.futures
    import json
    import time
    from unittest.mock import MagicMock
    from app.skills.router import ConfirmationRecord, RedisConfirmationStore

    stored: dict[str, str] = {}
    mock_redis = MagicMock()

    def _eval(script: str, numkeys: int, key: str, *args: Any) -> str | None:
        val = stored.get(key)
        if val is None:
            return None
        data = json.loads(val)
        if data.get("user_id") == args[0]:
            return stored.pop(key, None)
        return None

    mock_redis.set.side_effect = lambda k, v, **kw: stored.update({k: v}) or True
    mock_redis.eval.side_effect = _eval

    store = RedisConfirmationStore.__new__(RedisConfirmationStore)
    store._client = mock_redis

    record = ConfirmationRecord(
        token="tok_concurrent",
        user_id="user_alice",
        skill_slug="email_send",
        input_data={"amount": 1000},
        params_digest="dig",
        issued_at=time.time(),
    )
    store.save(record)

    results: list[ConfirmationRecord | None] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(store.consume, "tok_concurrent", "user_alice") for _ in range(5)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Exactly one consumer must have received the record, and the other 4 must have received None
    successes = [r for r in results if r is not None]
    failures = [r for r in results if r is None]
    assert len(successes) == 1
    assert len(failures) == 4
    assert successes[0].token == "tok_concurrent"


