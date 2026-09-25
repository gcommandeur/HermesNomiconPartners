"""add deletion_requests table and activities.sent_by_user_id

Revision ID: 4d36125199ca
Revises: 8f7054676265
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "4d36125199ca"
down_revision: str | None = "8f7054676265"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch_alter_table fuer die FK-Constraint (SQLite kann sie nicht per
    # plain ALTER TABLE nachtraeglich hinzufuegen, siehe bereits bestehende
    # Migration ba19956d18e8 fuer dasselbe Muster).
    with op.batch_alter_table("activities") as batch_op:
        batch_op.add_column(sa.Column("sent_by_user_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_activities_sent_by_user_id_users"),
            "users",
            ["sent_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            op.f("ix_activities_sent_by_user_id"), ["sent_by_user_id"]
        )

    op.create_table(
        "deletion_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_via", sa.String(length=240), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_deletion_requests_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"],
            ["users.id"],
            name=op.f("fk_deletion_requests_completed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deletion_requests")),
    )
    op.create_index(
        op.f("ix_deletion_requests_candidate_id"), "deletion_requests", ["candidate_id"]
    )
    op.create_index(
        op.f("ix_deletion_requests_deadline"), "deletion_requests", ["deadline"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_deletion_requests_deadline"), table_name="deletion_requests")
    op.drop_index(op.f("ix_deletion_requests_candidate_id"), table_name="deletion_requests")
    op.drop_table("deletion_requests")

    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_index(op.f("ix_activities_sent_by_user_id"))
        batch_op.drop_constraint(
            op.f("fk_activities_sent_by_user_id_users"), type_="foreignkey"
        )
        batch_op.drop_column("sent_by_user_id")
