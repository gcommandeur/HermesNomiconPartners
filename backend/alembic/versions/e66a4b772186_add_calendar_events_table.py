"""add calendar_events table (interviews, quali-calls, sonstige Termine mit Outlook-ICS-Sync)

Revision ID: e66a4b772186
Revises: 2840ce14c934
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e66a4b772186"
down_revision: str | None = "2840ce14c934"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "INTERVIEW",
                "QUALI_CALL",
                "OTHER",
                name="calendareventtype",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=240), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("client_company_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_submission_id", sa.Uuid(), nullable=True),
        sa.Column(
            "reminder_minutes_before", sa.Integer(), nullable=False, server_default="30"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_calendar_events_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_calendar_events_created_by_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_calendar_events_candidate_id_candidates"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["client_company_id"],
            ["client_companies.id"],
            name=op.f("fk_calendar_events_client_company_id_client_companies"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_submission_id"],
            ["candidate_submissions.id"],
            name=op.f(
                "fk_calendar_events_candidate_submission_id_candidate_submissions"
            ),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calendar_events")),
    )
    op.create_index(
        op.f("ix_calendar_events_owner_user_id"), "calendar_events", ["owner_user_id"]
    )
    op.create_index(op.f("ix_calendar_events_start_at"), "calendar_events", ["start_at"])
    op.create_index(op.f("ix_calendar_events_event_type"), "calendar_events", ["event_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_calendar_events_event_type"), table_name="calendar_events")
    op.drop_index(op.f("ix_calendar_events_start_at"), table_name="calendar_events")
    op.drop_index(op.f("ix_calendar_events_owner_user_id"), table_name="calendar_events")
    op.drop_table("calendar_events")
