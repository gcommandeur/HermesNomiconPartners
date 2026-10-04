"""add oauth_clients, oauth_authorizations, oauth_tokens (Hermes als OAuth-Anbieter fuer Claude)

Revision ID: c1f5a9b3d7e8
Revises: b0e4f8a2c6d7
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1f5a9b3d7e8"
down_revision: str | None = "b0e4f8a2c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(80), nullable=False),
        sa.Column("client_name", sa.String(120), nullable=False),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_clients")),
    )
    op.create_index(op.f("ix_oauth_clients_client_id"), "oauth_clients", ["client_id"], unique=True)

    op.create_table(
        "oauth_authorizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(80), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(200), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code_hash", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_authorizations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_authorizations")),
    )
    op.create_index(
        op.f("ix_oauth_authorizations_client_id"), "oauth_authorizations", ["client_id"]
    )
    op.create_index(
        op.f("ix_oauth_authorizations_code_hash"), "oauth_authorizations", ["code_hash"]
    )

    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(80), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=True),
        sa.Column("access_hash", sa.String(64), nullable=False),
        sa.Column("refresh_hash", sa.String(64), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["authorization_id"],
            ["oauth_authorizations.id"],
            name=op.f("fk_oauth_tokens_authorization_id_oauth_authorizations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_tokens")),
    )
    op.create_index(op.f("ix_oauth_tokens_user_id"), "oauth_tokens", ["user_id"])
    op.create_index(op.f("ix_oauth_tokens_authorization_id"), "oauth_tokens", ["authorization_id"])
    op.create_index(op.f("ix_oauth_tokens_access_hash"), "oauth_tokens", ["access_hash"], unique=True)
    op.create_index(
        op.f("ix_oauth_tokens_refresh_hash"), "oauth_tokens", ["refresh_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_table("oauth_tokens")
    op.drop_table("oauth_authorizations")
    op.drop_index(op.f("ix_oauth_clients_client_id"), table_name="oauth_clients")
    op.drop_table("oauth_clients")
