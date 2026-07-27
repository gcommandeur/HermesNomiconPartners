"""add notes_text to sourcing_leads (Stellenbeschreibung/Werdegang laut Quelle fuer die spaetere Notiz nach Uebernahme)

Revision ID: b4f7e1a9c3d6
Revises: d1f4a8c2e6b9
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4f7e1a9c3d6"
down_revision: str | None = "d1f4a8c2e6b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sourcing_leads", sa.Column("notes_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sourcing_leads", "notes_text")
