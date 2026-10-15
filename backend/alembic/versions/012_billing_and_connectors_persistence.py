"""Phase 8 & 26: Billing Subsystem (Subscriptions, Payments, Events, Methods, Wallets) and Connectors Persistence Migration.

Provisions durable PostgreSQL tables for:
- `connector_instances`: External OAuth/API-key connector tokens (Gmail, GitHub, etc.)
- `subscriptions`: Multi-provider subscription plans (Stripe, Safepay) with USD & PKR pricing
- `payments`: Normalized transaction records for Stripe & Safepay
- `payment_events`: Webhook deduplication log for idempotent event processing
- `payment_methods`: Tokenized customer payment methods (Visa, Mastercard, PayPak)
- `credit_wallets`: User token credit wallets for pay-as-you-go / top-up credits
- `usage_logs`: LLM token and tool execution cost analytics

Supports both fresh database provisioning and idempotent upgrade of pre-existing schemas.

Revision ID: 012_billing_and_connectors_persistence
Revises: 011_trust_reliability_hardening
Create Date: 2026-10-15
"""

from collections.abc import Sequence
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "012_billing_and_connectors_persistence"
down_revision: str | None = "011_trust_reliability_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception:
        inspector = None
        existing_tables = set()

    # -------------------------------------------------------------------------
    # 1. connector_instances table (OAuth / API Token Persistence)
    # -------------------------------------------------------------------------
    if inspector is None or "connector_instances" not in existing_tables:
        op.create_table(
            "connector_instances",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("workspace_id", sa.String(36), nullable=True, index=True),
            sa.Column("connector_type", sa.String(32), nullable=False, index=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("auth_type", sa.String(32), nullable=False, server_default=sa.text("'api_key'")),
            sa.Column("config_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("encrypted_credentials_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'"), index=True),
            sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "idx_connector_user_type",
            "connector_instances",
            ["user_id", "connector_type"],
            unique=False,
        )
    else:
        # Table exists: verify columns
        existing_cols = {col["name"] for col in inspector.get_columns("connector_instances")}
        if "encrypted_credentials_json" not in existing_cols:
            op.add_column(
                "connector_instances",
                sa.Column("encrypted_credentials_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
            )

    # -------------------------------------------------------------------------
    # 2. subscriptions table (Multi-provider Subscription Plans)
    # -------------------------------------------------------------------------
    if inspector is None or "subscriptions" not in existing_tables:
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("provider", sa.String(32), nullable=False, server_default=sa.text("'stripe'")),
            sa.Column("plan", sa.String(32), nullable=False, server_default=sa.text("'free'")),
            sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
            sa.Column("stripe_customer_id", sa.String(128), nullable=True),
            sa.Column("stripe_subscription_id", sa.String(128), nullable=True),
            sa.Column("provider_customer_id", sa.String(128), nullable=True),
            sa.Column("provider_subscription_id", sa.String(128), nullable=True),
            sa.Column("amount_usd", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("amount_pkr", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    else:
        # Table exists: add missing columns safely
        existing_cols = {col["name"] for col in inspector.get_columns("subscriptions")}
        sub_cols_to_add = [
            ("provider", sa.String(32), False, sa.text("'stripe'")),
            ("plan", sa.String(32), False, sa.text("'free'")),
            ("status", sa.String(32), False, sa.text("'active'")),
            ("stripe_customer_id", sa.String(128), True, None),
            ("stripe_subscription_id", sa.String(128), True, None),
            ("provider_customer_id", sa.String(128), True, None),
            ("provider_subscription_id", sa.String(128), True, None),
            ("amount_usd", sa.Float(), False, sa.text("0.0")),
            ("amount_pkr", sa.Float(), False, sa.text("0.0")),
            ("cancel_at_period_end", sa.Boolean(), False, sa.text("false")),
            ("current_period_start", sa.DateTime(timezone=True), False, sa.func.now()),
            ("current_period_end", sa.DateTime(timezone=True), True, None),
        ]
        for col_name, col_type, nullable, default in sub_cols_to_add:
            if col_name not in existing_cols:
                op.add_column(
                    "subscriptions",
                    sa.Column(col_name, cast(Any, col_type), nullable=nullable, server_default=default),
                )

    # -------------------------------------------------------------------------
    # 3. payments table (Normalized Transactions)
    # -------------------------------------------------------------------------
    if inspector is None or "payments" not in existing_tables:
        op.create_table(
            "payments",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("provider_payment_id", sa.String(128), nullable=True, index=True),
            sa.Column("provider_customer_id", sa.String(128), nullable=True),
            sa.Column("provider_session_id", sa.String(128), nullable=True, index=True),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(8), nullable=False, server_default=sa.text("'USD'")),
            sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'pending'")),
            sa.Column("payment_type", sa.String(32), nullable=False, server_default=sa.text("'subscription'")),
            sa.Column("plan_id", sa.String(32), nullable=True),
            sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # -------------------------------------------------------------------------
    # 4. payment_events table (Idempotent Webhook Log)
    # -------------------------------------------------------------------------
    if inspector is None or "payment_events" not in existing_tables:
        op.create_table(
            "payment_events",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("provider", sa.String(32), nullable=False),
            sa.Column("provider_event_id", sa.String(128), nullable=False, index=True),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "idx_payment_event_provider_event",
            "payment_events",
            ["provider", "provider_event_id"],
            unique=True,
        )

    # -------------------------------------------------------------------------
    # 5. payment_methods table (Saved Payment Methods)
    # -------------------------------------------------------------------------
    if inspector is None or "payment_methods" not in existing_tables:
        op.create_table(
            "payment_methods",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("provider", sa.String(32), nullable=False, server_default=sa.text("'stripe'")),
            sa.Column("stripe_payment_method_id", sa.String(128), nullable=False, server_default=sa.text("''")),
            sa.Column("provider_payment_method_id", sa.String(128), nullable=True),
            sa.Column("brand", sa.String(32), nullable=False, server_default=sa.text("'visa'")),
            sa.Column("last4", sa.String(4), nullable=False),
            sa.Column("exp_month", sa.Integer(), nullable=False),
            sa.Column("exp_year", sa.Integer(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # -------------------------------------------------------------------------
    # 6. credit_wallets table (User Token Balance)
    # -------------------------------------------------------------------------
    if inspector is None or "credit_wallets" not in existing_tables:
        op.create_table(
            "credit_wallets",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, unique=True, index=True),
            sa.Column("remaining_credits", sa.Float(), nullable=False, server_default=sa.text("100.0")),
            sa.Column("used_this_month", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("estimated_cost_pkr", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # -------------------------------------------------------------------------
    # 7. usage_logs table (Token and Feature Consumption)
    # -------------------------------------------------------------------------
    if inspector is None or "usage_logs" not in existing_tables:
        op.create_table(
            "usage_logs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), nullable=False, index=True),
            sa.Column("feature", sa.String(64), nullable=False, server_default=sa.text("'chat'")),
            sa.Column("model", sa.String(64), nullable=False, server_default=sa.text("'gemini-3.8-flash'")),
            sa.Column("tokens_input", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("tokens_output", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("cost_usd", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("cost_pkr", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_usage_logs_user_timestamp",
            "usage_logs",
            ["user_id", "timestamp"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception:
        existing_tables = set()

    for table in [
        "usage_logs",
        "credit_wallets",
        "payment_methods",
        "payment_events",
        "payments",
        "subscriptions",
        "connector_instances",
    ]:
        if table in existing_tables:
            op.drop_table(table)
