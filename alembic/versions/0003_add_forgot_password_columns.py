"""Add forgot_password columns to users table

Revision ID: 0003
Revises: 0002
Create Date: 2025-07-15 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add forgot_password_otp and forgot_password_otp_expiry columns to users table."""
    op.add_column(
        "users",
        sa.Column(
            "forgot_password_otp",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "forgot_password_otp_expiry",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove forgot_password_otp and forgot_password_otp_expiry columns from users table."""
    op.drop_column("users", "forgot_password_otp")
    op.drop_column("users", "forgot_password_otp_expiry")
