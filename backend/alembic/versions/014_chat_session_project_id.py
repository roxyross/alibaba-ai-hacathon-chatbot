"""Add project_id column to chat_sessions table.

Revision ID: 014_chat_session_project_id
Revises: 013_confirmation_challenges
Create Date: 2026-10-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014_chat_session_project_id"
down_revision: Union[str, None] = "013_confirmation_challenges"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        cols = {c["name"] for c in inspector.get_columns("chat_sessions")}
    except Exception:
        cols = set()

    if "project_id" not in cols:
        op.add_column(
            "chat_sessions",
            sa.Column("project_id", sa.String(36), nullable=True),
        )
        try:
            op.create_index(
                "ix_chat_sessions_project_id",
                "chat_sessions",
                ["project_id"],
                unique=False,
            )
        except Exception:
            pass


def downgrade() -> None:
    bind = op.get_bind()
    try:
        op.drop_index("ix_chat_sessions_project_id", table_name="chat_sessions")
    except Exception:
        pass
    try:
        op.drop_column("chat_sessions", "project_id")
    except Exception:
        pass
