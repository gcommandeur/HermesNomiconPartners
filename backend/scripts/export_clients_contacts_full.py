"""Vollstaendiger Export ALLER Kanzleien (ClientCompany) und Kontakte
(ContactPerson) aus der Datenbank als zwei CSV-Dateien - keine Pagination,
keine Limitierung (Nutzer-Vorgabe: "wirklich ALLE Zeilen").

Schreibt die CSVs lokal (im Container, wenn in der Produktions-Console
ausgefuehrt) und laedt sie zusaetzlich in den S3-Bucket unter dem Praefix
_diagnostics/ hoch - reiner Transportweg, damit die Dateien von dort auf den
lokalen Rechner geholt werden koennen (gleiches Muster wie schon beim
S3-Endpoint-Debugging genutzt). Die Objekte im Bucket sind KEIN dauerhafter
Speicherort und sollten nach dem Download wieder geloescht werden.

Usage (aus backend/, mit aktiviertem venv, in der Produktions-Console):

    python scripts/export_clients_contacts_full.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.core.config import get_settings  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402
from cc_crm.services.storage import _s3_client, _s3_configured  # noqa: E402

OUTPUT_DIR = Path("/tmp/cc_crm_export")
CLIENTS_FILENAME = "kanzleien_full_export_20260730.csv"
CONTACTS_FILENAME = "kontakte_full_export_20260730.csv"
S3_PREFIX = "_diagnostics"

CLIENT_FIELDS = [
    "id",
    "name",
    "kanzleigruppe",
    "status",
    "website",
    "email",
    "phone",
    "street",
    "postal_code",
    "city",
    "region",
    "company_size",
    "focus",
    "linkedin_url",
    "last_contact_at",
    "next_follow_up_at",
    "terms_status",
    "fee_percentage",
    "honorar_stufe",
    "nachlass_begruendung",
    "agb_version",
    "refund_terms",
    "guarantee_period_months",
    "payment_terms_days",
    "special_terms",
    "commercial_notes",
    "notes",
    "owner_user_id",
    "created_at",
    "updated_at",
]

# Deutsche Anzeigenamen fuer die vom Nutzer explizit genannten Kernfelder -
# alle uebrigen Modellfelder behalten ihren technischen Namen als Header.
CONTACT_HEADER_OVERRIDES = {
    "id": "id",
    "first_name": "vorname",
    "last_name": "nachname",
    "email": "email",
    "phone": "telefon",
    "role_title": "rolle",
    "client_company_id": "kanzlei_id",
}
CONTACT_FIELDS = [
    "id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "role_title",
    "client_company_id",
    "kanzleiname",
    "is_primary",
    "created_at",
    "updated_at",
]


def export_clients(session, path: Path) -> int:
    clients = session.scalars(select(ClientCompany).order_by(ClientCompany.name)).all()
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(CLIENT_FIELDS)
        for client in clients:
            writer.writerow([getattr(client, field) for field in CLIENT_FIELDS])
    return len(clients)


def export_contacts(session, path: Path) -> int:
    contacts = session.scalars(
        select(ContactPerson).order_by(ContactPerson.last_name)
    ).all()
    client_names = dict(session.execute(select(ClientCompany.id, ClientCompany.name)).all())
    header = [CONTACT_HEADER_OVERRIDES.get(field, field) for field in CONTACT_FIELDS]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(header)
        for contact in contacts:
            row = []
            for field in CONTACT_FIELDS:
                if field == "kanzleiname":
                    row.append(client_names.get(contact.client_company_id, ""))
                else:
                    row.append(getattr(contact, field))
            writer.writerow(row)
    return len(contacts)


def upload_to_s3(path: Path) -> str:
    settings = get_settings()
    key = f"{S3_PREFIX}/{path.name}"
    with path.open("rb") as handle:
        _s3_client().put_object(Bucket=settings.s3_bucket, Key=key, Body=handle.read())
    return key


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clients_path = OUTPUT_DIR / CLIENTS_FILENAME
    contacts_path = OUTPUT_DIR / CONTACTS_FILENAME

    with SessionLocal() as session:
        clients_count = export_clients(session, clients_path)
        contacts_count = export_contacts(session, contacts_path)

    print(f"Kanzleien exportiert: {clients_count} -> {clients_path}")
    print(f"Kontakte exportiert: {contacts_count} -> {contacts_path}")

    if _s3_configured():
        clients_key = upload_to_s3(clients_path)
        contacts_key = upload_to_s3(contacts_path)
        print()
        print("Zum Abholen in den Bucket hochgeladen (bitte danach wieder loeschen):")
        print(f"  {clients_key}")
        print(f"  {contacts_key}")
    else:
        print()
        print("S3 ist nicht konfiguriert - Dateien liegen nur lokal im Container unter:")
        print(f"  {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
