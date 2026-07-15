"""Create users table

Revision ID: 0001
Revises: None (initial migration)
Create Date: 2025-07-14 00:00:00.000000 UTC

Schema:
  users
    id                  SERIAL PRIMARY KEY
    role                VARCHAR(20)   NOT NULL DEFAULT 'user'
    username            VARCHAR(255)  NOT NULL UNIQUE
    password            VARCHAR(512)  NOT NULL
    register_otp        INTEGER       NULL
    register_otp_expiry TIMESTAMPTZ   NULL
    register_mfa        BOOLEAN       NOT NULL DEFAULT FALSE
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0001"
down_revision: Union[str, None] = None   # First migration — no parent
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Upgrade ────────────────────────────────────────────────────────────────────

def upgrade() -> None:
    """Create the `users` table with all 7 columns from the spec."""
    op.create_table(
        "users",

        # PK — integer, autoincrement, starts at 1
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),

        # Role — "user" | "admin"
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),

        # Username — unique email or phone number used as the login identifier
        sa.Column(
            "username",
            sa.String(length=255),
            nullable=False,
        ),

        # Password — PBKDF2-HMAC-SHA256 hash stored as "<hex_salt>:<hex_hash>"
        sa.Column(
            "password",
            sa.String(length=512),
            nullable=False,
        ),

        # OTP — 6-digit integer, NULL once verified or expired
        sa.Column(
            "register_otp",
            sa.Integer(),
            nullable=True,
        ),

        # OTP expiry — timezone-aware timestamp, NULL once consumed
        sa.Column(
            "register_otp_expiry",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # MFA flag — set to TRUE after the user successfully verifies their OTP
        sa.Column(
            "register_mfa",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ── Indexes ────────────────────────────────────────────────────────────────
    # Unique index on username enforces one account per email/phone
    op.create_index(
        "ix_users_username",
        "users",
        ["username"],
        unique=True,
    )

    # Non-unique index on id (already covered by PK, but explicit for clarity)
    op.create_index(
        "ix_users_id",
        "users",
        ["id"],
        unique=False,
    )


# ── Downgrade ──────────────────────────────────────────────────────────────────

def downgrade() -> None:
    """Drop the `users` table and all its indexes."""
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
