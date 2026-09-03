"""Create roles and user_roles tables, migrate data, drop old role column

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-26 12:00:00.000000 UTC

Roles:
  - admin   — full platform access, bypasses subscription
  - member  — paid subscription users
  - viewer  — starter / free-tier users
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES_SEED = [
    {"name": "admin", "description": "Full platform access; bypasses subscription checks"},
    {"name": "member", "description": "Paid subscription user"},
    {"name": "viewer", "description": "Starter / free-tier user"},
]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ── 1. Create roles table ─────────────────────────────────────────────────
    if not insp.has_table("roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=20), nullable=False, unique=True, index=True),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # ── 2. Seed role rows (idempotent) ───────────────────────────────────────
    roles_table = sa.table(
        "roles",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
    )
    existing = {row[0] for row in bind.execute(sa.select(roles_table.c.name)).fetchall()}
    for role in ROLES_SEED:
        if role["name"] not in existing:
            op.execute(roles_table.insert().values(**role))

    # ── 3. Create user_roles junction table ──────────────────────────────────
    if not insp.has_table("user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        )

    # ── 4. Migrate existing users from old role column → user_roles ──────────
    users_table = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("role", sa.String),
    )
    user_roles_table = sa.table(
        "user_roles",
        sa.column("user_id", sa.Integer),
        sa.column("role_id", sa.Integer),
    )

    columns = [c["name"] for c in insp.get_columns("users")]
    if "role" in columns:
        role_map = {}
        for row in bind.execute(sa.select(roles_table.c.id, roles_table.c.name)).fetchall():
            role_map[row[1]] = row[0]

        users_with_roles = bind.execute(
            sa.select(users_table.c.id, users_table.c.role).where(users_table.c.role.isnot(None))
        ).fetchall()

        for user_id, role_name in users_with_roles:
            role_id = role_map.get(role_name)
            if role_id is not None:
                already = bind.execute(
                    sa.select(user_roles_table).where(
                        user_roles_table.c.user_id == user_id,
                        user_roles_table.c.role_id == role_id,
                    )
                ).first()
                if not already:
                    op.execute(
                        user_roles_table.insert().values(user_id=user_id, role_id=role_id)
                    )

        # ── 5. Drop the old role column ──────────────────────────────────────
        op.drop_column("users", "role")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    columns = [c["name"] for c in insp.get_columns("users")]
    if "role" not in columns:
        op.add_column("users", sa.Column("role", sa.String(length=20), nullable=False, server_default="user"))

    if insp.has_table("user_roles"):
        op.drop_table("user_roles")
    if insp.has_table("roles"):
        op.drop_table("roles")
