"""add outreach sequences (Mehrkanal-Outreach-Sequenzen)

Revision ID: e3a6c9d2f5b8
Revises: d2f5a8b1c6e4
Create Date: 2026-10-03

Sequenzen (outreach_sequences), ihre Schritte (outreach_sequence_steps) und
Einschreibungen von Kandidaten (sequence_enrollments, hoechstens eine laufende
je Sequenz und Kandidat per partiellem Unique-Index).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e3a6c9d2f5b8"
down_revision: str | None = "d2f5a8b1c6e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "outreach_sequences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outreach_sequences")),
    )
    op.create_table(
        "outreach_sequence_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sequence_id", sa.Uuid(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("day_offset", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("subject", sa.String(240), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["sequence_id"],
            ["outreach_sequences.id"],
            name=op.f("fk_outreach_sequence_steps_sequence_id_outreach_sequences"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outreach_sequence_steps")),
        sa.UniqueConstraint(
            "sequence_id", "step_index", name=op.f("uq_outreach_sequence_steps_sequence_id")
        ),
    )
    op.create_index(
        op.f("ix_outreach_sequence_steps_sequence_id"), "outreach_sequence_steps", ["sequence_id"]
    )
    op.create_table(
        "sequence_enrollments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sequence_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("current_step_index", sa.Integer(), nullable=False),
        sa.Column("last_step_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stopped_reason", sa.String(240), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["sequence_id"],
            ["outreach_sequences.id"],
            name=op.f("fk_sequence_enrollments_sequence_id_outreach_sequences"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_sequence_enrollments_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_sequence_enrollments_owner_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sequence_enrollments")),
    )
    op.create_index(
        op.f("ix_sequence_enrollments_sequence_id"), "sequence_enrollments", ["sequence_id"]
    )
    op.create_index(
        op.f("ix_sequence_enrollments_candidate_id"), "sequence_enrollments", ["candidate_id"]
    )
    op.create_index(
        op.f("ix_sequence_enrollments_owner_user_id"), "sequence_enrollments", ["owner_user_id"]
    )
    op.create_index(op.f("ix_sequence_enrollments_status"), "sequence_enrollments", ["status"])
    op.create_index(
        "uq_sequence_enrollments_active",
        "sequence_enrollments",
        ["sequence_id", "candidate_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_sequence_enrollments_active", table_name="sequence_enrollments")
    op.drop_index(op.f("ix_sequence_enrollments_status"), table_name="sequence_enrollments")
    op.drop_index(op.f("ix_sequence_enrollments_owner_user_id"), table_name="sequence_enrollments")
    op.drop_index(op.f("ix_sequence_enrollments_candidate_id"), table_name="sequence_enrollments")
    op.drop_index(op.f("ix_sequence_enrollments_sequence_id"), table_name="sequence_enrollments")
    op.drop_table("sequence_enrollments")
    op.drop_index(
        op.f("ix_outreach_sequence_steps_sequence_id"), table_name="outreach_sequence_steps"
    )
    op.drop_table("outreach_sequence_steps")
    op.drop_table("outreach_sequences")
