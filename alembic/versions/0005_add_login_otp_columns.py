"""Add login_otp and login_otp_expiry to users table

Revision ID: 0005
Revises: 0004
Create Date: 2025-07-15 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add login_otp and login_otp_expiry columns to users table."""
    op.add_column(
        "users",
        sa.Column("login_otp", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("login_otp_expiry", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove login_otp and login_otp_expiry columns from users table."""
    op.drop_column("users", "login_otp_expiry")
    op.drop_column("users", "login_otp")
