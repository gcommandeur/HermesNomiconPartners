"""add client_companies.kanzleigruppe (brand/network name for multi-location clients)

Revision ID: b7d1e4f9a2c6
Revises: a3c8e1f6b2d7
Create Date: 2026-07-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7d1e4f9a2c6"
down_revision: str | None = "a3c8e1f6b2d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "client_companies",
        sa.Column("kanzleigruppe", sa.String(length=160), nullable=True),
    )
    op.create_index(
        "ix_client_companies_kanzleigruppe",
        "client_companies",
        ["kanzleigruppe"],
    )


def downgrade() -> None:
    op.drop_index("ix_client_companies_kanzleigruppe", table_name="client_companies")
    op.drop_column("client_companies", "kanzleigruppe")
