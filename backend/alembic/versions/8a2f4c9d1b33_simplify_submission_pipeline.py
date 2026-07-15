"""simplify submission pipeline and extend vacancies

Revision ID: 8a2f4c9d1b33
Revises: 5c1c4f821b90
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8a2f4c9d1b33"
down_revision: str | None = "5c1c4f821b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TO_NEW_STATUS = {
    "draft": "qualification_call",
    "sent": "cv_out",
    "client_review": "cv_out",
    "feedback_pending": "cv_out",
    "interview_requested": "interview",
    "interview_scheduled": "interview",
    "offer_expected": "offer",
    "offer_received": "offer",
    "placed": "placement",
    "rejected": "cancelled",
    "withdrawn": "cancelled",
}


def upgrade() -> None:
    submissions = sa.table("candidate_submissions", sa.column("status", sa.String))
    for old_value, new_value in OLD_TO_NEW_STATUS.items():
        op.execute(
            submissions.update().where(submissions.c.status == old_value).values(status=new_value)
        )
    with op.batch_alter_table("candidate_submissions") as batch_op:
        batch_op.alter_column("client_company_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.add_column(sa.Column("cancellation_reason", sa.String(40), nullable=True))

    with op.batch_alter_table("job_mandates") as batch_op:
        batch_op.alter_column("client_company_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.add_column(
            sa.Column("priority", sa.String(16), nullable=False, server_default="normal")
        )
        batch_op.add_column(sa.Column("must_have", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("nice_to_have", sa.JSON(), nullable=True))

    job_mandates = sa.table(
        "job_mandates", sa.column("must_have", sa.JSON), sa.column("nice_to_have", sa.JSON)
    )
    op.execute(job_mandates.update().values(must_have=[], nice_to_have=[]))
    with op.batch_alter_table("job_mandates") as batch_op:
        batch_op.alter_column("must_have", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("nice_to_have", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("job_mandates") as batch_op:
        batch_op.drop_column("nice_to_have")
        batch_op.drop_column("must_have")
        batch_op.drop_column("priority")
        batch_op.alter_column("client_company_id", existing_type=sa.Uuid(), nullable=False)

    with op.batch_alter_table("candidate_submissions") as batch_op:
        batch_op.drop_column("cancellation_reason")
        batch_op.alter_column("client_company_id", existing_type=sa.Uuid(), nullable=False)

    submissions = sa.table("candidate_submissions", sa.column("status", sa.String))
    new_to_old = {
        "qualification_call": "draft",
        "cv_in": "draft",
        "cv_out": "sent",
        "interview": "interview_scheduled",
        "offer": "offer_received",
        "placement": "placed",
        "cancelled": "withdrawn",
    }
    for new_value, old_value in new_to_old.items():
        op.execute(
            submissions.update().where(submissions.c.status == new_value).values(status=old_value)
        )
