"""Phase 26: Trust, Control, Recovery & Reliability hardening migration.

Adds normalized TrustEvent columns (session_id, correlation_id, actor_type, actor_id,
skill_id, connector_id, plugin_id, device_id, target, permission_status, confirmation_status)
and creates rollback_actions table for reusable rollback abstractions.

Revision ID: 011_trust_reliability_hardening
Revises: 010_cowork_artifacts_and_open_work
Create Date: 2026-10-11
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "011_trust_reliability_hardening"
down_revision: str | None = "010_cowork_artifacts_and_open_work"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. Update trust_events table with normalized Phase A columns if missing
    if "trust_events" in existing_tables:
        existing_cols = {col["name"] for col in inspector.get_columns("trust_events")}

        cols_to_add = [
            ("session_id", sa.String(36), True, None),
            ("correlation_id", sa.String(64), True, None),
            ("actor_type", sa.String(32), False, "agent"),
            ("actor_id", sa.String(64), True, None),
            ("skill_id", sa.String(64), True, None),
            ("connector_id", sa.String(64), True, None),
            ("plugin_id", sa.String(64), True, None),
            ("device_id", sa.String(64), True, None),
            ("target", sa.String(255), True, None),
            ("permission_required", sa.Boolean(), False, sa.text("false")),
            ("permission_status", sa.String(32), False, "approved"),
            ("confirmation_required", sa.Boolean(), False, sa.text("false")),
            ("confirmation_status", sa.String(32), False, "none"),
        ]

        for col_name, col_type, nullable, default in cols_to_add:
            if col_name not in existing_cols:
                kw = {"nullable": nullable}
                if default is not None:
                    kw["server_default"] = default
                op.add_column("trust_events", sa.Column(col_name, col_type, **kw))

        # Add indexes if missing
        existing_indexes = {ix["name"] for ix in inspector.get_indexes("trust_events")}
        if "ix_trust_events_session_id" not in existing_indexes and "session_id" in existing_cols:
            op.create_index("ix_trust_events_session_id", "trust_events", ["session_id"])
        if "ix_trust_events_correlation_id" not in existing_indexes and "correlation_id" in existing_cols:
            op.create_index("ix_trust_events_correlation_id", "trust_events", ["correlation_id"])
        if "ix_trust_events_device_id" not in existing_indexes and "device_id" in existing_cols:
            op.create_index("ix_trust_events_device_id", "trust_events", ["device_id"])

    # 2. Create rollback_actions table
    if "rollback_actions" not in existing_tables:
        op.create_table(
            "rollback_actions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("action_id", sa.String(36), nullable=False),
            sa.Column("trust_event_id", sa.String(36), nullable=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("supported", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("strategy", sa.String(64), nullable=False),
            sa.Column("rollback_window_seconds", sa.Integer(), server_default="86400", nullable=False),
            sa.Column("requirements_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("status", sa.String(32), server_default="available", nullable=False),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_rollback_actions_action_id", "rollback_actions", ["action_id"])
        op.create_index("ix_rollback_actions_user_id", "rollback_actions", ["user_id"])
        op.create_index("ix_rollback_actions_status", "rollback_actions", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "rollback_actions" in existing_tables:
        op.drop_table("rollback_actions")
