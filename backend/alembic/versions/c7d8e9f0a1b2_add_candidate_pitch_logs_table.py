"""add candidate_pitch_logs table (Pitch/InMail als zaehlbares Ereignis, keine Kanban-Stufe)

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_pitch_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes_text", sa.Text(), nullable=True),
        sa.Column("next_step", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_candidate_pitch_logs_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_pitch_logs")),
    )
    op.create_index(
        op.f("ix_candidate_pitch_logs_candidate_id"), "candidate_pitch_logs", ["candidate_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_candidate_pitch_logs_candidate_id"), table_name="candidate_pitch_logs")
    op.drop_table("candidate_pitch_logs")
