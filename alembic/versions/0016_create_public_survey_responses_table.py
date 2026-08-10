"""Create public_survey_responses table

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-04 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create public_survey_responses table."""
    op.create_table(
        "public_survey_responses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("survey_id", sa.Integer(), nullable=False),
        sa.Column("respondent_email", sa.String(length=255), nullable=True),
        sa.Column("answers", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["survey_id"], ["surveys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_public_survey_responses_id"), "public_survey_responses", ["id"], unique=False)
    op.create_index(op.f("ix_public_survey_responses_survey_id"), "public_survey_responses", ["survey_id"], unique=False)


def downgrade() -> None:
    """Drop public_survey_responses table."""
    op.drop_index(op.f("ix_public_survey_responses_survey_id"), table_name="public_survey_responses")
    op.drop_index(op.f("ix_public_survey_responses_id"), table_name="public_survey_responses")
    op.drop_table("public_survey_responses")
