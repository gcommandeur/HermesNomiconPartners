"""add pg_trgm trigram indexes for candidate/client/contact text search (postgres only)

Revision ID: 7c1e651c4844
Revises: a3f7c1e9d4b2
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7c1e651c4844"
down_revision: str | None = "a3f7c1e9d4b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (index_name, table, column)
_TRIGRAM_INDEXES: list[tuple[str, str, str]] = [
    ("ix_trgm_candidates_first_name", "candidates", "first_name"),
    ("ix_trgm_candidates_last_name", "candidates", "last_name"),
    ("ix_trgm_candidates_email", "candidates", "email"),
    ("ix_trgm_candidates_job_title", "candidates", "job_title"),
    ("ix_trgm_client_companies_name", "client_companies", "name"),
    ("ix_trgm_client_companies_website", "client_companies", "website"),
    ("ix_trgm_client_companies_city", "client_companies", "city"),
    ("ix_trgm_contact_persons_first_name", "contact_persons", "first_name"),
    ("ix_trgm_contact_persons_last_name", "contact_persons", "last_name"),
    ("ix_trgm_contact_persons_email", "contact_persons", "email"),
]


def upgrade() -> None:
    # Trigram-Indizes/pg_trgm existieren nur unter Postgres - unter SQLite
    # (lokale Entwicklung) sauber ueberspringen statt mit einem SQL-Fehler
    # abzubrechen ("no such module: pg_trgm").
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for index_name, table, column in _TRIGRAM_INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} "
            f"USING GIN ({column} gin_trgm_ops)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for index_name, _table, _column in _TRIGRAM_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
