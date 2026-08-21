"""Create token_usages table

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-20 00:00:00.000000 UTC

Adds the token_usages table for tracking and analyzing LLM token usage per user and per workspace.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "token_usages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="openai"),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_token_usages_id",
        "token_usages",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_token_usages_user_id",
        "token_usages",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_token_usages_workspace_id",
        "token_usages",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_token_usages_agent_name",
        "token_usages",
        ["agent_name"],
        unique=False,
    )
    op.create_index(
        "ix_token_usages_source",
        "token_usages",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ix_token_usages_created_at",
        "token_usages",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_token_usages_user_created",
        "token_usages",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_token_usages_workspace_created",
        "token_usages",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_token_usages_user_workspace",
        "token_usages",
        ["user_id", "workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_token_usages_user_workspace", table_name="token_usages")
    op.drop_index("ix_token_usages_workspace_created", table_name="token_usages")
    op.drop_index("ix_token_usages_user_created", table_name="token_usages")
    op.drop_index("ix_token_usages_created_at", table_name="token_usages")
    op.drop_index("ix_token_usages_source", table_name="token_usages")
    op.drop_index("ix_token_usages_agent_name", table_name="token_usages")
    op.drop_index("ix_token_usages_workspace_id", table_name="token_usages")
    op.drop_index("ix_token_usages_user_id", table_name="token_usages")
    op.drop_index("ix_token_usages_id", table_name="token_usages")
    op.drop_table("token_usages")
