"""add cv_in_recorded_at to candidates

Revision ID: a3f7c1e9d4b2
Revises: d5f8e3a7b1c9
Create Date: 2026-07-15

Stichtag-Zaehler fuer Analytics ("CV In"), getrennt vom reinen
cv_available-Anzeige-Flag: cv_available wurde beim Datenuebertrag pauschal
fuer 2481 Alt-Kandidaten gesetzt, ohne echtes Funnel-Ereignis - Analytics
zaehlte das faelschlich als "CV In" mit (Nutzer-Feedback 2026-07-15). Diese
Spalte bleibt fuer alle bestehenden Kandidaten NULL (bewusst kein Backfill)
und wird ab jetzt nur noch gesetzt, wenn cv_available echt (neu) auf True
wechselt (siehe CandidateService.update()).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f7c1e9d4b2"
down_revision: str | None = "d5f8e3a7b1c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidates", sa.Column("cv_in_recorded_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("candidates", "cv_in_recorded_at")
