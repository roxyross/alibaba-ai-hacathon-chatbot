"""Standalone Roxy Device Agent enrollment, identity, and command queue migration.

Adds hardware_fingerprint, device_token_hash, daemon_version to devices table.
Creates device_enrollment_tokens and device_commands tables.

Revision ID: 008_device_agent_enrollment
Revises: 007_target_scoped_permissions
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_device_agent_enrollment"
down_revision: Union[str, None] = "007_target_scoped_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception:
        inspector = None
        existing_tables = set()

    # 1. Create or update devices table with enrollment & identity columns
    if "devices" not in existing_tables:
        op.create_table(
            "devices",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), index=True, nullable=False),
            sa.Column("workspace_id", sa.String(36), index=True, nullable=True),
            sa.Column("device_name", sa.String(128), nullable=False),
            sa.Column("device_type", sa.String(32), server_default="desktop", nullable=False),
            sa.Column("os_platform", sa.String(32), server_default="windows", nullable=False),
            sa.Column("os_version", sa.String(64), server_default="", nullable=False),
            sa.Column("architecture", sa.String(32), server_default="x86_64", nullable=False),
            sa.Column("hostname", sa.String(128), server_default="localhost", nullable=False),
            sa.Column("ip_address", sa.String(64), server_default="127.0.0.1", nullable=False),
            sa.Column("status", sa.String(32), server_default="online", index=True, nullable=False),
            sa.Column("is_current_host", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column("hardware_fingerprint", sa.String(128), index=True, nullable=True),
            sa.Column("device_token_hash", sa.String(64), index=True, nullable=True),
            sa.Column("daemon_version", sa.String(32), server_default="1.0.0", nullable=True),
            sa.Column("capabilities_json", sa.Text(), server_default="[]", nullable=False),
            sa.Column("telemetry_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_devices_user_status", "devices", ["user_id", "status"])
        op.create_index("idx_devices_hw_fingerprint", "devices", ["hardware_fingerprint"])
        op.create_index("idx_devices_token_hash", "devices", ["device_token_hash"])
    else:
        columns = {c["name"] for c in inspector.get_columns("devices")}
        indexes = {i["name"] for i in inspector.get_indexes("devices")}

        if "hardware_fingerprint" not in columns:
            op.add_column("devices", sa.Column("hardware_fingerprint", sa.String(128), nullable=True))
        if "device_token_hash" not in columns:
            op.add_column("devices", sa.Column("device_token_hash", sa.String(64), nullable=True))
        if "daemon_version" not in columns:
            op.add_column("devices", sa.Column("daemon_version", sa.String(32), server_default="1.0.0", nullable=True))

        if "idx_devices_hw_fingerprint" not in indexes:
            op.create_index("idx_devices_hw_fingerprint", "devices", ["hardware_fingerprint"])
        if "idx_devices_token_hash" not in indexes:
            op.create_index("idx_devices_token_hash", "devices", ["device_token_hash"])

    # 2. Create device_enrollment_tokens table
    if "device_enrollment_tokens" not in existing_tables:
        op.create_table(
            "device_enrollment_tokens",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), index=True, nullable=False),
            sa.Column("token", sa.String(64), unique=True, index=True, nullable=False),
            sa.Column("label", sa.String(128), server_default="Device Enrollment Token", nullable=False),
            sa.Column("is_claimed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("claimed_by_device_id", sa.String(36), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        )

    # 3. Create device_commands table
    if "device_commands" not in existing_tables:
        op.create_table(
            "device_commands",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False),
            sa.Column("user_id", sa.String(36), index=True, nullable=False),
            sa.Column("command_type", sa.String(64), index=True, nullable=False),
            sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("status", sa.String(32), server_default="pending", index=True, nullable=False),
            sa.Column("result_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_device_commands_dev_status", "device_commands", ["device_id", "status"])


def downgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception:
        inspector = None
        existing_tables = set()

    if inspector is None:
        op.drop_table("device_commands")
        op.drop_table("device_enrollment_tokens")
        op.drop_table("devices")
    else:
        if "device_commands" in existing_tables:
            op.drop_table("device_commands")

    if "device_enrollment_tokens" in existing_tables:
        op.drop_table("device_enrollment_tokens")

    if "devices" in existing_tables:
        columns = {c["name"] for c in inspector.get_columns("devices")}
        indexes = {i["name"] for i in inspector.get_indexes("devices")}

        if "device_name" in columns and len(columns) <= 20:
            op.drop_table("devices")
        else:
            if "idx_devices_token_hash" in indexes:
                op.drop_index("idx_devices_token_hash", table_name="devices")
            if "idx_devices_hw_fingerprint" in indexes:
                op.drop_index("idx_devices_hw_fingerprint", table_name="devices")

            for col in ["daemon_version", "device_token_hash", "hardware_fingerprint"]:
                if col in columns:
                    op.drop_column("devices", col)
