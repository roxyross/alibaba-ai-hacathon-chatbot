"""Adversarial security regression tests for JWT development-secret fallback elimination.

Validates:
- Legit token signed with configured secret is accepted.
- Forged token signed with known dev secret is rejected.
- Forged token signed with attacker secret is rejected.
- Tampered signature is rejected.
- Expired and missing-claim tokens are rejected.
- In production, missing or weak JWT_SECRET fails closed with RuntimeError.
- get_current_user rejects forged dev-secret tokens with HTTP 401.
"""

from __future__ import annotations

import os
import time
from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException

from app.auth.dependencies import get_current_user
from app.auth.jwt import (
    INSECURE_DEV_SECRET,
    create_session_token,
    decode_session_payload,
    decode_session_token,
)


TEST_PROD_SECRET = "super-secret-production-cryptographic-signing-key-32chars"
ATTACKER_SECRET = "attacker-controlled-secret-key-that-should-never-work"


def test_legitimate_token_accepted():
    """Legitimate token signed with configured secret must decode successfully."""
    with patch.dict(os.environ, {"JWT_SECRET": TEST_PROD_SECRET, "APP_ENV": "production"}):
        token, ttl = create_session_token("user_123", email="user@example.com")
        payload = decode_session_payload(token)
        assert payload is not None
        assert payload["sub"] == "user_123"
        assert payload["email"] == "user@example.com"
        assert decode_session_token(token) == "user_123"


def test_dev_secret_forged_token_rejected_when_prod_secret_configured():
    """A token forged using INSECURE_DEV_SECRET must be strictly rejected even if validly signed by it."""
    with patch.dict(os.environ, {"JWT_SECRET": TEST_PROD_SECRET, "APP_ENV": "production"}):
        # Attacker signs token using known static dev secret
        forged_payload = {
            "sub": "victim_admin",
            "email": "admin@roxy.ai",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }
        forged_token = jwt.encode(forged_payload, INSECURE_DEV_SECRET, algorithm="HS256")

        # Decoder must reject it with None (never fall back to dev secret)
        assert decode_session_payload(forged_token) is None
        assert decode_session_token(forged_token) is None


def test_unrelated_secret_rejected():
    """Token signed with arbitrary third-party secret must be rejected."""
    with patch.dict(os.environ, {"JWT_SECRET": TEST_PROD_SECRET, "APP_ENV": "production"}):
        forged_token = jwt.encode(
            {"sub": "attacker", "exp": int(time.time()) + 3600, "iat": int(time.time())},
            ATTACKER_SECRET,
            algorithm="HS256",
        )
        assert decode_session_payload(forged_token) is None


def test_tampered_signature_rejected():
    """Token with altered payload/signature must be rejected."""
    with patch.dict(os.environ, {"JWT_SECRET": TEST_PROD_SECRET, "APP_ENV": "production"}):
        token, _ = create_session_token("user_456")
        # Tamper last 5 characters of signature
        tampered = token[:-5] + "AAAAA"
        assert decode_session_payload(tampered) is None


def test_expired_token_rejected():
    """Expired token must be rejected."""
    with patch.dict(os.environ, {"JWT_SECRET": TEST_PROD_SECRET, "APP_ENV": "production"}):
        expired_token = jwt.encode(
            {"sub": "user_expired", "exp": int(time.time()) - 10, "iat": int(time.time()) - 100},
            TEST_PROD_SECRET,
            algorithm="HS256",
        )
        assert decode_session_payload(expired_token) is None


def test_missing_claims_rejected():
    """Tokens missing required claims (sub, exp, iat) must be rejected."""
    with patch.dict(os.environ, {"JWT_SECRET": TEST_PROD_SECRET, "APP_ENV": "production"}):
        # Missing exp
        t1 = jwt.encode({"sub": "u1", "iat": int(time.time())}, TEST_PROD_SECRET, algorithm="HS256")
        assert decode_session_payload(t1) is None

        # Missing sub
        t2 = jwt.encode({"exp": int(time.time()) + 100, "iat": int(time.time())}, TEST_PROD_SECRET, algorithm="HS256")
        assert decode_session_payload(t2) is None


def test_production_fails_closed_on_missing_or_weak_secret():
    """In production, empty or weak secret (< 32 chars) must raise RuntimeError."""
    # Missing secret in production
    with patch.dict(os.environ, {"JWT_SECRET": "", "APP_ENV": "production"}, clear=True):
        with pytest.raises(RuntimeError, match="CRITICAL SECURITY CONFIGURATION ERROR"):
            create_session_token("user_test")

    # Insecure dev secret in production
    with patch.dict(os.environ, {"JWT_SECRET": INSECURE_DEV_SECRET, "APP_ENV": "production"}):
        with pytest.raises(RuntimeError, match="CRITICAL SECURITY CONFIGURATION ERROR"):
            create_session_token("user_test")

    # Too short secret (< 32 chars) in production
    with patch.dict(os.environ, {"JWT_SECRET": "too-short-secret", "APP_ENV": "production"}):
        with pytest.raises(RuntimeError, match="CRITICAL SECURITY CONFIGURATION ERROR"):
            create_session_token("user_test")


@pytest.mark.asyncio
async def test_get_current_user_rejects_forged_dev_secret():
    """FastAPI get_current_user dependency must raise 401 when presented with a dev-secret forged token."""
    with patch.dict(os.environ, {"JWT_SECRET": TEST_PROD_SECRET, "APP_ENV": "production"}):
        forged_payload = {
            "sub": "victim_admin",
            "email": "admin@roxy.ai",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }
        forged_token = jwt.encode(forged_payload, INSECURE_DEV_SECRET, algorithm="HS256")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=f"Bearer {forged_token}")

        assert exc_info.value.status_code == 401
        assert "Invalid or expired session" in exc_info.value.detail
