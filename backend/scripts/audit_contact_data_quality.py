"""Listet ContactPerson-Datensaetze mit auffaelligen Namen/Feldern zur
manuellen Durchsicht auf.

Anders als bei den frueheren rein syntaktischen Bereinigungen in diesem
Projekt (z.B. Kanzlei-Dubletten-Merge in services/name_matching.py) wird
hier NICHTS automatisch veraendert: um zu entscheiden, welcher Name
tatsaechlich korrekt ist, braucht es echtes Wissen ueber den Kontakt, das
dieses Skript nicht hat. Es liefert nur die Liste als Ausgangspunkt fuer
eine manuelle Durchsicht.

Erkannte Auffaelligkeiten je Kontakt:
- Name enthaelt Ziffern
- Name enthaelt ungewoehnliche Sonderzeichen
- moeglicher zusammengeschriebener Name (camelCase-Muster, z.B.
  "MaxMustermann" statt "Max Mustermann" - gleiches Problem wie bei den
  frueher bereinigten Kandidatennamen, siehe scripts/sync_names_20260711.py)
- Name sieht wie eine E-Mail-Adresse aus
- Name sieht wie ein Firmenname aus (Rechtsform-/Kanzlei-Suffixe)
- auffaellig kurzer Vor-/Nachname (1 Zeichen)
- Vor-/Nachname leer oder nur Leerzeichen
- E-Mail-Feld gesetzt, aber ohne "@" (offensichtlich ungueltig)

Laeuft standardmaessig gegen die lokale DB aus CC_CRM_DATABASE_URL (.env).
Fuer Produktion (Managed PostgreSQL, seit dem Go-Live 2026-07-20 von der
lokalen SQLite-Dev-DB getrennter Datenbestand) --database-url mit der
echten Postgres-Connection-URL uebergeben, analog zu
cleanup_stale_followup_tasks.py --database-url. Dafuer vorab die eigene
IPv4 temporaer als Trusted Source am DB-Cluster hinterlegen (siehe
docs/DEPLOYMENT.md, Abschnitt "Datenbank") - ODER direkt ueber die
DigitalOcean-App-Platform-Console ausfuehren (dort ohne --database-url,
die dortige CC_CRM_DATABASE_URL zeigt schon auf Produktion).

Usage (aus backend/, mit aktiviertem venv):

    python scripts/audit_contact_data_quality.py
    python scripts/audit_contact_data_quality.py --format markdown
    python scripts/audit_contact_data_quality.py --format csv --output contacts_review.csv
    python scripts/audit_contact_data_quality.py --database-url postgresql+psycopg://...
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402


def _redact_url(database_url: str) -> str:
    """Passwort in einer Connection-URL fuer Logs/Print-Ausgaben maskieren -
    Produktions-Zugangsdaten sollen unter keinen Umstaenden in Terminal-
    Output oder Skript-Logs landen (gleiches Muster wie
    cleanup_stale_followup_tasks.py::_redact_url)."""
    if "@" not in database_url or "://" not in database_url:
        return database_url
    scheme, rest = database_url.split("://", 1)
    credentials, host_part = rest.split("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host_part}"

_DIGIT_RE = re.compile(r"\d")
# Erlaubt Buchstaben (inkl. deutscher/franzoesischer Diakritika), Leerzeichen,
# Punkt, Bindestrich, Apostroph - alles andere gilt als ungewoehnlich fuer
# einen Personennamen.
_SPECIAL_CHAR_RE = re.compile(r"[^a-zA-ZäöüÄÖÜßéèêàáçÉÈÊÀÁÇ\s.\-']")
# Kleinbuchstabe direkt gefolgt von Grossbuchstabe innerhalb EINES Wortes -
# typisches Muster fuer einen ohne Leerzeichen zusammengeschriebenen
# Doppelnamen (z.B. "AlenaDracke" statt "Alena Dracke", siehe frueherer
# Kandidaten-Namensabgleich in scripts/sync_names_20260711.py).
_CAMEL_SMASH_RE = re.compile(r"[a-zäöüß][A-ZÄÖÜ]")
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(gmbh|mbh|ag|kgaa|kg|ohg|gbr|kanzlei|steuerberatung|treuhand|partner|"
    r"rechtsanwälte|rechtsanwalt|steuerberater(in)?|wirtschaftsprüfer(in)?)\b",
    re.IGNORECASE,
)

COLUMNS = [
    "id",
    "client_company",
    "first_name",
    "last_name",
    "role_title",
    "email",
    "phone",
    "reasons",
]


def _reasons_for(first_name: str, last_name: str, email: str | None) -> list[str]:
    reasons: list[str] = []
    full_name = f"{first_name} {last_name}"

    if not first_name.strip() or not last_name.strip():
        reasons.append("Vor-/Nachname leer oder nur Leerzeichen")
        return reasons

    if _DIGIT_RE.search(full_name):
        reasons.append("Name enthält Ziffern")
    if _SPECIAL_CHAR_RE.search(full_name):
        reasons.append("Name enthält ungewöhnliche Sonderzeichen")
    if _CAMEL_SMASH_RE.search(first_name) or _CAMEL_SMASH_RE.search(last_name):
        reasons.append("Möglicher zusammengeschriebener Name (camelCase-Muster)")
    if "@" in full_name:
        reasons.append("Name sieht wie eine E-Mail-Adresse aus")
    if _COMPANY_SUFFIX_RE.search(full_name):
        reasons.append("Name sieht wie ein Firmenname aus")
    if len(first_name.strip()) <= 1 or len(last_name.strip()) <= 1:
        reasons.append("Auffällig kurzer Vor-/Nachname (1 Zeichen)")
    if email and "@" not in email:
        reasons.append("E-Mail-Feld sieht nicht wie eine gültige Adresse aus")

    return reasons


def audit(session_factory: sessionmaker[Session] | None = None) -> list[dict[str, str]]:
    factory = session_factory or SessionLocal
    with factory() as session:
        contacts = session.scalars(select(ContactPerson)).all()
        client_names: dict[uuid.UUID, str] = dict(
            session.execute(select(ClientCompany.id, ClientCompany.name)).all()  # type: ignore[arg-type]
        )

    rows: list[dict[str, str]] = []
    for contact in contacts:
        reasons = _reasons_for(contact.first_name, contact.last_name, contact.email)
        if not reasons:
            continue
        rows.append(
            {
                "id": str(contact.id),
                "client_company": client_names.get(contact.client_company_id, "?"),
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "role_title": contact.role_title or "",
                "email": contact.email or "",
                "phone": contact.phone or "",
                "reasons": "; ".join(reasons),
            }
        )
    return rows


def render_csv(rows: list[dict[str, str]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def render_markdown(rows: list[dict[str, str]]) -> str:
    header = "| " + " | ".join(COLUMNS) + " |"
    separator = "| " + " | ".join("---" for _ in COLUMNS) + " |"
    lines = [header, separator]
    for row in rows:
        cells = (row[column].replace("|", "\\|") for column in COLUMNS)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["csv", "markdown"], default="csv")
    parser.add_argument("--output", type=Path, default=None, help="Datei statt stdout")
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Optionale Ziel-DB (z.B. Produktions-Postgres statt lokaler "
            "CC_CRM_DATABASE_URL) - siehe Docstring oben."
        ),
    )
    args = parser.parse_args()

    session_factory = None
    if args.database_url:
        engine = create_engine(args.database_url)
        session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        print(f"Ziel-DB: {_redact_url(args.database_url)}", file=sys.stderr)

    rows = audit(session_factory)
    rendered = render_csv(rows) if args.format == "csv" else render_markdown(rows)

    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
        print(f"{len(rows)} auffällige Kontakte -> {args.output}")
    else:
        print(rendered)
        print(f"\n{len(rows)} auffällige Kontakte zur manuellen Durchsicht.", file=sys.stderr)


if __name__ == "__main__":
    main()
