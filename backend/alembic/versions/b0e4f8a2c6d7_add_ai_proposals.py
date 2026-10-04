"""add ai_proposals (Claude-Vorschlaege mit Freigabe-Pflicht)

Revision ID: b0e4f8a2c6d7
Revises: a9d3e7b1c5f6
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b0e4f8a2c6d7"
down_revision: str | None = "a9d3e7b1c5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("result_entity_type", sa.String(20), nullable=True),
        sa.Column("result_entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_ai_proposals_created_by_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name=op.f("fk_ai_proposals_decided_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_proposals")),
    )
    op.create_index(op.f("ix_ai_proposals_status"), "ai_proposals", ["status"])
    op.create_index(
        op.f("ix_ai_proposals_created_by_user_id"), "ai_proposals", ["created_by_user_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_proposals_created_by_user_id"), table_name="ai_proposals")
    op.drop_index(op.f("ix_ai_proposals_status"), table_name="ai_proposals")
    op.drop_table("ai_proposals")
