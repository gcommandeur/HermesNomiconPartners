"""add users.role and users.calendar_feed_token (calendar feature prep)

Revision ID: 2840ce14c934
Revises: 7c1e651c4844
Create Date: 2026-07-16
"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import orm

from alembic import op

revision: str = "2840ce14c934"
down_revision: str | None = "7c1e651c4844"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=20), nullable=False, server_default="member"),
    )
    # calendar_feed_token muss PRO ZEILE eindeutig sein - ein server_default
    # wuerde derselbe Wert fuer alle bestehenden Nutzer sein. Deshalb erst
    # nullable anlegen, je Zeile individuell befuellen, dann erst NOT NULL +
    # UNIQUE erzwingen.
    op.add_column("users", sa.Column("calendar_feed_token", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    session = orm.Session(bind=bind)
    users_table = sa.table(
        "users", sa.column("id", sa.Uuid()), sa.column("calendar_feed_token", sa.String())
    )
    user_ids = session.execute(sa.select(users_table.c.id)).scalars().all()
    for user_id in user_ids:
        session.execute(
            users_table.update()
            .where(users_table.c.id == user_id)
            .values(calendar_feed_token=secrets.token_urlsafe(32))
        )
    session.commit()

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("calendar_feed_token", existing_type=sa.String(length=64), nullable=False)
    op.create_index(
        "ix_users_calendar_feed_token", "users", ["calendar_feed_token"], unique=True
    )

    # info@commandeurconsulting.de ist der Admin-Account dieses Projekts
    # (Nutzer-Vorgabe) - existiert der Login zum Zeitpunkt der Migration noch
    # nicht, ist das kein Fehler (z.B. leere Test-DB), einfach nichts zu tun.
    op.execute(
        "UPDATE users SET role = 'admin' WHERE email = 'info@commandeurconsulting.de'"
    )


def downgrade() -> None:
    op.drop_index("ix_users_calendar_feed_token", table_name="users")
    op.drop_column("users", "calendar_feed_token")
    op.drop_column("users", "role")
