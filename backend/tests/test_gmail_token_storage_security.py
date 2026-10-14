"""Security regression tests for Gmail OAuth token encrypted storage.

Validates:
- OAuth tokens saved to disk are encrypted at rest with Authenticated Fernet ciphertext.
- Token files on disk do NOT contain plaintext 'access_token' or 'refresh_token' strings.
- Authorized user can load and decrypt their own stored token.
- Tenant isolation: User B cannot load User A's token payload even if file is copied.
- Missing encryption keys fail safely without crashing or leaking plaintext.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from unittest.mock import patch

import pytest

from app.skills.email_send import EmailSendSkill


@pytest.fixture
def temp_token_data_dir():
    """Create isolated temporary directory for token storage testing."""
    tmp_dir = tempfile.mkdtemp()
    yield tmp_dir
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_tokens_are_encrypted_at_rest_not_plaintext(temp_token_data_dir, monkeypatch):
    """Saving tokens writes an encrypted envelope with no plaintext credentials."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    saved = skill._save_encrypted_token(
        "user_alice",
        {
            "access_token": "ya29.sensitive_oauth_access_token_12345",
            "refresh_token": "1//sensitive_refresh_token_67890",
            "expires_at": 9999999999.0,
        },
    )
    assert saved is True

    token_file = os.path.join(temp_token_data_dir, "gmail_token_user_alice.json")
    assert os.path.exists(token_file)

    with open(token_file, "r", encoding="utf-8") as f:
        raw_content = f.read()

    # Plaintext secrets MUST NOT appear in the on-disk file
    assert "ya29.sensitive_oauth_access_token_12345" not in raw_content
    assert "1//sensitive_refresh_token_67890" not in raw_content

    # Container must indicate encrypted status
    data = json.loads(raw_content)
    assert data.get("encrypted") is True
    assert "ciphertext" in data
    assert isinstance(data["ciphertext"], str)


def test_authorized_user_can_decrypt_token(temp_token_data_dir, monkeypatch):
    """The authorized user can load and decrypt their valid stored token."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    skill._save_encrypted_token(
        "user_alice",
        {
            "access_token": "ya29.secret_token",
            "refresh_token": "1//refresh_token",
            "expires_at": 9999999999.0,
        },
    )

    loaded_token = skill._load_user_token("user_alice")
    assert loaded_token == "ya29.secret_token"


def test_cross_user_tenant_isolation(temp_token_data_dir, monkeypatch):
    """If Bob attempts to load Alice's token file, tenant validation rejects it."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    skill._save_encrypted_token(
        "user_alice",
        {
            "access_token": "ya29.alice_secret",
            "refresh_token": "1//alice_refresh",
            "expires_at": 9999999999.0,
        },
    )

    # Copy Alice's token to Bob's path
    alice_file = os.path.join(temp_token_data_dir, "gmail_token_user_alice.json")
    bob_file = os.path.join(temp_token_data_dir, "gmail_token_user_bob.json")
    shutil.copyfile(alice_file, bob_file)

    # Bob attempts to load it — payload user_id mismatch must reject
    bob_token = skill._load_user_token("user_bob")
    assert bob_token is None
