"""Simplify user role: replace M2M user_roles with direct role_id FK on users.

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add role_id column to users (nullable initially for data migration)
    op.add_column("users", sa.Column("role_id", sa.Integer(), nullable=True))

    # 2. Populate role_id from user_roles junction table
    op.execute("""
        UPDATE users
        SET role_id = (
            SELECT ur.role_id
            FROM user_roles ur
            WHERE ur.user_id = users.id
            LIMIT 1
        )
    """)

    # 3. Default any remaining NULLs to viewer (id=3)
    op.execute("""
        UPDATE users
        SET role_id = (SELECT id FROM roles WHERE name = 'viewer' LIMIT 1)
        WHERE role_id IS NULL
    """)

    # 4. Add NOT NULL constraint and FK
    op.alter_column("users", "role_id", nullable=False)
    op.create_foreign_key("fk_users_role_id", "users", "roles", ["role_id"], ["id"], ondelete="RESTRICT")

    # 5. Drop the junction table
    op.drop_table("user_roles")


def downgrade() -> None:
    # Recreate junction table
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )

    # Populate junction table from role_id
    op.execute("""
        INSERT INTO user_roles (user_id, role_id)
        SELECT id, role_id FROM users
    """)

    # Drop FK and column
    op.drop_constraint("fk_users_role_id", "users", type_="foreignkey")
    op.drop_column("users", "role_id")
