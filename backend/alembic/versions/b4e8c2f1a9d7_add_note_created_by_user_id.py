"""add notes.created_by_user_id

Revision ID: b4e8c2f1a9d7
Revises: a7d3e91c5b20
Create Date: 2026-10-02

Autor einer Notiz (Kandidaten-Timeline: "jeder Kommentar soll anzeigen,
von wem er stammt"). Nullable - Alt-Notizen und automatisch erzeugte Notizen
(Mail-Sync, CV-Profilnotiz) behalten NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4e8c2f1a9d7"
down_revision: str | None = "a7d3e91c5b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notes") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Uuid(), nullable=True))
        batch_op.create_index(op.f("ix_notes_created_by_user_id"), ["created_by_user_id"])
        batch_op.create_foreign_key(
            op.f("fk_notes_created_by_user_id_users"),
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("notes") as batch_op:
        batch_op.drop_constraint(op.f("fk_notes_created_by_user_id_users"), type_="foreignkey")
        batch_op.drop_index(op.f("ix_notes_created_by_user_id"))
        batch_op.drop_column("created_by_user_id")
