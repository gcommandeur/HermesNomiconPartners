"""add background_jobs (Job-Warteschlange in Postgres)

Revision ID: b5d8e2a6c9f1
Revises: a1c5e9b3d7f2
Create Date: 2026-10-03

Eigene kleine Tabelle fuer Hintergrundjobs (Sourcing-Laeufe, CV-Scan,
Sicherheitsalarme): Status, Versuche, run_after, locked_until, letzter Fehler.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5d8e2a6c9f1"
down_revision: str | None = "a1c5e9b3d7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_blob", sa.LargeBinary(), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "run_after", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_background_jobs")),
    )
    op.create_index(op.f("ix_background_jobs_kind"), "background_jobs", ["kind"])
    op.create_index(
        "ix_background_jobs_status_run_after", "background_jobs", ["status", "run_after"]
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_status_run_after", table_name="background_jobs")
    op.drop_index(op.f("ix_background_jobs_kind"), table_name="background_jobs")
    op.drop_table("background_jobs")
