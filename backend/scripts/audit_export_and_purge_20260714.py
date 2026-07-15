"""Lagert die per Read-only-Audit als auffaellig markierten Kanzleien/Kontakte
in Pruefliste-CSVs aus, BEVOR irgendetwas geloescht wird, und entfernt sie
danach aus den Haupttabellen.

Eingabe (Projektordner):
  Audit_Kanzleien_Auffaellig_20260714.csv (121 Zeilen, Spalte "id")
  Audit_Kontakte_Auffaellig_20260714.csv  (263 Zeilen, Spalte "id")

Ausgabe (Projektordner):
  Pruefliste_Kanzleien_20260714.csv - alle Spalten von ClientCompany + pruefgrund
  Pruefliste_Kontakte_20260714.csv  - Vereinigung aus (a) direkt auffaelligen
      Kontakten und (b) allen Kontakten der 121 ausgelagerten Kanzleien (auch
      unauffaelligen - sonst verschwaenden die kommentarlos), dedupliziert,
      plus pruefgrund + firma_name.

WICHTIG (Erkenntnis waehrend der Implementierung):
1. Die id-Spalten in den Audit-CSVs sind roher 32-stelliger Hex-UUID-Text ohne
   Bindestriche (z.B. "708c17379c444464a725ad319ef2f72b") - das entspricht
   exakt uuid.UUID(...).hex, NICHT str(uuid.UUID(...)) (das mit Bindestrichen
   formatiert). Alle Vergleiche/Dict-Lookups zwischen den Audit-CSV-Werten und
   den aus der DB gelesenen SQLAlchemy Uuid(as_uuid=True)-Spalten laufen
   deshalb konsequent ueber .hex, nicht ueber str(). Beim Schreiben der
   Pruefliste-CSVs (reine Lesbarkeit) wird trotzdem die uebliche gebindestrichte
   str()-Form verwendet - das ist nur fuer den Menschen, keine Vergleichsbasis.
2. Die Modelle deklarieren ondelete="CASCADE" (ContactPerson.client_company_id)
   bzw. ondelete="RESTRICT" (CandidateSubmission/JobMandate.client_company_id),
   aber die App aktiviert nie "PRAGMA foreign_keys=ON" fuer ihre SQLite-
   Verbindungen (kein Event-Listener in infrastructure/core gefunden) - SQLite
   erzwingt Fremdschluessel-Constraints standardmaessig NICHT. Ein simples
   "DELETE FROM client_companies WHERE id IN (...)" wuerde deshalb weder
   automatisch die zugehoerigen Kontakte mitloeschen noch einen Fehler werfen,
   wenn noch eine Submission/ein Mandat an der Kanzlei haengt - es wuerden
   stille verwaiste Fremdschluessel entstehen. Dieses Skript bildet das
   GEWOLLTE Verhalten deshalb explizit nach:
     - Kontakte einer geloeschten Kanzlei werden manuell mitgeloescht
       (simuliert CASCADE).
     - Kanzleien mit einer verbleibenden Submission/einem Mandat werden NICHT
       geloescht (simuliert RESTRICT) und stattdessen gemeldet - keine eigene
       inhaltliche Neubewertung, nur ein technischer Show-Stopper.

Ausfuehren:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\audit_export_and_purge_20260714.py
"""

from __future__ import annotations

import csv
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.contact_person import ContactPerson  # noqa: E402
from cc_crm.models.job_mandate import JobMandate  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402

PROJECT_DIR = Path(r"C:\Users\comma\Claude\Projects\Commandeur Consulting GmbH")
AUDIT_KANZLEIEN_CSV = PROJECT_DIR / "Audit_Kanzleien_Auffaellig_20260714.csv"
AUDIT_KONTAKTE_CSV = PROJECT_DIR / "Audit_Kontakte_Auffaellig_20260714.csv"
PRUEFLISTE_KANZLEIEN_CSV = PROJECT_DIR / "Pruefliste_Kanzleien_20260714.csv"
PRUEFLISTE_KONTAKTE_CSV = PROJECT_DIR / "Pruefliste_Kontakte_20260714.csv"

CLIENT_COMPANY_COLUMNS = [
    "id",
    "name",
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
    "refund_terms",
    "guarantee_period_months",
    "payment_terms_days",
    "special_terms",
    "commercial_notes",
    "honorar_stufe",
    "nachlass_begruendung",
    "agb_version",
    "kanzleigruppe",
    "notes",
    "created_at",
    "updated_at",
]

CONTACT_PERSON_COLUMNS = [
    "id",
    "client_company_id",
    "first_name",
    "last_name",
    "role_title",
    "email",
    "phone",
    "is_primary",
    "created_at",
    "updated_at",
]


def load_audit_rows(path: Path) -> dict[str, dict[str, str]]:
    """Key = rohe Hex-UUID (.hex-Form) aus der CSV, wie sie dort steht."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}


def model_to_row(entity: object, columns: list[str]) -> dict[str, str]:
    row: dict[str, str] = {}
    for column in columns:
        value = getattr(entity, column)
        row[column] = "" if value is None else str(value)
    return row


def main() -> None:
    audit_kanzleien = load_audit_rows(AUDIT_KANZLEIEN_CSV)
    audit_kontakte = load_audit_rows(AUDIT_KONTAKTE_CSV)
    kanzleien_hex_ids = set(audit_kanzleien.keys())
    kontakte_hex_ids = set(audit_kontakte.keys())
    kanzleien_uuids = {uuid.UUID(hex_id) for hex_id in kanzleien_hex_ids}
    kontakte_uuids = {uuid.UUID(hex_id) for hex_id in kontakte_hex_ids}

    session = SessionLocal()
    try:
        companies_before = session.query(ClientCompany).count()
        contacts_before = session.query(ContactPerson).count()

        flagged_companies = (
            session.query(ClientCompany).filter(ClientCompany.id.in_(kanzleien_uuids)).all()
        )
        found_company_hex_ids = {c.id.hex for c in flagged_companies}
        missing_company_ids = kanzleien_hex_ids - found_company_hex_ids
        if missing_company_ids:
            print(
                f"WARNUNG: {len(missing_company_ids)} Kanzlei-ID(s) aus der Audit-CSV "
                f"nicht (mehr) in der DB gefunden: {sorted(missing_company_ids)}"
            )

        # --- Pruefliste Kanzleien exportieren (VOR jeder Loeschung) ---
        with PRUEFLISTE_KANZLEIEN_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[*CLIENT_COMPANY_COLUMNS, "pruefgrund"])
            writer.writeheader()
            for company in flagged_companies:
                row = model_to_row(company, CLIENT_COMPANY_COLUMNS)
                row["pruefgrund"] = audit_kanzleien[company.id.hex]["gruende"]
                writer.writerow(row)
        print(f"Pruefliste_Kanzleien_20260714.csv geschrieben: {len(flagged_companies)} Zeilen")

        # --- Kontakte: Gruppe (a) direkt auffaellig, Gruppe (b) Kontakte der
        # auszulagernden Kanzleien (auch unauffaellige) ---
        group_a_contacts = (
            session.query(ContactPerson).filter(ContactPerson.id.in_(kontakte_uuids)).all()
        )
        found_contact_hex_ids = {c.id.hex for c in group_a_contacts}
        missing_contact_ids = kontakte_hex_ids - found_contact_hex_ids
        if missing_contact_ids:
            print(
                f"WARNUNG: {len(missing_contact_ids)} Kontakt-ID(s) aus der Audit-CSV "
                f"nicht (mehr) in der DB gefunden: {sorted(missing_contact_ids)}"
            )

        found_company_uuids = {c.id for c in flagged_companies}
        group_b_contacts = (
            session.query(ContactPerson)
            .filter(ContactPerson.client_company_id.in_(found_company_uuids))
            .all()
        )

        company_name_by_hex_id = {c.id.hex: c.name for c in flagged_companies}
        # Zusaetzlich Firmennamen fuer Gruppe (a)-Kontakte laden, deren Kanzlei
        # NICHT mit ausgelagert wird (fuer die firma_name-Spalte trotzdem
        # benoetigt).
        other_company_uuids = {c.client_company_id for c in group_a_contacts} - found_company_uuids
        if other_company_uuids:
            for company in (
                session.query(ClientCompany).filter(ClientCompany.id.in_(other_company_uuids)).all()
            ):
                company_name_by_hex_id[company.id.hex] = company.name

        combined: dict[str, tuple[ContactPerson, str]] = {}
        for contact in group_a_contacts:
            combined[contact.id.hex] = (contact, audit_kontakte[contact.id.hex]["gruende"])
        for contact in group_b_contacts:
            if contact.id.hex not in combined:
                combined[contact.id.hex] = (contact, "Kontakt einer ausgelagerten Kanzlei")

        with PRUEFLISTE_KONTAKTE_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=[*CONTACT_PERSON_COLUMNS, "pruefgrund", "firma_name"]
            )
            writer.writeheader()
            for contact, pruefgrund in combined.values():
                row = model_to_row(contact, CONTACT_PERSON_COLUMNS)
                row["pruefgrund"] = pruefgrund
                row["firma_name"] = company_name_by_hex_id.get(contact.client_company_id.hex, "")
                writer.writerow(row)
        print(f"Pruefliste_Kontakte_20260714.csv geschrieben: {len(combined)} Zeilen")
        print(
            f"  davon direkt auffaellig (Gruppe a): {len(group_a_contacts)}, "
            f"davon nur ueber Kanzlei-Zugehoerigkeit (Gruppe b, unauffaellig "
            f"fuer sich genommen): {len(combined) - len(group_a_contacts)}"
        )

        # --- Loeschen: Kanzleien, die keine Submission/kein Mandat mehr haben ---
        blocked_companies: list[tuple[str, str]] = []
        deletable_company_uuids: list[uuid.UUID] = []
        for company in flagged_companies:
            has_submission = (
                session.query(CandidateSubmission).filter_by(client_company_id=company.id).first()
                is not None
            )
            has_mandate = (
                session.query(JobMandate).filter_by(client_company_id=company.id).first()
                is not None
            )
            if has_submission or has_mandate:
                blocked_companies.append((company.id.hex, company.name))
            else:
                deletable_company_uuids.append(company.id)

        # Kontakte der tatsaechlich geloeschten Kanzleien manuell mitloeschen
        # (kein DB-seitiges ON DELETE CASCADE aktiv, siehe Modul-Docstring).
        cascade_deleted_contacts = (
            session.query(ContactPerson)
            .filter(ContactPerson.client_company_id.in_(deletable_company_uuids))
            .count()
        )
        session.query(ContactPerson).filter(
            ContactPerson.client_company_id.in_(deletable_company_uuids)
        ).delete(synchronize_session=False)

        session.query(ClientCompany).filter(ClientCompany.id.in_(deletable_company_uuids)).delete(
            synchronize_session=False
        )
        session.flush()

        # --- Loeschen: verbleibende auffaellige Kontakte, deren Kanzlei NICHT
        # mit ausgelagert wurde (weder generell ausserhalb der 121, noch die
        # blockierten Faelle) ---
        deletable_company_hex_ids = {u.hex for u in deletable_company_uuids}
        already_cascaded_hex_ids = {
            c.id.hex
            for c in group_a_contacts
            if c.client_company_id.hex in deletable_company_hex_ids
        }
        remaining_flagged_hex_ids = kontakte_hex_ids - already_cascaded_hex_ids
        remaining_flagged_uuids = {uuid.UUID(hex_id) for hex_id in remaining_flagged_hex_ids}
        individually_deleted = (
            session.query(ContactPerson)
            .filter(ContactPerson.id.in_(remaining_flagged_uuids))
            .count()
        )
        session.query(ContactPerson).filter(ContactPerson.id.in_(remaining_flagged_uuids)).delete(
            synchronize_session=False
        )

        session.commit()

        companies_after = session.query(ClientCompany).count()
        contacts_after = session.query(ContactPerson).count()
    finally:
        session.close()

    print("\n=== Zusammenfassung ===")
    print(f"Kanzleien vorher: {companies_before}, nachher: {companies_after}")
    print(
        f"  davon geloescht: {len(deletable_company_uuids)}, "
        f"NICHT geloescht (Submission/Mandat vorhanden): {len(blocked_companies)}"
    )
    for company_hex_id, name in blocked_companies:
        print(f"    BLOCKIERT: {name!r} ({company_hex_id}) - hat noch Submission/Mandat")

    print(f"\nKontakte vorher: {contacts_before}, nachher: {contacts_after}")
    print(f"  davon durch Kanzlei-Loeschung (Kaskade) entfernt: {cascade_deleted_contacts}")
    print(f"  davon einzeln entfernt (Kanzlei blieb bestehen): {individually_deleted}")
    print(
        f"  gesamt entfernt: {cascade_deleted_contacts + individually_deleted} "
        f"(erwartet: {contacts_before - contacts_after})"
    )


if __name__ == "__main__":
    main()
