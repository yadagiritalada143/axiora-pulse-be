"""Create surveys table

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-04 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create surveys table."""
    op.create_table(
        "surveys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("survey_link", sa.String(length=2048), nullable=True),
        sa.Column("questions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_surveys_id"), "surveys", ["id"], unique=False)
    op.create_index(op.f("ix_surveys_user_id"), "surveys", ["user_id"], unique=False)
    op.create_index(op.f("ix_surveys_workspace_id"), "surveys", ["workspace_id"], unique=False)


def downgrade() -> None:
    """Drop surveys table."""
    op.drop_index(op.f("ix_surveys_workspace_id"), table_name="surveys")
    op.drop_index(op.f("ix_surveys_user_id"), table_name="surveys")
    op.drop_index(op.f("ix_surveys_id"), table_name="surveys")
    op.drop_table("surveys")
