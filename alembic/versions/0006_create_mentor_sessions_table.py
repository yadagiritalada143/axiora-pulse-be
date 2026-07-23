"""Create mentor sessions table

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-16 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create mentor_sessions table."""
    op.create_table(
        "mentor_sessions",
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False, server_default="GATHERING_INFO"),
        sa.Column("idea", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("conversation_history", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("validation_result", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(op.f("ix_mentor_sessions_session_id"), "mentor_sessions", ["session_id"], unique=False)


def downgrade() -> None:
    """Drop mentor_sessions table."""
    op.drop_index(op.f("ix_mentor_sessions_session_id"), table_name="mentor_sessions")
    op.drop_table("mentor_sessions")
