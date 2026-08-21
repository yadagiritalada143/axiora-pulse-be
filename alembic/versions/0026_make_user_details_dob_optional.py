"""Make user_details.date_of_birth optional

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-20 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("user_details", "date_of_birth", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    op.alter_column("user_details", "date_of_birth", existing_type=sa.Date(), nullable=False)
