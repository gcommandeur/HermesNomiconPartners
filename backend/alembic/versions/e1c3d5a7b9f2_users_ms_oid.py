"""users.ms_oid: unveraenderliche Microsoft-Kennung fuer den Microsoft-Login

Revision ID: e1c3d5a7b9f2
Revises: c1f5a9b3d7e8
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1c3d5a7b9f2"
down_revision: str | None = "c1f5a9b3d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("ms_oid", sa.String(64), nullable=True))
        batch.create_index(op.f("ix_users_ms_oid"), ["ms_oid"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index(op.f("ix_users_ms_oid"))
        batch.drop_column("ms_oid")
