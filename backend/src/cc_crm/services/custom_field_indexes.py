"""Postgres-Ausdrucks-Indizes fuer Eigene Felder.

Die Werte liegen in einer plain-JSON-Spalte (`custom_fields`), ein GIN-Index ist
dort nicht moeglich. Stattdessen bekommt jedes Feld beim Anlegen einen Index auf
genau den Ausdruck, den der Listen-Filter erzeugt (`->> 'schluessel'`, beim
Zahl-/Ja-Nein-Feld mit CAST wie `as_float()`/`as_boolean()` in SQLAlchemy). Ohne
Index ist der Filter bei 50.000+ Datensaetzen ein Tabellen-Scan.

Nur auf Postgres; SQLite (lokal/Tests) braucht und kennt das nicht. Der
Schluessel ist per Regex (`^[a-z][a-z0-9_]{0,59}$`) abgesichert und wird
deshalb inline in das DDL geschrieben (DDL kennt keine Bind-Parameter).
"""

import hashlib
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

TABLES = {
    "candidate": "candidates",
    "client": "client_companies",
    "contact": "contact_persons",
}
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,59}$")


def index_statement(entity_type: str, key: str, field_type: str) -> tuple[str, str] | None:
    """(Indexname, CREATE-INDEX-Statement) oder None bei unbekanntem Objekttyp
    bzw. ungueltigem Schluessel."""
    table = TABLES.get(entity_type)
    if table is None or not _KEY_RE.match(key):
        return None
    # Postgres kuerzt Namen ab 63 Zeichen - ein Hash haelt ihn eindeutig und kurz.
    name = "ix_cf_" + hashlib.sha1(f"{entity_type}:{key}".encode()).hexdigest()[:20]
    base = f"custom_fields ->> '{key}'"
    if field_type == "number":
        expression = f"CAST({base} AS FLOAT)"
    elif field_type == "boolean":
        expression = f"CAST({base} AS BOOLEAN)"
    else:
        expression = base
    return name, f"CREATE INDEX IF NOT EXISTS {name} ON {table} (({expression}))"


def ensure_index(session: Session, entity_type: str, key: str, field_type: str) -> bool:
    """Legt den Index an (nur Postgres). True, wenn ein Statement lief."""
    statement = index_statement(entity_type, key, field_type)
    if statement is None or session.get_bind().dialect.name != "postgresql":
        return False
    session.execute(text(statement[1]))
    session.commit()
    return True


def ensure_index_on_connection(
    connection: Connection, entity_type: str, key: str, field_type: str
) -> bool:
    """Wie ensure_index, fuer Migrationen (laufen ueber eine Connection)."""
    statement = index_statement(entity_type, key, field_type)
    if statement is None or connection.dialect.name != "postgresql":
        return False
    connection.execute(text(statement[1]))
    return True
