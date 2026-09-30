"""add approval_requests table and client_companies.approval_pending

Revision ID: a7d3e91c5b20
Revises: ec31119ae3be
Create Date: 2026-09-30

Task #200 Teil 2 (Freigabe-Inbox): Nicht-Admins legen fuer neue Kanzleien,
Honorar-Aenderungen und das Stellen einer Rechnung eine Freigabe-Anfrage an,
die ein Admin/GF genehmigt oder ablehnt (siehe services/approvals.py).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7d3e91c5b20"
down_revision: str | None = "ec31119ae3be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_by", sa.String(length=320), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("old_values", sa.JSON(), nullable=True),
        sa.Column("proposed_values", sa.JSON(), nullable=True),
        sa.Column("decided_by", sa.String(length=320), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_requests")),
    )
    op.create_index(
        op.f("ix_approval_requests_entity_type"), "approval_requests", ["entity_type"]
    )
    op.create_index(op.f("ix_approval_requests_entity_id"), "approval_requests", ["entity_id"])
    op.create_index(op.f("ix_approval_requests_status"), "approval_requests", ["status"])

    with op.batch_alter_table("client_companies") as batch_op:
        batch_op.add_column(
            sa.Column(
                "approval_pending", sa.Boolean(), server_default=sa.false(), nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("client_companies") as batch_op:
        batch_op.drop_column("approval_pending")
    op.drop_index(op.f("ix_approval_requests_status"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_entity_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_entity_type"), table_name="approval_requests")
    op.drop_table("approval_requests")
