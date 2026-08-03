"""Create auth_actions table.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-03 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("payment", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("interactive_questions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_auth_actions_user_id"),
    )
    op.create_index(
        op.f("ix_auth_actions_id"), "auth_actions", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_auth_actions_user_id"), "auth_actions", ["user_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_actions_user_id"), table_name="auth_actions")
    op.drop_index(op.f("ix_auth_actions_id"), table_name="auth_actions")
    op.drop_table("auth_actions")
