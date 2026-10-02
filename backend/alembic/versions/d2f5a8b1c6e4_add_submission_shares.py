"""add submission_shares (Prozess-Sharing)

Revision ID: d2f5a8b1c6e4
Revises: c9a1d4e7f2b3
Create Date: 2026-10-02

Einzelne Prozesse gezielt mit Kollegen teilen (Vertretung, Vier-Augen-
Pruefung). Eine Zeile = voller Zugriff der Person auf den Prozess.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2f5a8b1c6e4"
down_revision: str | None = "c9a1d4e7f2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "submission_shares",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("shared_with_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["candidate_submissions.id"],
            name=op.f("fk_submission_shares_submission_id_candidate_submissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shared_with_user_id"],
            ["users.id"],
            name=op.f("fk_submission_shares_shared_with_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_submission_shares_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_submission_shares")),
        sa.UniqueConstraint(
            "submission_id", "shared_with_user_id", name=op.f("uq_submission_shares_submission_id")
        ),
    )
    op.create_index(
        op.f("ix_submission_shares_submission_id"), "submission_shares", ["submission_id"]
    )
    op.create_index(
        op.f("ix_submission_shares_shared_with_user_id"),
        "submission_shares",
        ["shared_with_user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_submission_shares_shared_with_user_id"), table_name="submission_shares")
    op.drop_index(op.f("ix_submission_shares_submission_id"), table_name="submission_shares")
    op.drop_table("submission_shares")
