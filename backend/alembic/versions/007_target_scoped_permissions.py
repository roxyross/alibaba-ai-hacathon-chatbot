"""Target-scoped permissions migration.

Adds device_id, target_app, capability, resource, parameter_constraints_json,
risk_level, grant_source, expires_at, and revoked_at to permission_grants.

Revision ID: 007_target_scoped_permissions
Revises: 006_trust_and_reliability
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_target_scoped_permissions"
down_revision: Union[str, None] = "006_trust_and_reliability"
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

    if inspector is None or "permission_grants" not in existing_tables:
        op.create_table(
            "permission_grants",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), index=True, nullable=False),
            sa.Column("tool_id", sa.String(64), index=True, nullable=True),
            sa.Column("permission", sa.String(128), index=True, nullable=False, server_default="execute"),
            sa.Column("policy", sa.String(32), nullable=False, server_default="always_ask"),
            sa.Column("scope", sa.String(64), nullable=False, server_default="global"),
            sa.Column("device_id", sa.String(64), index=True, nullable=True),
            sa.Column("target_app", sa.String(128), index=True, nullable=True),
            sa.Column("capability", sa.String(128), index=True, nullable=True),
            sa.Column("resource", sa.String(255), index=True, nullable=True),
            sa.Column("parameter_constraints_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("risk_level", sa.String(16), nullable=True),
            sa.Column("grant_source", sa.String(64), nullable=False, server_default="user_manual"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_perm_user_tool", "permission_grants", ["user_id", "tool_id"])
        op.create_index("idx_perm_user_app", "permission_grants", ["user_id", "target_app"])
        op.create_index("idx_perm_user_device", "permission_grants", ["user_id", "device_id"])
    else:
        columns = {c["name"] for c in inspector.get_columns("permission_grants")}
        if "device_id" not in columns:
            op.add_column("permission_grants", sa.Column("device_id", sa.String(64), nullable=True))
        if "target_app" not in columns:
            op.add_column("permission_grants", sa.Column("target_app", sa.String(128), nullable=True))
        if "capability" not in columns:
            op.add_column("permission_grants", sa.Column("capability", sa.String(128), nullable=True))
        if "resource" not in columns:
            op.add_column("permission_grants", sa.Column("resource", sa.String(255), nullable=True))
        if "parameter_constraints_json" not in columns:
            op.add_column(
                "permission_grants",
                sa.Column("parameter_constraints_json", sa.Text(), nullable=False, server_default="{}"),
            )
        if "risk_level" not in columns:
            op.add_column("permission_grants", sa.Column("risk_level", sa.String(16), nullable=True))
        if "grant_source" not in columns:
            op.add_column(
                "permission_grants",
                sa.Column("grant_source", sa.String(64), nullable=False, server_default="user_manual"),
            )
        if "expires_at" not in columns:
            op.add_column("permission_grants", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        if "revoked_at" not in columns:
            op.add_column("permission_grants", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))

        indexes = {i["name"] for i in inspector.get_indexes("permission_grants")}
        if "idx_perm_user_app" not in indexes:
            op.create_index("idx_perm_user_app", "permission_grants", ["user_id", "target_app"])
        if "idx_perm_user_device" not in indexes:
            op.create_index("idx_perm_user_device", "permission_grants", ["user_id", "device_id"])


def downgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception:
        inspector = None
        existing_tables = set()

    if inspector is None:
        op.drop_table("permission_grants")
    elif "permission_grants" in existing_tables:
        columns = {c["name"] for c in inspector.get_columns("permission_grants")}
        indexes = {i["name"] for i in inspector.get_indexes("permission_grants")}

        if "idx_perm_user_device" in indexes:
            op.drop_index("idx_perm_user_device", table_name="permission_grants")
        if "idx_perm_user_app" in indexes:
            op.drop_index("idx_perm_user_app", table_name="permission_grants")

        for col in [
            "revoked_at",
            "expires_at",
            "grant_source",
            "risk_level",
            "parameter_constraints_json",
            "resource",
            "capability",
            "target_app",
            "device_id",
        ]:
            if col in columns:
                op.drop_column("permission_grants", col)
