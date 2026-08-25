"""add candidate abschluesse/rechtsgebiete/examensnoten, widen current_employer_internal

Revision ID: c1a9d5e7f402
Revises: b7e4c9a1f320
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1a9d5e7f402"
down_revision: str | None = "b7e4c9a1f320"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column("abschluesse", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "candidates",
        sa.Column("rechtsgebiete", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("candidates", sa.Column("examensnoten", sa.String(240)))
    # String(240) -> Text: lange Firmennamen (mehrere Gesellschaften/
    # Rechtsform) waren mit 240 Zeichen zu knapp bemessen, siehe
    # models/candidate.py::current_employer_internal. batch_alter_table noetig
    # fuer SQLite (lokale Entwicklung) - Postgres (Produktion) haette
    # op.alter_column() auch direkt vertragen.
    with op.batch_alter_table("candidates") as batch_op:
        batch_op.alter_column(
            "current_employer_internal", existing_type=sa.String(240), type_=sa.Text()
        )


def downgrade() -> None:
    with op.batch_alter_table("candidates") as batch_op:
        batch_op.alter_column(
            "current_employer_internal", existing_type=sa.Text(), type_=sa.String(240)
        )
    op.drop_column("candidates", "examensnoten")
    op.drop_column("candidates", "rechtsgebiete")
    op.drop_column("candidates", "abschluesse")
