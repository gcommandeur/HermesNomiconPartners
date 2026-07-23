"""remove pitch submission status (Phase 5a - pipeline starts at Quali Call)

Revision ID: c4d7e1a9f3b2
Revises: b2c5d8e1f4a7
Create Date: 2026-07-23

Migrates existing rows with the removed "pitch" value to
"qualification_call" (the next step). SubmissionStatus/Enum columns here use
native_enum=False (plain VARCHAR), so no column type/CHECK-constraint change
is needed - this is a pure data migration.

IMPORTANT: SQLAlchemy's Enum(..., native_enum=False) stores the Python enum
MEMBER NAME ("PITCH"), not its .value ("pitch") - confirmed by inspecting
the actual column contents. The WHERE clauses below therefore compare
against "PITCH", not "pitch".
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d7e1a9f3b2"
down_revision: str | None = "b2c5d8e1f4a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE candidate_submissions SET status = 'QUALIFICATION_CALL' "
            "WHERE status = 'PITCH'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE submission_feedback SET stage = 'QUALIFICATION_CALL' "
            "WHERE stage = 'PITCH'"
        )
    )


def downgrade() -> None:
    # Nicht reversibel: welche Zeilen urspruenglich "pitch" waren, ist nach
    # dem Upgrade nicht mehr unterscheidbar von echten qualification_call-
    # Eintraegen - kein Daten-Downgrade moeglich.
    pass
