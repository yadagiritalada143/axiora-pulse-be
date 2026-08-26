"""Add avatar_url to user_details table

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-25 12:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("user_details"):
        columns = [c["name"] for c in insp.get_columns("user_details")]
        if "avatar_url" not in columns:
            op.add_column("user_details", sa.Column("avatar_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("user_details"):
        columns = [c["name"] for c in insp.get_columns("user_details")]
        if "avatar_url" in columns:
            op.drop_column("user_details", "avatar_url")
