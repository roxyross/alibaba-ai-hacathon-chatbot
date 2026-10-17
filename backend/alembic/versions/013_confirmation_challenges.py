"""Phase Security Closure: Durable Confirmation Challenges Persistence.

Provisions durable PostgreSQL table `confirmation_challenges` supporting:
- Multi-worker atomic conditional updates and row-level locking (SELECT FOR UPDATE)
- Cryptographic challenge tokens and step-up 2FA state
- Parameter binding persistence
- Safe downgrade data preservation

Revision ID: 013_confirmation_challenges
Revises: 012_billing_connectors
Create Date: 2026-10-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013_confirmation_challenges"
down_revision: str | None = "012_billing_connectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception as exc:
        raise RuntimeError(f"Database schema inspection failed during migration 013 upgrade: {exc}") from exc

    created_tables: list[str] = []

    if "_alembic_013_created_tables" not in existing_tables:
        op.create_table(
            "_alembic_013_created_tables",
            sa.Column("table_name", sa.String(128), primary_key=True),
        )

    if "confirmation_challenges" not in existing_tables:
        op.create_table(
            "confirmation_challenges",
            sa.Column("challenge_id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("action_type", sa.String(64), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("details_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("risk_tier", sa.String(32), nullable=False, server_default=sa.text("'HIGH'")),
            sa.Column("risk_score", sa.Integer(), nullable=False, server_default=sa.text("75")),
            sa.Column("challenge_token", sa.String(128), nullable=False),
            sa.Column("step_up_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("step_up_code", sa.String(64), nullable=True),
            sa.Column("step_up_hint", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'pending'")),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("decision", sa.String(32), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_confirmation_challenges_user_id",
            "confirmation_challenges",
            ["user_id"],
            unique=False,
        )
        op.create_index(
            "ix_confirmation_challenges_action_type",
            "confirmation_challenges",
            ["action_type"],
            unique=False,
        )
        op.create_index(
            "ix_confirmation_challenges_challenge_token",
            "confirmation_challenges",
            ["challenge_token"],
            unique=False,
        )
        op.create_index(
            "ix_confirmation_challenges_status",
            "confirmation_challenges",
            ["status"],
            unique=False,
        )
        op.create_index(
            "ix_confirmation_challenges_created_at",
            "confirmation_challenges",
            ["created_at"],
            unique=False,
        )
        op.create_index(
            "ix_confirmation_challenges_expires_at",
            "confirmation_challenges",
            ["expires_at"],
            unique=False,
        )
        op.create_index(
            "ix_conf_challenges_user_status",
            "confirmation_challenges",
            ["user_id", "status"],
            unique=False,
        )
        created_tables.append("confirmation_challenges")

    if created_tables:
        insert_rows = ", ".join(f"('{tbl}')" for tbl in created_tables)
        op.execute(
            sa.text(
                f"INSERT INTO _alembic_013_created_tables (table_name) VALUES {insert_rows} "
                f"ON CONFLICT (table_name) DO NOTHING"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception as exc:
        raise RuntimeError(f"Database schema inspection failed during migration 013 downgrade: {exc}") from exc

    strictly_created_tables: set[str] = set()
    if "_alembic_013_created_tables" in existing_tables:
        res = bind.execute(sa.text("SELECT table_name FROM _alembic_013_created_tables"))
        strictly_created_tables = {row[0] for row in res.fetchall()}

    if "confirmation_challenges" in strictly_created_tables and "confirmation_challenges" in existing_tables:
        op.drop_table("confirmation_challenges")

    if "_alembic_013_created_tables" in existing_tables:
        op.drop_table("_alembic_013_created_tables")
