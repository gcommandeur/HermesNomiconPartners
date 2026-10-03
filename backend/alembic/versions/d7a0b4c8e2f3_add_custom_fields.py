"""add custom_field_definitions and custom_fields JSON columns

Revision ID: d7a0b4c8e2f3
Revises: c6e9f3b7d1a2
Create Date: 2026-10-03

Eigene Felder: Definitionen (Admin) und je eine JSON-Spalte `custom_fields` an
candidates, client_companies und contact_persons.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7a0b4c8e2f3"
down_revision: str | None = "c6e9f3b7d1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("candidates", "client_companies", "contact_persons")


def upgrade() -> None:
    op.create_table(
        "custom_field_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("field_type", sa.String(20), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_field_definitions")),
        sa.UniqueConstraint("entity_type", "key", name="uq_custom_field_entity_key"),
    )
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("custom_fields", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        )


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_column(table, "custom_fields")
    op.drop_table("custom_field_definitions")
