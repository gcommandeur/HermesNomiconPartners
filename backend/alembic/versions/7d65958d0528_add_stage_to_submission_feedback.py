"""add stage to submission feedback

Revision ID: 7d65958d0528
Revises: ba19956d18e8
Create Date: 2026-07-22

Ergaenzt SubmissionFeedback.stage (welche Prozess-Stufe der Eintrag betrifft,
z.B. Pitch/Quali-Call/Shortlist/CV-Sent - siehe stage-edit-modal.tsx). Bewusst
nullable OHNE Backfill: bestehende Feedback-Eintraege vor dieser Migration
haben keine erfasste Stufe, NULL bedeutet hier "Stufe unbekannt/historisch".
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7d65958d0528"
down_revision: str | None = "ba19956d18e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("submission_feedback", sa.Column("stage", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("submission_feedback", "stage")
