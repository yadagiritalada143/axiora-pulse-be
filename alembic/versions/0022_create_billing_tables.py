"""Create billing tables (plans, subscriptions, payments, webhook_events)

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-18 00:00:00.000000 UTC

Adds the Razorpay Subscriptions billing schema and seeds the plan catalog with
placeholder rows. The `razorpay_plan_id_*` columns are left NULL — fill them in
(via SQL or an admin update) once the matching Plans are created in the Razorpay
dashboard.
"""
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── plans ──────────────────────────────────────────────────────────────────
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("razorpay_plan_id_monthly", sa.String(length=255), nullable=True),
        sa.Column("razorpay_plan_id_yearly", sa.String(length=255), nullable=True),
        sa.Column("price_monthly", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_yearly", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("popular", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_plans_code"),
    )
    op.create_index(op.f("ix_plans_id"), "plans", ["id"], unique=False)
    op.create_index(op.f("ix_plans_code"), "plans", ["code"], unique=False)

    # ── subscriptions ──────────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("razorpay_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("razorpay_plan_id", sa.String(length=255), nullable=False),
        sa.Column("billing_period", sa.String(length=10), nullable=False, server_default="monthly"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="created"),
        sa.Column("short_url", sa.Text(), nullable=True),
        sa.Column("current_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("razorpay_subscription_id", name="uq_subscriptions_rzp_sub_id"),
    )
    op.create_index(op.f("ix_subscriptions_id"), "subscriptions", ["id"], unique=False)
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_subscriptions_razorpay_subscription_id"),
        "subscriptions",
        ["razorpay_subscription_id"],
        unique=False,
    )
    op.create_index(op.f("ix_subscriptions_status"), "subscriptions", ["status"], unique=False)

    # ── payments ───────────────────────────────────────────────────────────────
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(length=255), nullable=False),
        sa.Column("razorpay_invoice_id", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("method", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("razorpay_payment_id", name="uq_payments_rzp_payment_id"),
    )
    op.create_index(op.f("ix_payments_id"), "payments", ["id"], unique=False)
    op.create_index("ix_payments_user_id", "payments", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_payments_razorpay_payment_id"), "payments", ["razorpay_payment_id"], unique=False
    )

    # ── webhook_events ─────────────────────────────────────────────────────────
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_webhook_events_event_id"),
    )
    op.create_index(op.f("ix_webhook_events_id"), "webhook_events", ["id"], unique=False)
    op.create_index(op.f("ix_webhook_events_event_id"), "webhook_events", ["event_id"], unique=False)

    # ── Seed the plan catalog ──────────────────────────────────────────────────
    # Mirrors the pricing page catalog. All three tiers are paid, so each carries a
    # NULL razorpay_plan_id_* until the matching Plans are created in the Razorpay
    # dashboard and back-filled (via SQL or an admin update).
    plans_table = sa.table(
        "plans",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("price_monthly", sa.Integer),
        sa.column("price_yearly", sa.Integer),
        sa.column("currency", sa.String),
        sa.column("features", sa.JSON),
        sa.column("tier", sa.Integer),
        sa.column("popular", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    # A concrete datetime, not sa.func.now(): op.bulk_insert binds these as
    # executemany parameters, and asyncpg rejects a SQL function object there.
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        plans_table,
        [
            {
                "code": "starter",
                "name": "Starter Plan",
                "description": "Perfect for individuals exploring startup ideas.",
                "price_monthly": 799,
                "price_yearly": 7990,
                "currency": "INR",
                "features": [
                    "AI Co-Founder (Basic)",
                    "20 AI conversations / month",
                    "Founder Foundation",
                    "5 AI-generated documents",
                    "Basic Founder Intelligence",
                    "Community Support",
                ],
                "tier": 1,
                "popular": False,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "professional",
                "name": "Professional",
                "description": "Perfect for individuals exploring startup ideas.",
                "price_monthly": 999,
                "price_yearly": 9990,
                "currency": "INR",
                "features": [
                    "AI Co-Founder (Basic)",
                    "10 AI conversations / month",
                    "Founder Foundation",
                    "5 AI-generated documents",
                    "Basic Founder Intelligence",
                    "Community Support",
                ],
                "tier": 2,
                "popular": True,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "code": "enterprise",
                "name": "Enterprise",
                "description": "Perfect for individuals exploring startup ideas.",
                "price_monthly": 1499,
                "price_yearly": 14990,
                "currency": "INR",
                "features": [
                    "AI Co-Founder (Basic)",
                    "20 AI conversations / month",
                    "Founder Foundation",
                    "5 AI-generated documents",
                    "Basic Founder Intelligence",
                    "Community Support",
                ],
                "tier": 3,
                "popular": False,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_webhook_events_event_id"), table_name="webhook_events")
    op.drop_index(op.f("ix_webhook_events_id"), table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_index(op.f("ix_payments_razorpay_payment_id"), table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_index(op.f("ix_payments_id"), table_name="payments")
    op.drop_table("payments")

    op.drop_index(op.f("ix_subscriptions_status"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_razorpay_subscription_id"), table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_id"), table_name="subscriptions")
    op.drop_table("subscriptions")

    op.drop_index(op.f("ix_plans_code"), table_name="plans")
    op.drop_index(op.f("ix_plans_id"), table_name="plans")
    op.drop_table("plans")
