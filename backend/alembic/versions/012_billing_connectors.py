"""Phase 8 & 26: Billing Subsystem and Connectors Persistence Migration.

Provisions durable PostgreSQL tables for:
- `connector_instances`: External OAuth/API-key connector tokens (Gmail, GitHub, etc.)
- `subscriptions`: Multi-provider subscription plans (Stripe, Safepay) with USD & PKR pricing
- `payments`: Normalized transaction records for Stripe & Safepay
- `payment_events`: Webhook deduplication log for idempotent event processing
- `payment_methods`: Tokenized customer payment methods (Visa, Mastercard, PayPak)
- `credit_wallets`: User token credit wallets for pay-as-you-go / top-up credits
- `usage_logs`: LLM token and tool execution cost analytics

Supports both fresh database provisioning and safe idempotent upgrade of pre-existing schemas.
Implements safe data preservation on downgrade to never drop pre-existing tables.

Revision ID: 012_billing_connectors
Revises: 011_trust_reliability_hardening
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012_billing_connectors"
down_revision: str | None = "011_trust_reliability_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception as exc:
        raise RuntimeError(f"Database schema inspection failed during migration 012 upgrade: {exc}") from exc

    # Track newly created tables in a dedicated metadata table so downgrade
    # only drops tables created during this migration, and NEVER drops pre-existing tables.
    if "_alembic_012_created_tables" not in existing_tables:
        op.create_table(
            "_alembic_012_created_tables",
            sa.Column("table_name", sa.String(64), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    created_tables: list[str] = []

    # -------------------------------------------------------------------------
    # 1. connector_instances table (OAuth / API Token Persistence)
    # -------------------------------------------------------------------------
    if "connector_instances" not in existing_tables:
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
        op.create_unique_constraint(
            "uq_connector_instances_user_type",
            "connector_instances",
            ["user_id", "connector_type"],
        )
        created_tables.append("connector_instances")
    else:
        # Check for missing unique constraint
        try:
            constraints = {c["name"] for c in inspector.get_unique_constraints("connector_instances")}
            if "uq_connector_instances_user_type" not in constraints:
                op.create_unique_constraint(
                    "uq_connector_instances_user_type",
                    "connector_instances",
                    ["user_id", "connector_type"],
                )
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # 2. subscriptions table (Multi-provider Subscription Persistence)
    # -------------------------------------------------------------------------
    if "subscriptions" not in existing_tables:
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(64), nullable=False, index=True),
            sa.Column("plan", sa.String(32), nullable=False, server_default=sa.text("'free'")),
            sa.Column("provider", sa.String(32), nullable=False, server_default=sa.text("'stripe'"), index=True),
            sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'"), index=True),
            sa.Column("amount_usd", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("amount_pkr", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("stripe_customer_id", sa.String(128), nullable=True),
            sa.Column("stripe_subscription_id", sa.String(128), nullable=True),
            sa.Column("provider_customer_id", sa.String(128), nullable=True),
            sa.Column("provider_subscription_id", sa.String(128), nullable=True),
            sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
            sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        created_tables.append("subscriptions")
    else:
        sub_cols = {c["name"] for c in inspector.get_columns("subscriptions")}
        if "provider" not in sub_cols:
            op.add_column(
                "subscriptions",
                sa.Column("provider", sa.String(32), nullable=True),
            )
            # Safe backfill for historical rows without overwriting non-null provider values
            op.execute("UPDATE subscriptions SET provider = 'stripe' WHERE provider IS NULL")
            op.alter_column(
                "subscriptions",
                "provider",
                nullable=False,
                server_default=sa.text("'stripe'"),
            )
            op.create_index(
                "ix_subscriptions_provider",
                "subscriptions",
                ["provider"],
                unique=False,
            )
        if "amount_pkr" not in sub_cols:
            op.add_column(
                "subscriptions",
                sa.Column("amount_pkr", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            )
        if "amount_usd" not in sub_cols:
            op.add_column(
                "subscriptions",
                sa.Column("amount_usd", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            )
        if "stripe_customer_id" not in sub_cols:
            op.add_column(
                "subscriptions",
                sa.Column("stripe_customer_id", sa.String(128), nullable=True),
            )
        if "stripe_subscription_id" not in sub_cols:
            op.add_column(
                "subscriptions",
                sa.Column("stripe_subscription_id", sa.String(128), nullable=True),
            )
        if "provider_customer_id" not in sub_cols:
            op.add_column(
                "subscriptions",
                sa.Column("provider_customer_id", sa.String(128), nullable=True),
            )
        if "provider_subscription_id" not in sub_cols:
            op.add_column(
                "subscriptions",
                sa.Column("provider_subscription_id", sa.String(128), nullable=True),
            )
        if "current_period_start" not in sub_cols:
            op.add_column(
                "subscriptions",
                sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
            )

    # -------------------------------------------------------------------------
    # 3. payments table (Transaction Records)
    # -------------------------------------------------------------------------
    if "payments" not in existing_tables:
        op.create_table(
            "payments",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(64), nullable=False, index=True),
            sa.Column("provider", sa.String(32), nullable=False, index=True),
            sa.Column("provider_payment_id", sa.String(128), nullable=True, index=True),
            sa.Column("provider_customer_id", sa.String(128), nullable=True),
            sa.Column("provider_session_id", sa.String(128), nullable=True, index=True),
            sa.Column("amount", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(8), nullable=False, server_default=sa.text("'USD'")),
            sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'paid'")),
            sa.Column("payment_type", sa.String(32), nullable=False, server_default=sa.text("'subscription'")),
            sa.Column("plan_id", sa.String(64), nullable=True),
            sa.Column("metadata_json", sa.dialects.postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        created_tables.append("payments")
    else:
        pay_cols = {c["name"] for c in inspector.get_columns("payments")}
        if "provider_session_id" not in pay_cols:
            op.add_column(
                "payments",
                sa.Column("provider_session_id", sa.String(128), nullable=True),
            )
            op.create_index("ix_payments_provider_session_id", "payments", ["provider_session_id"], unique=False)
        if "metadata_json" not in pay_cols:
            op.add_column(
                "payments",
                sa.Column("metadata_json", sa.dialects.postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False, server_default=sa.text("'{}'")),
            )
        if "updated_at" not in pay_cols:
            op.add_column(
                "payments",
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            )

    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # 4. payment_events table (Webhook Deduplication)
    # -------------------------------------------------------------------------
    if "payment_events" not in existing_tables:
        op.create_table(
            "payment_events",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("provider", sa.String(32), nullable=False, index=True),
            sa.Column("provider_event_id", sa.String(128), nullable=False, index=True),
            sa.Column("event_id", sa.String(128), nullable=True, index=True),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("payload", sa.dialects.postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_unique_constraint(
            "uq_payment_events_provider_event",
            "payment_events",
            ["provider", "provider_event_id"],
        )
        created_tables.append("payment_events")
    else:
        pe_cols = {c["name"] for c in inspector.get_columns("payment_events")}

        # 1. Ensure provider column exists
        if "provider" not in pe_cols:
            op.add_column("payment_events", sa.Column("provider", sa.String(32), nullable=True))
            op.execute("UPDATE payment_events SET provider = 'stripe' WHERE provider IS NULL")
            op.alter_column("payment_events", "provider", nullable=False, server_default=sa.text("'stripe'"))

        # 2. Reconcile event_id vs provider_event_id
        if "provider_event_id" not in pe_cols and "event_id" in pe_cols:
            op.add_column("payment_events", sa.Column("provider_event_id", sa.String(128), nullable=True))
            op.execute("UPDATE payment_events SET provider_event_id = event_id WHERE provider_event_id IS NULL AND event_id IS NOT NULL")
            op.execute("UPDATE payment_events SET provider_event_id = id WHERE provider_event_id IS NULL")
            op.alter_column("payment_events", "provider_event_id", nullable=False)
            op.create_index("ix_payment_events_provider_event_id", "payment_events", ["provider_event_id"], unique=False)
            op.alter_column("payment_events", "event_id", nullable=True)
        elif "provider_event_id" in pe_cols and "event_id" not in pe_cols:
            op.add_column("payment_events", sa.Column("event_id", sa.String(128), nullable=True))
            op.execute("UPDATE payment_events SET event_id = provider_event_id WHERE event_id IS NULL AND provider_event_id IS NOT NULL")
        elif "provider_event_id" in pe_cols and "event_id" in pe_cols:
            op.execute("UPDATE payment_events SET provider_event_id = event_id WHERE (provider_event_id IS NULL OR provider_event_id = '') AND event_id IS NOT NULL")
            op.execute("UPDATE payment_events SET event_id = provider_event_id WHERE (event_id IS NULL OR event_id = '') AND provider_event_id IS NOT NULL")
            op.alter_column("payment_events", "event_id", nullable=True)

        # 3. Ensure event_type exists
        if "event_type" not in pe_cols:
            op.add_column("payment_events", sa.Column("event_type", sa.String(64), nullable=True))
            op.execute("UPDATE payment_events SET event_type = 'unknown' WHERE event_type IS NULL")
            op.alter_column("payment_events", "event_type", nullable=False, server_default=sa.text("'unknown'"))

        # 4. Reconcile raw_payload vs payload and migrate actual historical data
        if "payload" not in pe_cols:
            op.add_column(
                "payment_events",
                sa.Column("payload", sa.dialects.postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True),
            )

        if "raw_payload" in pe_cols:
            # Migrate actual data from raw_payload to payload safely
            import json as _json
            from typing import Any as _Any
            res = bind.execute(sa.text("SELECT id, raw_payload FROM payment_events WHERE raw_payload IS NOT NULL"))
            for row in res.fetchall():
                row_id, r_payload = row[0], row[1]
                parsed_payload: dict[str, _Any] = {}
                if isinstance(r_payload, dict):
                    parsed_payload = r_payload
                elif isinstance(r_payload, str):
                    try:
                        loaded = _json.loads(r_payload)
                        parsed_payload = loaded if isinstance(loaded, dict) else {"raw": loaded}
                    except Exception:
                        parsed_payload = {"raw": r_payload}
                else:
                    parsed_payload = {"raw": str(r_payload)}
                bind.execute(
                    sa.text("UPDATE payment_events SET payload = :p WHERE id = :id"),
                    {"p": _json.dumps(parsed_payload), "id": row_id},
                )
            # Make raw_payload nullable so new inserts using the updated ORM model succeed
            op.alter_column("payment_events", "raw_payload", nullable=True)

        op.execute("UPDATE payment_events SET payload = '{}' WHERE payload IS NULL")
        op.alter_column("payment_events", "payload", nullable=False, server_default=sa.text("'{}'"))

        # 5. Reconcile processed flag
        if "processed" not in pe_cols:
            op.add_column("payment_events", sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
            if "processed_at" in pe_cols:
                op.execute("UPDATE payment_events SET processed = true WHERE processed_at IS NOT NULL")

        # 6. Reconcile processed_at timestamp (ensure nullable)
        if "processed_at" not in pe_cols:
            op.add_column(
                "payment_events",
                sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            )
        else:
            op.alter_column(
                "payment_events",
                "processed_at",
                nullable=True,
            )

        # 7. Deduplicate legacy duplicate provider_event_id records before applying unique constraint
        try:
            # Check for duplicate (provider, provider_event_id)
            dup_res = bind.execute(sa.text(
                "SELECT provider, provider_event_id FROM payment_events "
                "WHERE provider IS NOT NULL AND provider_event_id IS NOT NULL "
                "GROUP BY provider, provider_event_id HAVING count(*) > 1"
            ))
            dups = dup_res.fetchall()
            for dup in dups:
                d_prov, d_evid = dup[0], dup[1]
                # Keep the first/most recent, rename subsequent with unique suffix so NO row is dropped
                rows_res = bind.execute(
                    sa.text("SELECT id FROM payment_events WHERE provider = :prv AND provider_event_id = :eid ORDER BY processed DESC, created_at DESC, id DESC"),
                    {"prv": d_prov, "eid": d_evid}
                )
                matching_ids = [r[0] for r in rows_res.fetchall()]
                # Keep matching_ids[0], modify subsequent
                for idx, dup_id in enumerate(matching_ids[1:], start=1):
                    new_eid = f"{d_evid}-legacy-dup-{idx}"
                    bind.execute(
                        sa.text("UPDATE payment_events SET provider_event_id = :neid, event_id = :neid WHERE id = :id"),
                        {"neid": new_eid, "id": dup_id}
                    )
        except Exception as exc:
            raise RuntimeError(
                f"Migration 012 failed during duplicate provider_event_id reconciliation: {exc}"
            ) from exc

        # 8. Ensure unique constraint exists
        constraints = {c["name"] for c in inspector.get_unique_constraints("payment_events")}
        if "uq_payment_events_provider_event" not in constraints:
            try:
                op.create_unique_constraint(
                    "uq_payment_events_provider_event",
                    "payment_events",
                    ["provider", "provider_event_id"],
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Migration 012 failed to create unique constraint 'uq_payment_events_provider_event': {exc}"
                ) from exc

    # -------------------------------------------------------------------------
    # 5. payment_methods table (Customer Payment Methods)
    # -------------------------------------------------------------------------
    if "payment_methods" not in existing_tables:
        op.create_table(
            "payment_methods",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("user_id", sa.String(64), nullable=False, index=True),
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
        created_tables.append("payment_methods")
    else:
        pm_cols = {c["name"] for c in inspector.get_columns("payment_methods")}
        if "stripe_payment_method_id" not in pm_cols:
            op.add_column(
                "payment_methods",
                sa.Column("stripe_payment_method_id", sa.String(128), nullable=False, server_default=sa.text("''")),
            )
        if "provider_payment_method_id" not in pm_cols:
            op.add_column(
                "payment_methods",
                sa.Column("provider_payment_method_id", sa.String(128), nullable=True),
            )

    # -------------------------------------------------------------------------
    # 6. credit_wallets table (User Token Balance)
    # -------------------------------------------------------------------------
    if "credit_wallets" not in existing_tables:
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
        created_tables.append("credit_wallets")

    # -------------------------------------------------------------------------
    # 7. usage_logs table (Token and Feature Consumption)
    # -------------------------------------------------------------------------
    if "usage_logs" not in existing_tables:
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
        created_tables.append("usage_logs")

    # Record strictly created tables in the metadata tracker table
    if created_tables:
        insert_rows = ", ".join(f"('{tbl}')" for tbl in created_tables)
        op.execute(
            sa.text(
                f"INSERT INTO _alembic_012_created_tables (table_name) VALUES {insert_rows} "
                f"ON CONFLICT (table_name) DO NOTHING"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    try:
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())
    except Exception as exc:
        raise RuntimeError(f"Database schema inspection failed during migration 012 downgrade: {exc}") from exc

    # Safe data preservation strategy:
    # Query strictly created tables recorded by migration 012.
    strictly_created_tables: set[str] = set()
    if "_alembic_012_created_tables" in existing_tables:
        res = bind.execute(sa.text("SELECT table_name FROM _alembic_012_created_tables"))
        strictly_created_tables = {row[0] for row in res.fetchall()}

    tables_to_drop_order = [
        "usage_logs",
        "credit_wallets",
        "payment_methods",
        "payment_events",
        "payments",
        "subscriptions",
        "connector_instances",
    ]

    for table in tables_to_drop_order:
        # Only drop table if it was CREATED by this migration.
        # NEVER drop pre-existing tables to prevent destroying historical records!
        if table in strictly_created_tables and table in existing_tables:
            op.drop_table(table)

    # Clean up the migration tracker table
    if "_alembic_012_created_tables" in existing_tables:
        op.drop_table("_alembic_012_created_tables")
