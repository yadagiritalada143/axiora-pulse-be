"""Create user_details table (extended profile, 1:1 with users)

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-20 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("user_details"):
        op.create_table(
            "user_details",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("profile_id", sa.String(length=20), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("first_name", sa.String(length=100), nullable=False),
            sa.Column("last_name", sa.String(length=100), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("mobile_number", sa.String(length=20), nullable=False),
            sa.Column("date_of_birth", sa.Date(), nullable=False),
            sa.Column("gender", sa.String(length=20), nullable=True),
            sa.Column("profile_status", sa.String(length=20), nullable=False, server_default="Active"),
            sa.Column("nationality", sa.String(length=100), nullable=True),
            sa.Column("communication_preferences", sa.JSON(), nullable=False),
            sa.Column("last_login_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("profile_id", name="uq_user_details_profile_id"),
            sa.UniqueConstraint("user_id", name="uq_user_details_user_id"),
        )
        op.create_index(op.f("ix_user_details_id"), "user_details", ["id"], unique=False)
        op.create_index(op.f("ix_user_details_profile_id"), "user_details", ["profile_id"], unique=False)
        op.create_index(op.f("ix_user_details_user_id"), "user_details", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_details_user_id"), table_name="user_details")
    op.drop_index(op.f("ix_user_details_profile_id"), table_name="user_details")
    op.drop_index(op.f("ix_user_details_id"), table_name="user_details")
    op.drop_table("user_details")
