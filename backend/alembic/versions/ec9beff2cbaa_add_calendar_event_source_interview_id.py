"""add calendar_events.source_interview_id (back-reference for auto-created interview calendar events)

Revision ID: ec9beff2cbaa
Revises: e66a4b772186
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ec9beff2cbaa"
down_revision: str | None = "e66a4b772186"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite kann eine Fremdschluessel-Constraint nicht per plain ALTER TABLE
    # nachtraeglich hinzufuegen - batch_alter_table umgeht das (auf Postgres
    # ein direktes ALTER TABLE, siehe bereits bestehende Migration
    # 8a2f4c9d1b33 fuer dasselbe Muster).
    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.add_column(sa.Column("source_interview_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_calendar_events_source_interview_id_interviews",
            "interviews",
            ["source_interview_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            "ix_calendar_events_source_interview_id", ["source_interview_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("calendar_events") as batch_op:
        batch_op.drop_index("ix_calendar_events_source_interview_id")
        batch_op.drop_constraint(
            "fk_calendar_events_source_interview_id_interviews", type_="foreignkey"
        )
        batch_op.drop_column("source_interview_id")
