"""Create workspace_states table

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-24 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create workspace_states table."""
    op.create_table(
        "workspace_states",
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False, server_default="GATHERING_INFO"),
        sa.Column("idea", sa.JSON(), nullable=False),
        sa.Column("conversation_history", sa.JSON(), nullable=False),
        sa.Column("validation_result", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.create_index(op.f("ix_workspace_states_workspace_id"), "workspace_states", ["workspace_id"], unique=False)


def downgrade() -> None:
    """Drop workspace_states table."""
    op.drop_index(op.f("ix_workspace_states_workspace_id"), table_name="workspace_states")
    op.drop_table("workspace_states")
