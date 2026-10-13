"""Phase 8: Cowork Artifacts and Open Work Tasks database persistence migration.

Creates cowork_artifacts and cowork_artifact_versions tables for PostgreSQL/Neon
multi-tenant durability across horizontal cloud workers.

Revision ID: 010_cowork_artifacts_open_work
Revises: 009_deep_app_catalog
Create Date: 2026-10-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "010_cowork_artifacts_open_work"
down_revision: str | None = "009_deep_app_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # Ensure alembic_version table can hold revisions up to 64 chars on PostgreSQL
    if bind.dialect.name == "postgresql":
        try:
            op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
        except Exception:
            pass

    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "cowork_artifacts" not in existing_tables:
        op.create_table(
            "cowork_artifacts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("task_id", sa.String(36), nullable=True, index=True),
            sa.Column("session_id", sa.String(36), nullable=True, index=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("artifact_type", sa.String(32), nullable=False, server_default="markdown"),
            sa.Column("language", sa.String(32), nullable=False, server_default="markdown"),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
            sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("idx_cowork_artifact_user_status", "cowork_artifacts", ["user_id", "status"])

    if "cowork_artifact_versions" not in existing_tables:
        op.create_table(
            "cowork_artifact_versions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("artifact_id", sa.String(36), sa.ForeignKey("cowork_artifacts.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("diff_from_previous", sa.Text(), nullable=True),
            sa.Column("change_summary", sa.String(255), nullable=False, server_default="Update"),
            sa.Column("created_by", sa.String(64), nullable=False, server_default="user"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "idx_cowork_version_artifact_num",
            "cowork_artifact_versions",
            ["artifact_id", "version_number"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "cowork_artifact_versions" in existing_tables:
        op.drop_table("cowork_artifact_versions")
    if "cowork_artifacts" in existing_tables:
        op.drop_table("cowork_artifacts")
