"""add login_challenges and trusted_devices tables (E-Mail-2FA)

Revision ID: 8f7054676265
Revises: eb8d7e148783
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8f7054676265"
down_revision: str | None = "eb8d7e148783"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_login_challenges_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_challenges")),
    )
    op.create_index(
        op.f("ix_login_challenges_user_id"), "login_challenges", ["user_id"]
    )

    op.create_table(
        "trusted_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_trusted_devices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trusted_devices")),
    )
    op.create_index(op.f("ix_trusted_devices_user_id"), "trusted_devices", ["user_id"])
    op.create_index(
        op.f("ix_trusted_devices_token_hash"), "trusted_devices", ["token_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trusted_devices_token_hash"), table_name="trusted_devices")
    op.drop_index(op.f("ix_trusted_devices_user_id"), table_name="trusted_devices")
    op.drop_table("trusted_devices")
    op.drop_index(op.f("ix_login_challenges_user_id"), table_name="login_challenges")
    op.drop_table("login_challenges")
