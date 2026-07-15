"""Add register_otp_attempts to users table

Revision ID: 0002
Revises: 0001
Create Date: 2025-07-14 01:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add register_otp_attempts column to users table."""
    op.add_column(
        "users",
        sa.Column(
            "register_otp_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Remove register_otp_attempts column from users table."""
    op.drop_column("users", "register_otp_attempts")
