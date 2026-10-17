"""Permanent Real-PostgreSQL Integration Test Suite for Roxy-AI Gmail OAuth Token Persistence.

Guarantees:
- Real PostgreSQL connection and SQLAlchemy AsyncSession transactions (zero mocked DB functions).
- Positive Database Guard: Refuses execution unless positively connected to an isolated test database.
- Full Persistence Lifecycle: Save, commit, fresh-session retrieval, AES-Fernet decryption,
  upsert deduplication, refresh persistence, tenant isolation, and deletion.
- Scoped Cleanup: Modifies and deletes only synthetic test identities created during this run.
- Production Fail-Closed (SEC-06): Validates that DB errors or missing configuration in production
  fail closed and never fall back to local JSON disk files.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from typing import Any
from unittest import mock

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import (
    _session_factory,
    get_engine,
    normalize_database_url,
)
from app.models.connector import ConnectorInstance
from app.skills.email_send import EmailSendSkill

# Allowed test database identifiers
VALID_TEST_DB_NAMES = {"roxy_isolated_test_db", "roxy_test"}
PROD_DB_MARKERS = {"prod", "production", "neon.tech", "aws.neon", "cloudsql"}


def _resolve_test_database_url() -> str | None:
    """Resolve the test database URL from environment or known isolated test ports."""
    url = os.environ.get("ROXY_TEST_DATABASE_URL")
    if url:
        return url
    env_db = os.environ.get("DATABASE_URL", "").strip()
    if env_db and not any(marker in env_db.lower() for marker in PROD_DB_MARKERS):
        return env_db
    # Default to local dedicated isolated test container port 5433
    return "postgresql+asyncpg://roxy_test_usr:roxy_test_secure_pwd_123@127.0.0.1:5433/roxy_isolated_test_db"


TEST_DATABASE_URL = _resolve_test_database_url()


@pytest_asyncio.fixture(scope="function")
async def pg_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide verified AsyncEngine connected strictly to an isolated test database."""
    if not TEST_DATABASE_URL:
        pytest.skip("No test database URL configured. Skipping real PostgreSQL integration tests.")

    norm_url, connect_args = normalize_database_url(TEST_DATABASE_URL)
    engine = create_async_engine(norm_url, connect_args=connect_args, poolclass=NullPool)

    # Positive Safety Gate: Verify target database identity
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT current_database(), inet_server_port()"))
            row = res.first()
            if not row:
                pytest.skip("Could not query PostgreSQL test database identity.")
            db_name, port = row
            if db_name not in VALID_TEST_DB_NAMES and not (db_name.endswith("_test") or "test" in db_name):
                pytest.skip(
                    f"Refusing to execute on non-test database '{db_name}'. "
                    f"Must be an isolated test database (e.g., 'roxy_isolated_test_db' or 'roxy_test')."
                )
            if any(marker in str(db_name).lower() for marker in ("prod", "production")):
                pytest.fail(f"CRITICAL SAFETY ABORT: Database name '{db_name}' contains production marker!")
    except Exception as exc:
        pytest.skip(f"PostgreSQL test service is unreachable: {exc}")

    yield engine
    await engine.dispose()


@pytest.fixture(scope="function", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """Configure disposable test encryption key and test DB environment for each test."""
    prev_db = os.environ.get("DATABASE_URL")
    prev_key = os.environ.get("GMAIL_TOKEN_ENCRYPTION_KEY")

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL or ""
    os.environ["GMAIL_TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

    # Clear cached engine and session factory to bind to test environment
    get_engine.cache_clear()
    _session_factory.cache_clear()

    yield

    if prev_db is not None:
        os.environ["DATABASE_URL"] = prev_db
    else:
        os.environ.pop("DATABASE_URL", None)

    if prev_key is not None:
        os.environ["GMAIL_TOKEN_ENCRYPTION_KEY"] = prev_key
    else:
        os.environ.pop("GMAIL_TOKEN_ENCRYPTION_KEY", None)

    get_engine.cache_clear()
    _session_factory.cache_clear()


@pytest.fixture
def temp_token_dir() -> Generator[str, None, None]:
    """Isolated temporary directory for skill local token operations."""
    temp_dir = tempfile.mkdtemp(prefix="roxy_test_token_dir_")
    with mock.patch.object(EmailSendSkill, "_token_dir", return_value=temp_dir):
        yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_01_safety_gate_and_schema_verification(pg_engine: AsyncEngine) -> None:
    """Positively assert target database is an isolated test database with connector_instances table."""
    async with pg_engine.connect() as conn:
        db_res = await conn.execute(text("SELECT current_database()"))
        current_db = db_res.scalar()
        assert current_db in VALID_TEST_DB_NAMES or "test" in str(current_db)

        table_res = await conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'connector_instances')")
        )
        assert bool(table_res.scalar()) is True, "connector_instances table missing from test database!"


@pytest.mark.asyncio
async def test_02_real_database_write_commit_and_encryption(
    pg_engine: AsyncEngine, temp_token_dir: str
) -> None:
    """Verify that _save_encrypted_token writes, commits, and encrypts tokens in PostgreSQL."""
    skill = EmailSendSkill()
    user_id = f"test_user_synthetic_alpha_{uuid.uuid4().hex[:8]}"
    raw_access = "ya29.synthetic_alpha_access_token_abc123"
    raw_refresh = "1//synthetic_alpha_refresh_token_xyz789"
    payload = {
        "access_token": raw_access,
        "refresh_token": raw_refresh,
        "expires_at": time.time() + 3600,
    }

    try:
        saved = skill._save_encrypted_token(user_id, payload)
        assert saved is True, "_save_encrypted_token failed"

        # Verify physical row in PostgreSQL via separate connection
        async with AsyncSession(pg_engine) as session:
            stmt = select(ConnectorInstance).where(
                ConnectorInstance.user_id == user_id,
                ConnectorInstance.connector_type == "gmail",
            )
            res = await session.execute(stmt)
            row = res.scalars().first()
            assert row is not None, "Row was not committed to PostgreSQL"
            assert row.user_id == user_id
            assert row.connector_type == "gmail"
            assert row.status == "active"

            envelope = json.loads(row.encrypted_credentials_json)
            assert envelope.get("encrypted") is True
            assert envelope.get("user_id") == user_id
            assert "ciphertext" in envelope

            # Security: plaintext tokens must NEVER appear in raw row fields
            raw_text = f"{row.config_json} {row.encrypted_credentials_json} {row.name} {row.description}"
            assert raw_access not in raw_text, "SECURITY VIOLATION: Raw access token found in DB row"
            assert raw_refresh not in raw_text, "SECURITY VIOLATION: Raw refresh token found in DB row"
    finally:
        # Cleanup synthetic row
        async with pg_engine.begin() as conn:
            await conn.execute(text("DELETE FROM connector_instances WHERE user_id = :uid"), {"uid": user_id})


@pytest.mark.asyncio
async def test_03_fresh_session_retrieval_and_decryption(
    pg_engine: AsyncEngine, temp_token_dir: str
) -> None:
    """Verify fresh skill instance retrieves and decrypts token from PostgreSQL without disk file."""
    skill = EmailSendSkill()
    user_id = f"test_user_synthetic_read_{uuid.uuid4().hex[:8]}"
    synthetic_access = "ya29.synthetic_read_access_token_111"
    synthetic_refresh = "1//synthetic_read_refresh_token_222"
    payload = {
        "access_token": synthetic_access,
        "refresh_token": synthetic_refresh,
        "expires_at": time.time() + 3600,
    }

    try:
        assert skill._save_encrypted_token(user_id, payload) is True

        # Remove local disk file to force 100% database read
        local_file = os.path.join(temp_token_dir, f"gmail_token_{user_id}.json")
        if os.path.exists(local_file):
            os.remove(local_file)

        # Fresh instance
        fresh_skill = EmailSendSkill()
        loaded = fresh_skill._load_user_token_payload(user_id)
        assert loaded is not None, "Failed to load token from PostgreSQL"
        assert loaded["access_token"] == synthetic_access
        assert loaded["refresh_token"] == synthetic_refresh
        assert loaded["user_id"] == user_id

        # Also test _load_user_token
        token_str = fresh_skill._load_user_token(user_id)
        assert token_str == synthetic_access
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(text("DELETE FROM connector_instances WHERE user_id = :uid"), {"uid": user_id})


@pytest.mark.asyncio
async def test_04_strict_tenant_isolation_and_tampering_rejection(
    pg_engine: AsyncEngine, temp_token_dir: str
) -> None:
    """Verify Tenant A cannot read Tenant B's tokens and cross-tenant tampering is rejected."""
    skill = EmailSendSkill()
    user_a = f"test_user_synthetic_iso_a_{uuid.uuid4().hex[:8]}"
    user_b = f"test_user_synthetic_iso_b_{uuid.uuid4().hex[:8]}"
    user_gamma = f"test_user_synthetic_gamma_{uuid.uuid4().hex[:8]}"

    token_a = "ya29.synthetic_token_user_a"
    token_b = "ya29.synthetic_token_user_b"

    try:
        # User B reads before having a token -> must be None
        assert skill._load_user_token_payload(user_b) is None

        # Store tokens for User A and User B
        assert skill._save_encrypted_token(user_a, {"access_token": token_a, "expires_at": time.time() + 3600}) is True
        assert skill._save_encrypted_token(user_b, {"access_token": token_b, "expires_at": time.time() + 3600}) is True

        # Remove local files
        for u in (user_a, user_b):
            f = os.path.join(temp_token_dir, f"gmail_token_{u}.json")
            if os.path.exists(f):
                os.remove(f)

        fresh_skill = EmailSendSkill()
        loaded_a = fresh_skill._load_user_token_payload(user_a)
        loaded_b = fresh_skill._load_user_token_payload(user_b)

        assert loaded_a is not None and loaded_a["access_token"] == token_a
        assert loaded_b is not None and loaded_b["access_token"] == token_b
        assert loaded_a["access_token"] != loaded_b["access_token"]

        # Tampering Rejection: Insert row where DB user_id is gamma but payload belongs to User A
        async with AsyncSession(pg_engine) as session:
            stmt = select(ConnectorInstance).where(ConnectorInstance.user_id == user_a)
            res = await session.execute(stmt)
            row_a = res.scalars().first()
            assert row_a is not None
            envelope_a = json.loads(row_a.encrypted_credentials_json)

            # Insert poisoned row for user_gamma with user_a's ciphertext
            poisoned_envelope = {
                "encrypted": True,
                "user_id": user_gamma,
                "ciphertext": envelope_a["ciphertext"],
                "updated_at": datetime.now(UTC).isoformat(),
            }
            poisoned_row = ConnectorInstance(
                id=str(uuid.uuid4()),
                user_id=user_gamma,
                connector_type="gmail",
                name="Poisoned Connector",
                auth_type="oauth2",
                status="active",
                encrypted_credentials_json=json.dumps(poisoned_envelope),
            )
            session.add(poisoned_row)
            await session.commit()

        # Reading gamma must detect identity mismatch and return None
        gamma_loaded = fresh_skill._load_user_token_payload(user_gamma)
        assert gamma_loaded is None, "SECURITY FAILURE: Cross-tenant payload tampering was not rejected!"
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM connector_instances WHERE user_id IN (:a, :b, :g)"),
                {"a": user_a, "b": user_b, "g": user_gamma},
            )


@pytest.mark.asyncio
async def test_05_upsert_single_row_no_duplicates(
    pg_engine: AsyncEngine, temp_token_dir: str
) -> None:
    """Verify overwriting an existing user's token updates the single row without duplicates."""
    skill = EmailSendSkill()
    user_id = f"test_user_synthetic_upsert_{uuid.uuid4().hex[:8]}"

    try:
        assert skill._save_encrypted_token(user_id, {"access_token": "ya29.initial", "expires_at": time.time() + 3600}) is True
        assert skill._save_encrypted_token(user_id, {"access_token": "ya29.updated", "expires_at": time.time() + 7200}) is True

        async with AsyncSession(pg_engine) as session:
            stmt = select(ConnectorInstance).where(
                ConnectorInstance.user_id == user_id,
                ConnectorInstance.connector_type == "gmail",
            )
            res = await session.execute(stmt)
            rows = res.scalars().all()
            assert len(rows) == 1, f"Expected exactly 1 row after upsert, found {len(rows)}"

        # Remove local file to verify read from DB
        local_f = os.path.join(temp_token_dir, f"gmail_token_{user_id}.json")
        if os.path.exists(local_f):
            os.remove(local_f)

        fresh_skill = EmailSendSkill()
        loaded = fresh_skill._load_user_token_payload(user_id)
        assert loaded is not None and loaded["access_token"] == "ya29.updated"
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(text("DELETE FROM connector_instances WHERE user_id = :uid"), {"uid": user_id})


@pytest.mark.asyncio
async def test_06_refresh_flow_persists_to_real_postgres(
    pg_engine: AsyncEngine, temp_token_dir: str
) -> None:
    """Verify expired token refresh automatically commits the new token to PostgreSQL."""
    skill = EmailSendSkill()
    user_id = f"test_user_synthetic_refresh_{uuid.uuid4().hex[:8]}"
    refreshed_access = "ya29.synthetic_refreshed_access_NEW"

    try:
        # Save expired token
        expired_payload = {
            "access_token": "ya29.old_expired",
            "refresh_token": "1//synthetic_valid_refresh_token",
            "expires_at": time.time() - 100,  # Expired
        }
        assert skill._save_encrypted_token(user_id, expired_payload) is True

        # Remove local disk file
        local_f = os.path.join(temp_token_dir, f"gmail_token_{user_id}.json")
        if os.path.exists(local_f):
            os.remove(local_f)

        # Mock ONLY external HTTP call to Google token endpoint, NOT the database!
        class DummyResponse:
            status_code = 200

            def json(self) -> dict[str, Any]:
                return {
                    "access_token": refreshed_access,
                    "expires_in": 3600,
                    "token_type": "Bearer",
                }

        with mock.patch.dict(
            os.environ,
            {
                "GMAIL_CLIENT_ID": "synthetic_client_id",
                "GMAIL_CLIENT_SECRET": "synthetic_secret",
            },
        ):
            with mock.patch("httpx.post", return_value=DummyResponse()):
                token = skill._load_user_token(user_id)
                assert token == refreshed_access

        if os.path.exists(local_f):
            os.remove(local_f)

        # Verify the refreshed token was committed to PostgreSQL
        async with AsyncSession(pg_engine) as session:
            stmt = select(ConnectorInstance).where(
                ConnectorInstance.user_id == user_id,
                ConnectorInstance.connector_type == "gmail",
            )
            res = await session.execute(stmt)
            row = res.scalars().first()
            assert row is not None
            envelope = json.loads(row.encrypted_credentials_json)
            cipher = skill._get_cipher()
            assert cipher is not None
            decrypted = json.loads(cipher.decrypt(envelope["ciphertext"].encode()).decode())
            assert decrypted["access_token"] == refreshed_access
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(text("DELETE FROM connector_instances WHERE user_id = :uid"), {"uid": user_id})


@pytest.mark.asyncio
async def test_07_revocation_and_scoped_deletion(
    pg_engine: AsyncEngine, temp_token_dir: str
) -> None:
    """Verify _delete_user_token deletes the row from PostgreSQL."""
    skill = EmailSendSkill()
    user_id = f"test_user_synthetic_del_{uuid.uuid4().hex[:8]}"

    try:
        assert skill._save_encrypted_token(user_id, {"access_token": "ya29.to_delete"}) is True
        skill._delete_user_token(user_id)

        # Verify deletion in PostgreSQL
        async with AsyncSession(pg_engine) as session:
            stmt = select(ConnectorInstance).where(ConnectorInstance.user_id == user_id)
            res = await session.execute(stmt)
            assert res.scalars().first() is None, "ConnectorInstance row must be deleted from PostgreSQL"

        assert skill._load_user_token_payload(user_id) is None
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(text("DELETE FROM connector_instances WHERE user_id = :uid"), {"uid": user_id})


@pytest.mark.asyncio
async def test_08_production_fail_closed_missing_database_url(
    temp_token_dir: str
) -> None:
    """Verify missing DATABASE_URL in production fails closed without local disk write."""
    skill = EmailSendSkill()
    user_id = f"test_user_prod_nodb_{uuid.uuid4().hex[:8]}"

    with mock.patch.dict(os.environ, {"ENVIRONMENT": "production", "DATABASE_URL": ""}):
        result = skill._save_encrypted_token(user_id, {"access_token": "ya29.token"})
        assert result is False, "Production mode did not fail closed on missing DATABASE_URL"

        token_file = os.path.join(temp_token_dir, f"gmail_token_{user_id}.json")
        assert not os.path.exists(token_file), "SECURITY VIOLATION: Wrote token to local disk in production!"


@pytest.mark.asyncio
async def test_09_production_fail_closed_database_write_failure(
    temp_token_dir: str
) -> None:
    """Verify database write failure in production fails closed without local disk write."""
    skill = EmailSendSkill()
    user_id = f"test_user_prod_dbfail_{uuid.uuid4().hex[:8]}"

    def _failing_save(*args: Any, **kwargs: Any) -> bool:
        return False

    with mock.patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        with mock.patch.object(EmailSendSkill, "_save_token_to_db", side_effect=_failing_save):
            result = skill._save_encrypted_token(user_id, {"access_token": "ya29.token"})
            assert result is False, "Production mode did not fail closed on DB write failure"

            token_file = os.path.join(temp_token_dir, f"gmail_token_{user_id}.json")
            assert not os.path.exists(token_file), "SECURITY VIOLATION: Wrote token to local disk on DB write failure!"
