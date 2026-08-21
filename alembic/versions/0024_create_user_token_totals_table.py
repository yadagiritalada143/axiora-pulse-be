"""Create user_token_totals table

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-20 16:20:00.000000 UTC

Adds the user_token_totals table for maintaining 1 row per user containing cumulative
input tokens, output tokens, total tokens, total cost, and invocation counts.
Backfills data from existing token_usages records.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_token_totals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_token_totals_user_id"),
    )
    op.create_index(
        "ix_user_token_totals_id",
        "user_token_totals",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_user_token_totals_user_id",
        "user_token_totals",
        ["user_id"],
        unique=True,
    )

    # 1. Backfill from existing token_usages records (if any exist)
    op.execute(
        """
        INSERT INTO user_token_totals (user_id, prompt_tokens, completion_tokens, total_tokens, total_cost, total_calls, created_at, updated_at)
        SELECT 
            user_id,
            COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
            COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(estimated_cost), 0.0) AS total_cost,
            COUNT(id) AS total_calls,
            MIN(created_at) AS created_at,
            MAX(created_at) AS updated_at
        FROM token_usages
        GROUP BY user_id
        ON CONFLICT (user_id) DO NOTHING;
        """
    )

    # 2. Initialize 0-token rows for all existing users who haven't made LLM calls yet
    op.execute(
        """
        INSERT INTO user_token_totals (user_id, prompt_tokens, completion_tokens, total_tokens, total_cost, total_calls, created_at, updated_at)
        SELECT 
            id AS user_id,
            0 AS prompt_tokens,
            0 AS completion_tokens,
            0 AS total_tokens,
            0.0 AS total_cost,
            0 AS total_calls,
            NOW() AS created_at,
            NOW() AS updated_at
        FROM users
        ON CONFLICT (user_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_token_totals_user_id", table_name="user_token_totals")
    op.drop_index("ix_user_token_totals_id", table_name="user_token_totals")
    op.drop_table("user_token_totals")
