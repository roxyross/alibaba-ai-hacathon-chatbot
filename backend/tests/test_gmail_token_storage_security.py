"""Security regression tests for Gmail OAuth token encrypted storage at rest.

Validates SEC-06:
- Tokens saved to disk are encrypted at rest using Fernet authenticated encryption.
- On-disk files never contain plaintext 'access_token' or 'refresh_token' credentials.
- Authorized user can load and decrypt their valid stored token using the correct key.
- Decryption with wrong key fails closed (returns None).
- Missing encryption key in production fails closed (returns None, no insecure fallback).
- Vercel deployment indicators trigger production strict path and fail closed if key is missing.
- Insecure development key rejected in production.
- Too-short key (< 32 chars) rejected in production.
- Tenant isolation: cross-user token access is strictly rejected.
- Ciphertext tampering / corruption is rejected (Fernet HMAC fails closed).
- Transparent key rotation via MultiFernet (fallback key decrypts and rotates to primary).
- Local non-production development mode allows fallback.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from app.skills.email_send import EmailSendSkill

TEST_PROD_ENCRYPTION_KEY = Fernet.generate_key().decode("utf-8")
TEST_ROTATION_FALLBACK_KEY = Fernet.generate_key().decode("utf-8")
TEST_DIFFERENT_KEY = Fernet.generate_key().decode("utf-8")


@pytest.fixture
def temp_token_data_dir() -> Generator[str, None, None]:
    """Create isolated temporary directory for token storage testing."""
    tmp_dir = tempfile.mkdtemp()
    yield tmp_dir
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_tokens_are_encrypted_at_rest_not_plaintext(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Saving tokens writes an authenticated Fernet envelope with no plaintext credentials."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    with patch.dict(os.environ, {"GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY, "APP_ENV": "production"}):
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

        with open(token_file, encoding="utf-8") as f:
            raw_content = f.read()

        # Plaintext secrets MUST NOT appear in the on-disk file
        assert "ya29.sensitive_oauth_access_token_12345" not in raw_content
        assert "1//sensitive_refresh_token_67890" not in raw_content

        # Container must indicate encrypted status
        data = json.loads(raw_content)
        assert data.get("encrypted") is True
        assert "ciphertext" in data
        assert isinstance(data["ciphertext"], str)


def test_authorized_user_can_decrypt_token(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The authorized user can load and decrypt their valid stored token using the correct key."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    with patch.dict(os.environ, {"GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY, "APP_ENV": "production"}):
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


def test_wrong_key_fails_closed(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Attempting to decrypt a token encrypted under a different key fails safely."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    # Save under Key A
    with patch.dict(os.environ, {"GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY, "APP_ENV": "production"}):
        skill._save_encrypted_token(
            "user_alice",
            {"access_token": "ya29.secret_key_a", "expires_at": 9999999999.0},
        )

    # Attempt to load under Key B
    with patch.dict(os.environ, {"GMAIL_TOKEN_ENCRYPTION_KEY": TEST_DIFFERENT_KEY, "APP_ENV": "production"}):
        loaded_token = skill._load_user_token("user_alice")
        assert loaded_token is None


def test_missing_production_key_fails_closed(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, missing GMAIL_TOKEN_ENCRYPTION_KEY fails closed with no insecure fallback."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
        os.environ.pop("GMAIL_TOKEN_ENCRYPTION_KEY", None)

        saved = skill._save_encrypted_token(
            "user_alice",
            {"access_token": "ya29.prod_token", "expires_at": 9999999999.0},
        )
        assert saved is False

        loaded = skill._load_user_token("user_alice")
        assert loaded is None


def test_vercel_environment_detection_fails_closed_when_key_missing(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vercel production indicators trigger strict production path and fail closed without key."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    # Vercel env indicators without encryption key
    with patch.dict(os.environ, {"VERCEL": "1", "VERCEL_ENV": "production"}, clear=False):
        os.environ.pop("GMAIL_TOKEN_ENCRYPTION_KEY", None)

        saved = skill._save_encrypted_token(
            "user_alice",
            {"access_token": "ya29.vercel_token", "expires_at": 9999999999.0},
        )
        assert saved is False
        assert skill._get_cipher() is None


def test_insecure_development_key_rejected_in_production(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Providing a known dev key in production is strictly rejected."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    with patch.dict(
        os.environ,
        {
            "APP_ENV": "production",
            "GMAIL_TOKEN_ENCRYPTION_KEY": "roxy-dev-secret-do-not-use-in-prod",
        },
    ):
        assert skill._get_cipher() is None
        assert skill._save_encrypted_token("user_alice", {"access_token": "ya29.token"}) is False


def test_short_encryption_key_rejected_in_production() -> None:
    """An encryption key shorter than 32 characters is rejected in production."""
    skill = EmailSendSkill()
    with patch.dict(os.environ, {"APP_ENV": "production", "GMAIL_TOKEN_ENCRYPTION_KEY": "too_short_key_12345"}):
        assert skill._get_cipher() is None


def test_cross_user_tenant_isolation(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """If Bob attempts to load Alice's token file, tenant validation rejects it."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    with patch.dict(os.environ, {"GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY, "APP_ENV": "production"}):
        skill._save_encrypted_token(
            "user_alice",
            {
                "access_token": "ya29.alice_secret",
                "refresh_token": "1//alice_refresh",
                "expires_at": 9999999999.0,
            },
        )

        # Copy Alice's token file to Bob's path
        alice_file = os.path.join(temp_token_data_dir, "gmail_token_user_alice.json")
        bob_file = os.path.join(temp_token_data_dir, "gmail_token_user_bob.json")
        shutil.copyfile(alice_file, bob_file)

        # Bob attempts to load it — payload user_id mismatch must reject
        bob_token = skill._load_user_token("user_bob")
        assert bob_token is None


def test_ciphertext_tampering_rejected(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Corrupted or tampered ciphertext fails authentication and returns None."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    with patch.dict(os.environ, {"GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY, "APP_ENV": "production"}):
        skill._save_encrypted_token(
            "user_alice",
            {"access_token": "ya29.alice_secret", "expires_at": 9999999999.0},
        )

        token_file = os.path.join(temp_token_data_dir, "gmail_token_user_alice.json")
        with open(token_file, encoding="utf-8") as f:
            data = json.load(f)

        # Tamper with the ciphertext
        tampered_bytes = bytearray(data["ciphertext"].encode("utf-8"))
        tampered_bytes[-5] = ord("X") if tampered_bytes[-5] != ord("X") else ord("Y")
        data["ciphertext"] = tampered_bytes.decode("utf-8")

        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        # Loading tampered token must fail closed
        assert skill._load_user_token("user_alice") is None


def test_key_rotation_via_multifernet(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tokens encrypted under a previous fallback key are decrypted and re-encrypted under primary key."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    # 1. Encrypt token under the fallback key originally
    with patch.dict(os.environ, {"GMAIL_TOKEN_ENCRYPTION_KEY": TEST_ROTATION_FALLBACK_KEY, "APP_ENV": "production"}):
        skill._save_encrypted_token(
            "user_alice",
            {"access_token": "ya29.rotate_me", "expires_at": 9999999999.0},
        )

    # 2. Configure new primary key and list old key as fallback
    with patch.dict(
        os.environ,
        {
            "GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY,
            "GMAIL_TOKEN_ENCRYPTION_KEY_FALLBACK": TEST_ROTATION_FALLBACK_KEY,
            "APP_ENV": "production",
        },
    ):
        loaded_token = skill._load_user_token("user_alice")
        assert loaded_token == "ya29.rotate_me"

    # 3. Verify the file is now decryptable using ONLY the new primary key (rotation completed)
    with patch.dict(os.environ, {"GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY, "APP_ENV": "production"}):
        os.environ.pop("GMAIL_TOKEN_ENCRYPTION_KEY_FALLBACK", None)
        assert skill._load_user_token("user_alice") == "ya29.rotate_me"


def test_development_mode_allows_local_fallback(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """In non-production, dev fallback key is allowed for offline test execution."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    with patch.dict(os.environ, {"APP_ENV": "development"}, clear=False):
        os.environ.pop("GMAIL_TOKEN_ENCRYPTION_KEY", None)

        saved = skill._save_encrypted_token(
            "user_dev",
            {"access_token": "ya29.dev_token", "expires_at": 9999999999.0},
        )
        assert saved is True
        assert skill._load_user_token("user_dev") == "ya29.dev_token"


def test_durable_multi_instance_token_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instance A saves an encrypted token into the durable store.
    Instance B (with an empty, independent local container filesystem) loads and decrypts it.
    """
    instance_a_dir = tempfile.mkdtemp()
    instance_b_dir = tempfile.mkdtemp()
    try:
        shared_db_store: dict[str, Any] = {}

        def _mock_save(user_id: str, container: dict[str, Any]) -> bool:
            shared_db_store[user_id] = container
            return True

        def _mock_load(user_id: str) -> dict[str, Any] | None:
            return shared_db_store.get(user_id)

        skill_a = EmailSendSkill()
        monkeypatch.setattr(skill_a, "_token_dir", lambda: instance_a_dir)
        monkeypatch.setattr(skill_a, "_save_token_to_db", _mock_save)
        monkeypatch.setattr(skill_a, "_load_token_from_db", _mock_load)

        skill_b = EmailSendSkill()
        monkeypatch.setattr(skill_b, "_token_dir", lambda: instance_b_dir)
        monkeypatch.setattr(skill_b, "_load_token_from_db", _mock_load)

        with patch.dict(
            os.environ,
            {
                "GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY,
                "APP_ENV": "production",
                "DATABASE_URL": "postgresql+asyncpg://postgres:pass@localhost:5432/roxy_test",
            },
        ):
            # Instance A writes token
            ok = skill_a._save_encrypted_token(
                "user_multi_inst",
                {"access_token": "ya29.multi_instance_token", "expires_at": 9999999999.0},
            )
            assert ok is True

            # Verify instance B has NO local file
            assert not os.path.exists(os.path.join(instance_b_dir, "gmail_token_user_multi_inst.json"))

            # Instance B loads token directly from shared durable persistence
            token = skill_b._load_user_token("user_multi_inst")
            assert token == "ya29.multi_instance_token"
    finally:
        shutil.rmtree(instance_a_dir, ignore_errors=True)
        shutil.rmtree(instance_b_dir, ignore_errors=True)


def test_database_write_failure_returns_false_and_does_not_claim_success(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """When DATABASE_URL is configured and durable database write fails, _save_encrypted_token MUST return False."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)
    # Simulate DB write failure
    monkeypatch.setattr(skill, "_save_token_to_db", lambda uid, container: False)

    with patch.dict(
        os.environ,
        {
            "GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY,
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+asyncpg://postgres:pass@localhost:5432/roxy_test",
        },
    ):
        saved = skill._save_encrypted_token(
            "user_alice",
            {"access_token": "ya29.token_db_fail", "expires_at": 9999999999.0},
        )
        assert saved is False, "Must NOT claim successful persistence when durable DB write failed"


def test_strict_durable_storage_fails_closed_without_database_url(temp_token_data_dir: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """When strict durable storage is enforced in production, missing DATABASE_URL fails closed."""
    skill = EmailSendSkill()
    monkeypatch.setattr(skill, "_token_dir", lambda: temp_token_data_dir)

    with patch.dict(
        os.environ,
        {
            "GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY,
            "APP_ENV": "production",
            "REQUIRE_DURABLE_TOKEN_STORE": "true",
        },
        clear=False,
    ):
        os.environ.pop("DATABASE_URL", None)
        saved = skill._save_encrypted_token(
            "user_alice",
            {"access_token": "ya29.strict_token", "expires_at": 9999999999.0},
        )
        assert saved is False, "Must fail closed when REQUIRE_DURABLE_TOKEN_STORE is true and DATABASE_URL is absent"


def test_container_restart_restores_token_from_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate container restart: local disk is wiped clean, but token is restored and decrypted from DB."""
    local_dir = tempfile.mkdtemp()
    try:
        db_storage: dict[str, Any] = {}

        def _mock_db_save(uid: str, container: dict[str, Any]) -> bool:
            db_storage[uid] = container
            return True

        def _mock_db_load(uid: str) -> dict[str, Any] | None:
            return db_storage.get(uid)

        skill = EmailSendSkill()
        monkeypatch.setattr(skill, "_token_dir", lambda: local_dir)
        monkeypatch.setattr(skill, "_save_token_to_db", _mock_db_save)
        monkeypatch.setattr(skill, "_load_token_from_db", _mock_db_load)

        with patch.dict(
            os.environ,
            {
                "GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY,
                "APP_ENV": "production",
                "DATABASE_URL": "postgresql+asyncpg://postgres:pass@localhost:5432/roxy_test",
            },
        ):
            ok = skill._save_encrypted_token(
                "user_restart",
                {"access_token": "ya29.survives_restart", "expires_at": 9999999999.0},
            )
            assert ok is True

            # Simulate container restart: wipe local directory completely
            shutil.rmtree(local_dir, ignore_errors=True)
            os.makedirs(local_dir, exist_ok=True)
            assert len(os.listdir(local_dir)) == 0

            # Reload token after restart
            token = skill._load_user_token("user_restart")
            assert token == "ya29.survives_restart"
    finally:
        shutil.rmtree(local_dir, ignore_errors=True)


def test_db_session_factory_unavailable_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """When DB session factory is unavailable, DB save returns False and persistence fails closed."""
    import app.db

    skill = EmailSendSkill()
    monkeypatch.setattr(app.db, "get_session_factory", lambda: None)

    with patch.dict(
        os.environ,
        {
            "GMAIL_TOKEN_ENCRYPTION_KEY": TEST_PROD_ENCRYPTION_KEY,
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+asyncpg://postgres:pass@localhost:5432/roxy_test",
        },
    ):
        db_ok = skill._save_token_to_db("user_nofactory", {"data": "test"})
        assert db_ok is False

        saved = skill._save_encrypted_token("user_nofactory", {"access_token": "ya29.test"})
        assert saved is False


