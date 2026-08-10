"""Create workspace_attachments table

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-06 12:30:00.000000 UTC
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ── Revision identifiers ───────────────────────────────────────────────────────
revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create workspace_attachments table."""
    op.create_table(
        "workspace_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False, server_default="application/octet-stream"),
        sa.Column("s3_key", sa.String(length=1024), nullable=False),
        sa.Column("file_url", sa.String(length=2048), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "file_type IN ('image', 'pdf', 'doc')",
            name="ck_workspace_attachments_file_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workspace_attachments_id"), "workspace_attachments", ["id"], unique=False)
    op.create_index(op.f("ix_workspace_attachments_user_id"), "workspace_attachments", ["user_id"], unique=False)
    op.create_index(op.f("ix_workspace_attachments_workspace_id"), "workspace_attachments", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_workspace_attachments_file_type"), "workspace_attachments", ["file_type"], unique=False)


def downgrade() -> None:
    """Drop workspace_attachments table."""
    op.drop_index(op.f("ix_workspace_attachments_file_type"), table_name="workspace_attachments")
    op.drop_index(op.f("ix_workspace_attachments_workspace_id"), table_name="workspace_attachments")
    op.drop_index(op.f("ix_workspace_attachments_user_id"), table_name="workspace_attachments")
    op.drop_index(op.f("ix_workspace_attachments_id"), table_name="workspace_attachments")
    op.drop_table("workspace_attachments")
