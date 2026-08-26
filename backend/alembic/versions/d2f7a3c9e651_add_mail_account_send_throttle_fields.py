"""add mail_accounts send_throttle_seconds/daily_send_limit

Revision ID: d2f7a3c9e651
Revises: c1a9d5e7f402
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2f7a3c9e651"
down_revision: str | None = "c1a9d5e7f402"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mail_accounts",
        sa.Column("send_throttle_seconds", sa.Integer(), nullable=False, server_default="8"),
    )
    op.add_column(
        "mail_accounts",
        sa.Column("daily_send_limit", sa.Integer(), nullable=False, server_default="150"),
    )


def downgrade() -> None:
    op.drop_column("mail_accounts", "daily_send_limit")
    op.drop_column("mail_accounts", "send_throttle_seconds")
