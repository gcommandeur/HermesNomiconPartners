"""add rate_limit_attempts table (DB-gestuetztes Rate-Limiting)

Revision ID: 7474f6037383
Revises: 4d36125199ca
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7474f6037383"
down_revision: str | None = "4d36125199ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_limit_attempts")),
    )
    op.create_index(
        op.f("ix_rate_limit_attempts_scope"), "rate_limit_attempts", ["scope"]
    )
    op.create_index(
        op.f("ix_rate_limit_attempts_key"), "rate_limit_attempts", ["key"]
    )
    op.create_index(
        op.f("ix_rate_limit_attempts_created_at"), "rate_limit_attempts", ["created_at"]
    )
    op.create_index(
        "ix_rate_limit_attempts_scope_key_created_at",
        "rate_limit_attempts",
        ["scope", "key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_rate_limit_attempts_scope_key_created_at", table_name="rate_limit_attempts")
    op.drop_index(op.f("ix_rate_limit_attempts_created_at"), table_name="rate_limit_attempts")
    op.drop_index(op.f("ix_rate_limit_attempts_key"), table_name="rate_limit_attempts")
    op.drop_index(op.f("ix_rate_limit_attempts_scope"), table_name="rate_limit_attempts")
    op.drop_table("rate_limit_attempts")
