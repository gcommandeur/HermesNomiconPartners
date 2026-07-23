"""add postal_localities table (PLZ<->Ort reference dataset, Phase 4b)

Revision ID: b2c5d8e1f4a7
Revises: a9d4e2f7c8b1
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c5d8e1f4a7"
down_revision: str | None = "a9d4e2f7c8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "postal_localities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("postal_code", sa.String(length=5), nullable=False),
        sa.Column("locality", sa.String(length=160), nullable=False),
        sa.Column("borough", sa.String(length=160), nullable=True),
        sa.Column("suburb", sa.String(length=160), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_postal_localities_postal_code", "postal_localities", ["postal_code"]
    )
    op.create_index("ix_postal_localities_locality", "postal_localities", ["locality"])


def downgrade() -> None:
    op.drop_index("ix_postal_localities_locality", table_name="postal_localities")
    op.drop_index("ix_postal_localities_postal_code", table_name="postal_localities")
    op.drop_table("postal_localities")
