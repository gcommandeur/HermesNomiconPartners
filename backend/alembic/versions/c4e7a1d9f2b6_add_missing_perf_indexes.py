"""add missing performance indexes (candidates.last_contact_at, candidate_submissions.closing_probability)

Revision ID: c4e7a1d9f2b6
Revises: a8c2f5e9d6b3
Create Date: 2026-07-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4e7a1d9f2b6"
down_revision: str | None = "a8c2f5e9d6b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reaktivierungsliste filtert/sortiert nach last_contact_at.
    op.create_index("ix_candidates_last_contact_at", "candidates", ["last_contact_at"])
    # Prioritaetsansicht filtert nach "closing_probability IS NOT NULL".
    op.create_index(
        "ix_candidate_submissions_closing_probability",
        "candidate_submissions",
        ["closing_probability"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_submissions_closing_probability",
        table_name="candidate_submissions",
    )
    op.drop_index("ix_candidates_last_contact_at", table_name="candidates")
