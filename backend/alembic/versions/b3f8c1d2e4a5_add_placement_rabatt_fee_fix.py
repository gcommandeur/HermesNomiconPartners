"""add placements.rabatt_percentage and placements.fee_fix

Additiv: rabatt_percentage reduziert die berechnete Fee prozentual (Default 0,
kein Verhalten fuer Bestandsdaten geaendert). fee_fix ist nullable - wenn
gesetzt, wird dieser Betrag 1:1 als calculated_fee uebernommen und
Honorarsatz/Rabatt werden ignoriert (siehe services/recruiting.py).

Revision ID: b3f8c1d2e4a5
Revises: c7d8e9f0a1b2
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b3f8c1d2e4a5"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "placements",
        sa.Column(
            "rabatt_percentage",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "placements",
        sa.Column("fee_fix", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("placements", "fee_fix")
    op.drop_column("placements", "rabatt_percentage")
