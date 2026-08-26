"""Add Google SSO columns and relax password / mobile_number nullability

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-25 00:00:00.000000 UTC

Adds federated-login support:
  - users.auth_provider  → "local" (default) or "google"
  - users.google_sub     → Google's stable subject id (unique, nullable)
  - users.password       → now nullable (Google accounts have no local password)
  - user_details.mobile_number → now nullable (Google provides no phone number)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_provider",
            sa.String(length=20),
            nullable=False,
            server_default="local",
        ),
    )
    op.add_column(
        "users",
        sa.Column("google_sub", sa.String(length=255), nullable=True),
    )
    op.create_index(op.f("ix_users_google_sub"), "users", ["google_sub"], unique=True)

    op.alter_column("users", "password", existing_type=sa.String(length=512), nullable=True)
    op.alter_column(
        "user_details", "mobile_number", existing_type=sa.String(length=20), nullable=True
    )


def downgrade() -> None:
    # Restore NOT NULL constraints. Any Google-only rows (null password /
    # mobile_number) must be backfilled or removed before downgrading.
    op.alter_column(
        "user_details", "mobile_number", existing_type=sa.String(length=20), nullable=False
    )
    op.alter_column("users", "password", existing_type=sa.String(length=512), nullable=False)

    op.drop_index(op.f("ix_users_google_sub"), table_name="users")
    op.drop_column("users", "google_sub")
    op.drop_column("users", "auth_provider")
