"""candidates.search_text (normalisierter Suchtext) + Trigram-Index (nur Postgres)

Revision ID: a1c5e9b3d7f2
Revises: f4b7d1a8c2e5
Create Date: 2026-10-03

Die Freitextsuche (repositories/candidates.py) faltete bisher bei JEDER Anfrage
neun Textspalten und drei JSON-Spalten mit je 16 verschachtelten replace()-Aufrufen,
und kein Index konnte genutzt werden - bei 50.000 Kandidaten p95 ca. 1,3 s
(docs/PERFORMANCE.md). Jetzt: eine gespeicherte, generierte Spalte `search_text`
mit demselben normalisierten Text (lower + Umlaut-Faltung, Bindestrich/Punkt
entfernt), Felder durch chr(31) getrennt, plus GIN-Trigram-Index - `LIKE '%wort%'`
nutzt ihn und behaelt die Teilwort-Semantik ("Buchhaltung" findet
"Finanzbuchhaltung"). Zusaetzlich Trigram-Indizes fuer Stadt/PLZ (Regionsfilter).

Die Normalisierung ist hier EINGEFROREN kopiert (Migrationen duerfen sich nicht mit
dem App-Code mitaendern); sie muss identisch zu
repositories/candidates.py::_NORMALIZE_REPLACEMENTS bleiben - ein Test
(tests/api/test_candidates_search_text.py) prueft das. Nur Postgres; unter SQLite
bleibt die bisherige Mehrspalten-Suche.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1c5e9b3d7f2"
down_revision: str | None = "f4b7d1a8c2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TEXT_COLUMNS = (
    "first_name",
    "last_name",
    "email",
    "job_title",
    "candidate_number",
    "qualification",
    "ausbildung_titel",
    "current_employer_internal",
    "summary",
)
_JSON_COLUMNS = ("fachliche_schwerpunkte", "edv_kenntnisse", "berufliche_stationen")
_REPLACEMENTS = (
    ("ä", "ae"),
    ("ö", "oe"),
    ("ü", "ue"),
    ("ß", "ss"),
    ("Ä", "ae"),
    ("Ö", "oe"),
    ("Ü", "ue"),
    ("\\u00e4", "ae"),
    ("\\u00c4", "ae"),
    ("\\u00f6", "oe"),
    ("\\u00d6", "oe"),
    ("\\u00fc", "ue"),
    ("\\u00dc", "ue"),
    ("\\u00df", "ss"),
    ("-", ""),
    (".", ""),
)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _search_text_expression() -> str:
    parts = [f"coalesce({column}, '')" for column in _TEXT_COLUMNS]
    parts += [f"coalesce(cast({column} as text), '')" for column in _JSON_COLUMNS]
    expression = "lower(" + " || chr(31) || ".join(parts) + ")"
    for old, new in _REPLACEMENTS:
        expression = f"replace({expression}, {_literal(old)}, {_literal(new)})"
    return expression


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "ALTER TABLE candidates ADD COLUMN search_text text "
        f"GENERATED ALWAYS AS ({_search_text_expression()}) STORED"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trgm_candidates_search_text "
        "ON candidates USING GIN (search_text gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trgm_candidates_city "
        "ON candidates USING GIN (city gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trgm_candidates_postal_code "
        "ON candidates USING GIN (postal_code gin_trgm_ops)"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_trgm_candidates_postal_code")
    op.execute("DROP INDEX IF EXISTS ix_trgm_candidates_city")
    op.execute("DROP INDEX IF EXISTS ix_trgm_candidates_search_text")
    op.execute("ALTER TABLE candidates DROP COLUMN IF EXISTS search_text")
