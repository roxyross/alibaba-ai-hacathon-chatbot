"""Add extra_settings JSON column to user_preferences table.

Revision ID: 004_extra_settings
Revises: 003_session_settings
Create Date: 2026-09-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004_extra_settings"
down_revision: Union[str, None] = "003_session_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("extra_settings", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "extra_settings")
