"""Session pinned/archived fields and user preferences schema enhancements.

Revision ID: 003_session_settings
Revises: 002_auth_sessions_messages
Create Date: 2026-09-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003_session_settings"
down_revision: Union[str, None] = "002_auth_sessions_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. chat_sessions enhancements
    op.add_column(
        "chat_sessions",
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "chat_sessions",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_chat_sessions_user_pinned",
        "chat_sessions",
        ["user_id", "pinned"],
    )

    # 2. user_preferences / settings enhancements
    op.add_column(
        "user_preferences",
        sa.Column("theme", sa.String(20), server_default="dark", nullable=False),
    )
    op.add_column(
        "user_preferences",
        sa.Column("custom_persona", sa.Text(), server_default="", nullable=True),
    )
    op.add_column(
        "user_preferences",
        sa.Column("stream_speed", sa.String(20), server_default="fast", nullable=False),
    )
    op.add_column(
        "user_preferences",
        sa.Column("sound_effects", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "user_preferences",
        sa.Column("auto_scroll", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "user_preferences",
        sa.Column("voice_id", sa.String(50), server_default="aura-asteria-en", nullable=True),
    )
    op.add_column(
        "user_preferences",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Ensure index exists on user_id
    try:
        op.create_index(
            "ix_user_preferences_user_id",
            "user_preferences",
            ["user_id"],
        )
    except Exception:
        pass


def downgrade() -> None:
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_column("user_preferences", "created_at")
    op.drop_column("user_preferences", "voice_id")
    op.drop_column("user_preferences", "auto_scroll")
    op.drop_column("user_preferences", "sound_effects")
    op.drop_column("user_preferences", "stream_speed")
    op.drop_column("user_preferences", "custom_persona")
    op.drop_column("user_preferences", "theme")

    op.drop_index("ix_chat_sessions_user_pinned", table_name="chat_sessions")
    op.drop_column("chat_sessions", "archived_at")
    op.drop_column("chat_sessions", "pinned")
