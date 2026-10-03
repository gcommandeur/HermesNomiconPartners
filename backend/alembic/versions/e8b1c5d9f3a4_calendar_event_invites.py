"""calendar_events: Einladung (Teilnehmer, Teams-Link, Antwort)

Revision ID: e8b1c5d9f3a4
Revises: d7a0b4c8e2f3
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8b1c5d9f3a4"
down_revision: str | None = "d7a0b4c8e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("calendar_events", sa.Column("attendee_email", sa.String(320), nullable=True))
    op.add_column("calendar_events", sa.Column("attendee_name", sa.String(240), nullable=True))
    op.add_column("calendar_events", sa.Column("invite_message", sa.Text(), nullable=True))
    op.add_column(
        "calendar_events",
        sa.Column("online_meeting", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "calendar_events", sa.Column("online_meeting_url", sa.String(1000), nullable=True)
    )
    op.add_column("calendar_events", sa.Column("attendee_response", sa.String(20), nullable=True))


def downgrade() -> None:
    for column in (
        "attendee_response",
        "online_meeting_url",
        "online_meeting",
        "invite_message",
        "attendee_name",
        "attendee_email",
    ):
        op.drop_column("calendar_events", column)
