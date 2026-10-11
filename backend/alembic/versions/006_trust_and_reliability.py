"""Add trust events, recovery jobs, personalization, data exports and evaluation records.

Revision ID: 006_trust_and_reliability
Revises: 005_session_type
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_trust_and_reliability"
down_revision: Union[str, None] = "005_session_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. trust_events
    if "trust_events" not in existing_tables:
        op.create_table(
            "trust_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("workspace_id", sa.String(36), nullable=True),
            sa.Column("task_id", sa.String(36), nullable=True),
            sa.Column("action_id", sa.String(36), nullable=True),
            sa.Column("action_type", sa.String(64), nullable=False),
            sa.Column("action_name", sa.String(128), nullable=False),
            sa.Column("tool_id", sa.String(64), nullable=True),
            sa.Column("risk_level", sa.String(16), server_default="low", nullable=False),
            sa.Column("permission_policy", sa.String(32), server_default="allow_automatically", nullable=False),
            sa.Column("confirmation_id", sa.String(36), nullable=True),
            sa.Column("execution_status", sa.String(32), server_default="requested", nullable=False),
            sa.Column("verification_status", sa.String(32), server_default="unverified", nullable=False),
            sa.Column("success", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("failure_code", sa.String(64), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("rollback_supported", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("rollback_status", sa.String(32), server_default="none", nullable=False),
            sa.Column("rollback_strategy", sa.String(64), nullable=True),
            sa.Column("rollback_payload_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("data_accessed", sa.Text(), server_default="[]", nullable=False),
            sa.Column("external_service", sa.String(64), nullable=True),
            sa.Column("external_reference", sa.String(255), nullable=True),
            sa.Column("metadata_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_trust_events_user_id", "trust_events", ["user_id"])
        op.create_index("ix_trust_events_workspace_id", "trust_events", ["workspace_id"])
        op.create_index("ix_trust_events_task_id", "trust_events", ["task_id"])
        op.create_index("ix_trust_events_action_id", "trust_events", ["action_id"])
        op.create_index("ix_trust_events_action_type", "trust_events", ["action_type"])
        op.create_index("ix_trust_events_tool_id", "trust_events", ["tool_id"])
        op.create_index("ix_trust_events_execution_status", "trust_events", ["execution_status"])
        op.create_index("ix_trust_events_verification_status", "trust_events", ["verification_status"])
        op.create_index("ix_trust_events_created_at", "trust_events", ["created_at"])
        op.create_index("idx_trust_events_user_status", "trust_events", ["user_id", "execution_status"])
        op.create_index("idx_trust_events_user_verification", "trust_events", ["user_id", "verification_status"])

    # 2. recovery_jobs
    if "recovery_jobs" not in existing_tables:
        op.create_table(
            "recovery_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("trust_event_id", sa.String(36), nullable=True),
            sa.Column("action_type", sa.String(64), nullable=False),
            sa.Column("tool_id", sa.String(64), nullable=True),
            sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("failure_category", sa.String(64), nullable=False),
            sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("max_retries", sa.Integer(), server_default="3", nullable=False),
            sa.Column("idempotency_key", sa.String(128), unique=True, nullable=False),
            sa.Column("status", sa.String(32), server_default="queued", nullable=False),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_recovery_jobs_user_id", "recovery_jobs", ["user_id"])
        op.create_index("ix_recovery_jobs_trust_event_id", "recovery_jobs", ["trust_event_id"])
        op.create_index("ix_recovery_jobs_idempotency_key", "recovery_jobs", ["idempotency_key"])
        op.create_index("ix_recovery_jobs_status", "recovery_jobs", ["status"])

    # 3. personalization_proposals
    if "personalization_proposals" not in existing_tables:
        op.create_table(
            "personalization_proposals",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("category", sa.String(64), nullable=False),
            sa.Column("key", sa.String(128), nullable=False),
            sa.Column("proposed_value", sa.Text(), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=False),
            sa.Column("status", sa.String(32), server_default="pending", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_personalization_proposals_user_id", "personalization_proposals", ["user_id"])
        op.create_index("ix_personalization_proposals_status", "personalization_proposals", ["status"])
        op.create_index("idx_pers_user_status", "personalization_proposals", ["user_id", "status"])

    # 4. data_export_jobs
    if "data_export_jobs" not in existing_tables:
        op.create_table(
            "data_export_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("status", sa.String(32), server_default="requested", nullable=False),
            sa.Column("file_path", sa.String(255), nullable=True),
            sa.Column("export_payload_json", sa.Text(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_data_export_jobs_user_id", "data_export_jobs", ["user_id"])
        op.create_index("ix_data_export_jobs_status", "data_export_jobs", ["status"])

    # 5. evaluation_records
    if "evaluation_records" not in existing_tables:
        op.create_table(
            "evaluation_records",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("run_id", sa.String(36), nullable=False),
            sa.Column("test_case_id", sa.String(64), nullable=False),
            sa.Column("category", sa.String(64), nullable=False),
            sa.Column("passed", sa.Boolean(), nullable=False),
            sa.Column("score", sa.Integer(), server_default="100", nullable=False),
            sa.Column("details_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_evaluation_records_run_id", "evaluation_records", ["run_id"])
        op.create_index("ix_evaluation_records_test_case_id", "evaluation_records", ["test_case_id"])
        op.create_index("ix_evaluation_records_category", "evaluation_records", ["category"])


def downgrade() -> None:
    op.drop_table("evaluation_records")
    op.drop_table("data_export_jobs")
    op.drop_table("personalization_proposals")
    op.drop_table("recovery_jobs")
    op.drop_table("trust_events")
