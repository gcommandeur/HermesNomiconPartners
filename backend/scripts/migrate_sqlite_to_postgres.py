"""Kopiert alle Zeilen aus der bestehenden lokalen SQLite-Datenbank
(cc_crm_local.db) in eine Ziel-PostgreSQL-Datenbank - Tabelle fuer Tabelle in
Fremdschluessel-sicherer Reihenfolge.

Hintergrund: Umstellung von SQLite (lokale Entwicklung) auf managed
PostgreSQL fuer den produktiven Cloud-Betrieb (siehe docs/DEPLOYMENT.md).
Dieses Skript ist NUR der Datenumzug fuer den tatsaechlichen Wechsel, sobald
eine echte Ziel-Postgres-Instanz existiert - es veraendert NIE die
Quell-SQLite-Datei (nur lesender Zugriff) und muss VOR dem Lauf
`alembic upgrade head` gegen die Ziel-DB bereits durchgelaufen sein (das
Skript legt selbst keine Tabellen an, nur Zeilen).

Fremdschluessel-Reihenfolge: `Base.metadata.sorted_tables` liefert automatisch
eine topologisch nach Fremdschluessel-Abhaengigkeiten sortierte Tabellenliste
(z.B. client_companies vor contact_persons, candidates vor
candidate_submissions) - das haendisch zu pflegen waere fehleranfaellig
und wuerde bei jedem neuen Modell veralten.

Da ueber SQLAlchemy Core (nicht rohe sqlite3-Zeilen) gelesen wird, kommen
Werte bereits im richtigen Python-Typ an (uuid.UUID statt Hex-String, echte
datetime-Objekte, dekodierte JSON-Listen) - beim Schreiben gegen die
Postgres-Engine wandelt der Treiber sie automatisch in die jeweils native
Spaltenform (natives UUID, natives json, timestamptz).

Ausfuehren:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\migrate_sqlite_to_postgres.py \\
        --target-url postgresql+psycopg://user:pass@host:5432/dbname

    (Quelle ist per Default CC_CRM_DATABASE_URL / die lokale
    cc_crm_local.db; per --source-url ueberschreibbar.)

WICHTIG: Vor dem Lauf muss das Zielschema bereits existieren
(`CC_CRM_DATABASE_URL=<target-url> alembic upgrade head`) - dieses Skript
legt keine Tabellen an. Das Skript bricht ab, wenn eine Zieltabelle bereits
Zeilen enthaelt (--force zum Ueberschreiben dieser Sicherung), damit ein
versehentlicher zweiter Lauf keine Duplikate erzeugt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import Table, create_engine, func, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from cc_crm.core.config import get_settings  # noqa: E402
from cc_crm.models import Base  # noqa: E402  (populates Base.metadata with all tables)

CHUNK_SIZE = 1000


class MigrationError(Exception):
    pass


def ordered_tables() -> list[Table]:
    """Tabellen in Fremdschluessel-sicherer Reihenfolge (Eltern vor Kindern)."""
    return list(Base.metadata.sorted_tables)


def row_count(engine: Engine, table: Table) -> int:
    with engine.connect() as conn:
        return int(conn.execute(select(func.count()).select_from(table)).scalar_one())


def sanitize_dangling_fks(target: Engine, table: Table, rows: list[dict]) -> None:
    """Setzt Fremdschluessel-Werte auf NULL, die im Ziel (noch) nicht existieren.

    Die lokale Dev-Datenbank enthaelt bereits verwaiste Referenzen (z.B.
    `activities.candidate_submission_id`, die auf laengst geloeschte
    `candidate_submissions`-Zeilen zeigen - ein vorbestehendes Datenqualitaets-
    problem, siehe Cockpit-Task "Daten-Hygiene"). Ein striktes INSERT wuerde an
    diesen einzelnen Werten scheitern und die GESAMTE Zeile (und damit echte
    Historie) verlieren. Stattdessen wird nur der ungueltige FK-Wert genullt -
    nur fuer nullable Spalten; bei NOT NULL bleibt der Wert unveraendert und
    das INSERT scheitert wie bisher sichtbar, statt still falsche Daten zu
    erzeugen."""
    for col in table.columns:
        for fk in col.foreign_keys:
            if not col.nullable:
                continue
            parent_table = fk.column.table
            parent_col = fk.column.name
            with target.connect() as conn:
                valid_ids = {
                    row[0] for row in conn.execute(select(parent_table.c[parent_col]))
                }
            dangling = 0
            for row in rows:
                value = row.get(col.name)
                if value is not None and value not in valid_ids:
                    row[col.name] = None
                    dangling += 1
            if dangling:
                print(
                    f"    HINWEIS: {dangling}x {table.name}.{col.name} auf NULL gesetzt "
                    f"(verwaiste Referenz auf {parent_table.name} in der Quelle)."
                )


def copy_table(source: Engine, target: Engine, table: Table) -> tuple[int, int]:
    """Liest alle Zeilen aus `table` an der Quelle und schreibt sie in Chunks
    an das Ziel. Gibt (gelesene Zeilen, geschriebene Zeilen) zurueck."""
    with source.connect() as source_conn:
        rows = [dict(row._mapping) for row in source_conn.execute(select(table))]

    if not rows:
        return 0, 0

    sanitize_dangling_fks(target, table, rows)

    with target.begin() as target_conn:
        for start in range(0, len(rows), CHUNK_SIZE):
            chunk = rows[start : start + CHUNK_SIZE]
            # ON CONFLICT DO NOTHING statt striktem INSERT: macht den Lauf
            # sicher wiederholbar (bereits erfolgreich kopierte Tabellen aus
            # einem vorherigen Teil-Lauf werden nicht doppelt eingefuegt) und
            # ueberspringt einzelne Zeilen, die schon unabhaengig im Ziel
            # existieren (z.B. ein Admin-User, der direkt in Prod angelegt
            # wurde), ohne die restlichen Zeilen der Tabelle zu blockieren.
            stmt = pg_insert(table).values(chunk).on_conflict_do_nothing()
            target_conn.execute(stmt)

    return len(rows), len(rows)


def run_migration(
    source_url: str, target_url: str, *, force: bool, skip_tables: set[str] | None = None
) -> dict[str, tuple[int, int]]:
    if not source_url.startswith("sqlite"):
        raise MigrationError(
            f"Quelle ist keine SQLite-URL ({source_url!r}) - dieses Skript ist fuer den "
            "Umzug von der lokalen SQLite-Entwicklungsdatenbank gedacht."
        )
    if target_url.startswith("sqlite"):
        raise MigrationError(
            f"Ziel ist eine SQLite-URL ({target_url!r}) - erwartet wird eine PostgreSQL-URL "
            "(postgresql+psycopg://...)."
        )

    source_engine = create_engine(source_url)
    target_engine = create_engine(target_url)

    tables = ordered_tables()
    skip_tables = skip_tables or set()
    if skip_tables:
        tables = [t for t in tables if t.name not in skip_tables]

    if not force:
        already_populated = [t.name for t in tables if row_count(target_engine, t) > 0]
        if already_populated:
            raise MigrationError(
                "Ziel-Tabellen enthalten bereits Zeilen (Abbruch, um keine Duplikate zu "
                f"erzeugen): {', '.join(already_populated)}. Mit --force erzwingen, falls das "
                "gewollt ist (z.B. Zieltabellen wurden vorher bewusst geleert)."
            )

    results: dict[str, tuple[int, int]] = {}
    for table in tables:
        source_count = row_count(source_engine, table)
        _, written = copy_table(source_engine, target_engine, table)
        target_count = row_count(target_engine, table)
        results[table.name] = (source_count, target_count)
        status = "OK" if source_count == target_count else "ABWEICHUNG"
        print(f"  {table.name}: Quelle={source_count}, Ziel={target_count} [{status}]")

    return results


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-url",
        default=None,
        help="Quell-SQLite-URL (Default: CC_CRM_DATABASE_URL aus der Umgebung/.env).",
    )
    parser.add_argument(
        "--target-url",
        required=True,
        help="Ziel-PostgreSQL-URL (z.B. postgresql+psycopg://user:pass@host:5432/dbname).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Auch schreiben, wenn Zieltabellen bereits Zeilen enthalten.",
    )
    parser.add_argument(
        "--skip-tables",
        default="",
        help=(
            "Kommagetrennte Liste von Tabellennamen, die komplett uebersprungen werden "
            "(z.B. auth_sessions - reine Login-Token-Historie ohne Produktionswert, die "
            "verwaiste Fremdschluessel auf laengst geloeschte lokale Dev-User enthalten kann)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    source_url = args.source_url or get_settings().resolved_database_url

    print(f"Quelle: {source_url}")
    print(f"Ziel:   {args.target_url}")
    print("Kopiere Tabellen (Fremdschluessel-sichere Reihenfolge)...")

    skip_tables = {name.strip() for name in args.skip_tables.split(",") if name.strip()}

    try:
        results = run_migration(source_url, args.target_url, force=args.force, skip_tables=skip_tables)
    except MigrationError as exception:
        print(f"FEHLER: {exception}")
        raise SystemExit(1) from exception

    mismatches = [name for name, (src, tgt) in results.items() if src != tgt]
    if mismatches:
        print(f"\nWARNUNG: Abweichende Zeilenzahlen bei: {', '.join(mismatches)}")
        raise SystemExit(1)

    total = sum(src for src, _tgt in results.values())
    print(f"\nFertig - {total} Zeilen ueber {len(results)} Tabellen migriert.")


if __name__ == "__main__":
    main()
