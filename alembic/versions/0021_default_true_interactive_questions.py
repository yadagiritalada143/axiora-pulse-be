"""Default auth_actions.interactive_questions to true.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-17 00:00:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "auth_actions",
        "interactive_questions",
        server_default=sa.text("true"),
    )


def downgrade() -> None:
    op.alter_column(
        "auth_actions",
        "interactive_questions",
        server_default=sa.text("false"),
    )
