"""Add public_token column to surveys table

Opaque, unguessable identifier used in the public survey link instead of the
sequential `id` — prevents respondents from enumerating other users' surveys
by incrementing the URL.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-13 00:00:00.000000 UTC
"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("surveys", sa.Column("public_token", sa.String(length=64), nullable=True))

    # Backfill existing rows with a random token before enforcing NOT NULL + UNIQUE.
    bind = op.get_bind()
    surveys = sa.table("surveys", sa.column("id", sa.Integer), sa.column("public_token", sa.String))
    for (survey_id,) in bind.execute(sa.select(surveys.c.id)):
        bind.execute(
            surveys.update()
            .where(surveys.c.id == survey_id)
            .values(public_token=uuid.uuid4().hex)
        )

    with op.batch_alter_table("surveys") as batch_op:
        batch_op.alter_column("public_token", existing_type=sa.String(length=64), nullable=False)

    op.create_index(
        "ix_surveys_public_token",
        "surveys",
        ["public_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_surveys_public_token", table_name="surveys")
    op.drop_column("surveys", "public_token")
