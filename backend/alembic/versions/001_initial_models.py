"""Initial models — providers, models, token_usage_logs, user_preferences

Revision ID: 001_initial_models
Revises:
Create Date: 2026-09-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '001_initial_models'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # providers
    op.create_table(
        'providers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(50), unique=True, nullable=False),
        sa.Column('enabled', sa.Boolean, default=True),
        sa.Column('api_key_env_var', sa.String(100)),
        sa.Column('base_url', sa.String(255)),
        sa.Column('timeout_seconds', sa.Float, default=10.0),
        sa.Column('routing_priority', sa.Integer, unique=True),
        sa.Column('supports_streaming', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # models
    op.create_table(
        'models',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('provider_id', sa.String(36), sa.ForeignKey('providers.id', ondelete='CASCADE')),
        sa.Column('name', sa.String(100)),
        sa.Column('display_name', sa.String(100)),
        sa.Column('task_types', sa.ARRAY(sa.String), default=[]),
        sa.Column('cost_per_1k_input_tokens', sa.Float, default=0.0),
        sa.Column('cost_per_1k_output_tokens', sa.Float, default=0.0),
        sa.Column('max_tokens', sa.Integer, default=4096),
        sa.Column('enabled', sa.Boolean, default=True),
        sa.UniqueConstraint('provider_id', 'name', name='uq_model_provider_name'),
    )

    # token_usage_logs
    op.create_table(
        'token_usage_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('request_id', sa.String(36), index=True),
        sa.Column('provider_id', sa.String(36), sa.ForeignKey('providers.id', ondelete='CASCADE')),
        sa.Column('model_id', sa.String(36), sa.ForeignKey('models.id', ondelete='CASCADE')),
        sa.Column('input_tokens', sa.Integer, default=0),
        sa.Column('output_tokens', sa.Integer, default=0),
        sa.Column('cost_usd', sa.Float, default=0.0),
        sa.Column('latency_ms', sa.Integer, default=0),
        sa.Column('provider_response_ms', sa.Integer, nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index('ix_token_usage_logs_provider_id', 'provider_id'),
        sa.Index('ix_token_usage_logs_timestamp', 'timestamp'),
    )

    # user_preferences
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), unique=True),
        sa.Column('preferred_provider', sa.String(50), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('user_preferences')
    op.drop_table('token_usage_logs')
    op.drop_table('models')
    op.drop_table('providers')
