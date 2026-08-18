"""Add analysis_result JSON column to surveys table

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-13 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("surveys", sa.Column("analysis_result", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("surveys", "analysis_result")
