"""Embed state, idea, conversation_history, and validation_result in workspaces table

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-24 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add state columns directly to workspaces table."""
    op.add_column("workspaces", sa.Column("state", sa.String(length=50), nullable=False, server_default="GATHERING_INFO"))
    op.add_column("workspaces", sa.Column("idea", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("workspaces", sa.Column("conversation_history", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("workspaces", sa.Column("validation_result", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Drop state columns from workspaces table."""
    op.drop_column("workspaces", "validation_result")
    op.drop_column("workspaces", "conversation_history")
    op.drop_column("workspaces", "idea")
    op.drop_column("workspaces", "state")
