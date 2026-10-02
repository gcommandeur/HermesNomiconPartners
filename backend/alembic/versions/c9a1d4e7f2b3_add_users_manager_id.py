"""add users.manager_id (Teamleiter-Zuordnung)

Revision ID: c9a1d4e7f2b3
Revises: b4e8c2f1a9d7
Create Date: 2026-10-02

Rolle "team_lead": sieht die Prozesse von sich und den Mitarbeitern, die ihm
ueber users.manager_id zugeordnet sind. Self-referenzierender FK, nullable.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9a1d4e7f2b3"
down_revision: str | None = "b4e8c2f1a9d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("manager_id", sa.Uuid(), nullable=True))
        batch_op.create_index(op.f("ix_users_manager_id"), ["manager_id"])
        batch_op.create_foreign_key(
            op.f("fk_users_manager_id_users"), "users", ["manager_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(op.f("fk_users_manager_id_users"), type_="foreignkey")
        batch_op.drop_index(op.f("ix_users_manager_id"))
        batch_op.drop_column("manager_id")
