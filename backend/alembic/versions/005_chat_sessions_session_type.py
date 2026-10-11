"""Add session_type column to chat_sessions table.

Revision ID: 005_session_type
Revises: 004_extra_settings
Create Date: 2026-10-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_session_type"
down_revision: Union[str, None] = "004_extra_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("session_type", sa.String(20), server_default="chat", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "session_type")
