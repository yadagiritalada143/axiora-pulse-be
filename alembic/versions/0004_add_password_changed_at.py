"""Add password_changed_at to users table

Revision ID: 0004
Revises: 0003
Create Date: 2025-07-15 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add password_changed_at column to users table."""
    op.add_column(
        "users",
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove password_changed_at column from users table."""
    op.drop_column("users", "password_changed_at")
