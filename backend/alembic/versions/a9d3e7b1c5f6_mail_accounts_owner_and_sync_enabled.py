"""mail_accounts: owner_user_id (persoenliche Postfaecher) und sync_enabled

Revision ID: a9d3e7b1c5f6
Revises: a3e5c7b9d1f2
Create Date: 2026-10-04

Bestand bleibt gemeinsam (owner_user_id NULL) und wird weiter abgerufen
(sync_enabled true).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9d3e7b1c5f6"
down_revision: str | None = "a3e5c7b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mail_accounts") as batch:
        batch.add_column(sa.Column("owner_user_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("sync_enabled", sa.Boolean(), server_default=sa.true(), nullable=False)
        )
        batch.create_foreign_key(
            op.f("fk_mail_accounts_owner_user_id_users"),
            "users",
            ["owner_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_mail_accounts_owner_user_id"), ["owner_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("mail_accounts") as batch:
        batch.drop_index(op.f("ix_mail_accounts_owner_user_id"))
        batch.drop_constraint(op.f("fk_mail_accounts_owner_user_id_users"), type_="foreignkey")
        batch.drop_column("sync_enabled")
        batch.drop_column("owner_user_id")
