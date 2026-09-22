"""add cv_extraction_jobs table (Hintergrundauswertung gescannter CVs)

Revision ID: eb8d7e148783
Revises: a86368ef29ba
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "eb8d7e148783"
down_revision: str | None = "a86368ef29ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cv_extraction_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PROCESSING",
                "DONE",
                "FAILED",
                name="cvextractionjobstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_cv_extraction_jobs_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cv_extraction_jobs")),
    )
    op.create_index(
        op.f("ix_cv_extraction_jobs_owner_user_id"), "cv_extraction_jobs", ["owner_user_id"]
    )
    op.create_index(op.f("ix_cv_extraction_jobs_status"), "cv_extraction_jobs", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_cv_extraction_jobs_status"), table_name="cv_extraction_jobs")
    op.drop_index(op.f("ix_cv_extraction_jobs_owner_user_id"), table_name="cv_extraction_jobs")
    op.drop_table("cv_extraction_jobs")
