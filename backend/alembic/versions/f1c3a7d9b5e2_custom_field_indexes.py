"""Ausdrucks-Indizes fuer bestehende Eigene Felder (nur Postgres)

Revision ID: f1c3a7d9b5e2
Revises: e8b1c5d9f3a4
Create Date: 2026-10-04

Neue Felder bekommen ihren Index beim Anlegen (services/custom_field_indexes.py);
diese Migration holt ihn fuer die schon vorhandenen Felder nach. Auf SQLite ein
No-op. Die Indexe sind reine Beschleuniger, `downgrade` entfernt sie wieder.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from cc_crm.services.custom_field_indexes import ensure_index_on_connection, index_statement

revision: str = "f1c3a7d9b5e2"
down_revision: str | None = "e8b1c5d9f3a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _definitions() -> list[tuple[str, str, str]]:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT entity_type, key, field_type FROM custom_field_definitions")
    ).all()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return
    for entity_type, key, field_type in _definitions():
        ensure_index_on_connection(connection, entity_type, key, field_type)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return
    for entity_type, key, field_type in _definitions():
        statement = index_statement(entity_type, key, field_type)
        if statement is not None:
            op.execute(sa.text(f"DROP INDEX IF EXISTS {statement[0]}"))
