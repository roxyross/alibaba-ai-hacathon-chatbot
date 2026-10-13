"""Phase 4: Local Application Discovery Engine - Deep App Catalog migration.

Adds publisher, description, capabilities_json, supported_actions_json,
metadata_json, install_location, and is_system_app to discovered_apps table.

Revision ID: 009_deep_app_catalog
Revises: 008_device_agent_enrollment
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009_deep_app_catalog"
down_revision: Union[str, None] = "008_device_agent_enrollment"
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

    if "discovered_apps" not in existing_tables:
        op.create_table(
            "discovered_apps",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), index=True, nullable=False),
            sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False),
            sa.Column("app_name", sa.String(128), nullable=False),
            sa.Column("executable_path", sa.String(512), nullable=False),
            sa.Column("bundle_id", sa.String(128), nullable=True),
            sa.Column("category", sa.String(32), server_default="utilities", index=True, nullable=False),
            sa.Column("version", sa.String(64), nullable=True),
            sa.Column("publisher", sa.String(128), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("capabilities_json", sa.Text(), server_default="[]", nullable=False),
            sa.Column("supported_actions_json", sa.Text(), server_default="[]", nullable=False),
            sa.Column("metadata_json", sa.Text(), server_default="{}", nullable=False),
            sa.Column("install_location", sa.String(512), nullable=True),
            sa.Column("is_system_app", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column("icon_url", sa.String(255), nullable=True),
            sa.Column("is_running", sa.Boolean(), server_default=sa.text("false"), index=True, nullable=False),
            sa.Column("process_id", sa.Integer(), nullable=True),
            sa.Column("launch_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_launched_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_discovered_apps_device_name", "discovered_apps", ["device_id", "app_name"])
    else:
        columns = {c["name"] for c in inspector.get_columns("discovered_apps")}

        if "publisher" not in columns:
            op.add_column("discovered_apps", sa.Column("publisher", sa.String(128), nullable=True))
        if "description" not in columns:
            op.add_column("discovered_apps", sa.Column("description", sa.Text(), nullable=True))
        if "capabilities_json" not in columns:
            op.add_column("discovered_apps", sa.Column("capabilities_json", sa.Text(), server_default="[]", nullable=False))
        if "supported_actions_json" not in columns:
            op.add_column("discovered_apps", sa.Column("supported_actions_json", sa.Text(), server_default="[]", nullable=False))
        if "metadata_json" not in columns:
            op.add_column("discovered_apps", sa.Column("metadata_json", sa.Text(), server_default="{}", nullable=False))
        if "install_location" not in columns:
            op.add_column("discovered_apps", sa.Column("install_location", sa.String(512), nullable=True))
        if "is_system_app" not in columns:
            op.add_column("discovered_apps", sa.Column("is_system_app", sa.Boolean(), server_default=sa.text("false"), nullable=False))


def downgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception:
        inspector = None
        existing_tables = set()

    if inspector is None:
        op.drop_table("discovered_apps")
    elif "discovered_apps" in existing_tables:
        columns = {c["name"] for c in inspector.get_columns("discovered_apps")}
        if "app_name" in columns and len(columns) <= 22:
            op.drop_table("discovered_apps")
        else:
            for col in [
                "is_system_app",
                "install_location",
                "metadata_json",
                "supported_actions_json",
                "capabilities_json",
                "description",
                "publisher",
            ]:
                if col in columns:
                    op.drop_column("discovered_apps", col)
