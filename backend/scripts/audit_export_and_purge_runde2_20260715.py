"""Runde 2: lagert Infra/SaaS-Fehleintraege und wahrscheinliche Nicht-Kanzleien
aus der manuellen Zweitsichtung in Pruefliste-CSVs aus, BEVOR irgendetwas
geloescht wird, und entfernt sie danach aus den Haupttabellen. Gleiches
Vorgehen wie beim ersten Durchgang (audit_export_and_purge_20260714.py),
diesmal ohne separate "auffaellige Kontakte"-Liste - hier werden schlicht
ALLE Kontakte der 62 auszulagernden Kanzleien mit ausgelagert.

Eingabe (Projektordner):
  Audit2_Infra_SaaS_Domains_20260715.csv (28 Zeilen) - Mail-/Hosting-/SaaS-
      Infrastruktur (Yahoo, Personio, Lexware, ...), die die Postfach-
      Extraktion faelschlich als Kanzlei gelesen hat.
  Audit2_Wahrscheinlich_NichtKanzlei_20260715.csv (34 Zeilen) - echte Firmen,
      aber keine Steuerkanzleien/WP/Kanzleien (Kandidaten-Arbeitgeber-
      Erwaehnungen wie Bilfinger, Generali, Kliniken, Universitaeten, Stadt
      Leverkusen).
  Beide: Spalten id, name, status, website, email, grund. Keine Ueberlappung
  (62 eindeutige IDs, per Diff bestaetigt).

Ausgabe (Projektordner):
  Pruefliste_Kanzleien_Runde2_20260715.csv - alle 62 ClientCompany-Zeilen,
      alle Spalten + pruefgrund (aus "grund", praefixiert mit "Infra/SaaS: "
      bzw. "Nicht-Kanzlei: " je nach Quelldatei).
  Pruefliste_Kontakte_Runde2_20260715.csv - alle ContactPerson-Zeilen der 62
      Kanzleien (auch unauffaellige - sonst verschwaenden sie beim Loeschen
      kommentarlos), plus pruefgrund + firma_name.

WICHTIG (aus Runde 1 gelernt, hier konsequent angewendet):
1. Die id-Spalten in den Audit-CSVs sind roher 32-stelliger Hex-Text ohne
   Bindestriche, identisch zu uuid.UUID(...).hex. SQLAlchemys
   Uuid(as_uuid=True)-Spaltentyp verlangt fuer Bind-Parameter trotzdem echte
   uuid.UUID-Objekte (reine Strings fuehren zu einem AttributeError beim
   Ausfuehren der Query) - deshalb wird fuer JEDE DB-Query weiterhin nach
   uuid.UUID(hex_id) konvertiert, aber JEDER Vergleich/jedes Dict-Lookup
   zwischen Audit-CSV und DB-Entity laeuft ausschliesslich ueber die
   .hex-Form (nie ueber str(), das Bindestriche einfuegen wuerde). Beim
   Schreiben der Pruefliste-CSVs wird die id-Spalte deshalb explizit als
   .hex geschrieben (nicht die menschenlesbich gebindestrichte str()-Form
   wie in Runde 1) - damit bleibt sie 1:1 mit der DB/den Audit-CSVs
   vergleichbar, wie explizit gewuenscht.
2. SQLite erzwingt ondelete="CASCADE"/"RESTRICT" aus den Modellen NICHT
   automatisch (kein aktives PRAGMA foreign_keys=ON in der App - siehe
   Docstring von audit_export_and_purge_20260714.py fuer die vollstaendige
   Herleitung). Kontakte geloeschter Kanzleien werden deshalb manuell
   mitgeloescht (simuliert CASCADE); Kanzleien mit einer verbleibenden
   Submission/einem Mandat werden NICHT geloescht (simuliert RESTRICT),
   bleiben aber korrekt in der Pruefliste (wie beim ZAHLENWERK-Fall in
   Runde 1).

Ausfuehren:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\audit_export_and_purge_runde2_20260715.py
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
AUDIT_INFRA_CSV = PROJECT_DIR / "Audit2_Infra_SaaS_Domains_20260715.csv"
AUDIT_NICHTKANZLEI_CSV = PROJECT_DIR / "Audit2_Wahrscheinlich_NichtKanzlei_20260715.csv"
PRUEFLISTE_KANZLEIEN_CSV = PROJECT_DIR / "Pruefliste_Kanzleien_Runde2_20260715.csv"
PRUEFLISTE_KONTAKTE_CSV = PROJECT_DIR / "Pruefliste_Kontakte_Runde2_20260715.csv"

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


def load_audit_rows(path: Path, prefix: str) -> dict[str, dict[str, str]]:
    """Key = rohe Hex-UUID (.hex-Form) aus der CSV. pruefgrund wird hier
    schon mit dem Quell-Praefix versehen ("Infra/SaaS: "/"Nicht-Kanzlei: ")."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = {}
        for row in csv.DictReader(handle):
            row["pruefgrund"] = f"{prefix}{row['grund']}"
            rows[row["id"]] = row
        return rows


def model_to_row(entity: object, columns: list[str]) -> dict[str, str]:
    """Wie in Runde 1, aber id/client_company_id werden bewusst als .hex
    (rohe DB-Form ohne Bindestriche) statt als gebindestrichte str()-Form
    geschrieben - explizite Vorgabe fuer Runde 2, damit die Pruefliste-CSV
    1:1 mit der DB und den Audit-CSVs vergleichbar bleibt."""
    row: dict[str, str] = {}
    for column in columns:
        value = getattr(entity, column)
        if value is None:
            row[column] = ""
        elif isinstance(value, uuid.UUID):
            row[column] = value.hex
        else:
            row[column] = str(value)
    return row


def main() -> None:
    audit_infra = load_audit_rows(AUDIT_INFRA_CSV, "Infra/SaaS: ")
    audit_nichtkanzlei = load_audit_rows(AUDIT_NICHTKANZLEI_CSV, "Nicht-Kanzlei: ")

    overlap = set(audit_infra) & set(audit_nichtkanzlei)
    if overlap:
        print(f"WARNUNG: {len(overlap)} ID(s) kommen in BEIDEN Audit-CSVs vor: {sorted(overlap)}")

    audit_combined = {**audit_infra, **audit_nichtkanzlei}
    target_hex_ids = set(audit_combined.keys())
    target_uuids = {uuid.UUID(hex_id) for hex_id in target_hex_ids}
    print(f"Zusammengefuehrte Zielliste: {len(target_hex_ids)} eindeutige IDs")

    session = SessionLocal()
    try:
        companies_before = session.query(ClientCompany).count()
        contacts_before = session.query(ContactPerson).count()

        flagged_companies = (
            session.query(ClientCompany).filter(ClientCompany.id.in_(target_uuids)).all()
        )
        found_hex_ids = {c.id.hex for c in flagged_companies}
        missing_ids = target_hex_ids - found_hex_ids
        if missing_ids:
            print(
                f"WARNUNG: {len(missing_ids)} ID(s) aus den Audit-CSVs nicht (mehr) "
                f"in der DB gefunden: {sorted(missing_ids)}"
            )

        # --- Pruefliste Kanzleien exportieren (VOR jeder Loeschung) ---
        with PRUEFLISTE_KANZLEIEN_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[*CLIENT_COMPANY_COLUMNS, "pruefgrund"])
            writer.writeheader()
            for company in flagged_companies:
                row = model_to_row(company, CLIENT_COMPANY_COLUMNS)
                row["pruefgrund"] = audit_combined[company.id.hex]["pruefgrund"]
                writer.writerow(row)
        print(
            f"Pruefliste_Kanzleien_Runde2_20260715.csv geschrieben: {len(flagged_companies)} Zeilen"
        )

        # --- Pruefliste Kontakte: ALLE Kontakte der 62 Kanzleien ---
        flagged_company_uuids = {c.id for c in flagged_companies}
        all_contacts = (
            session.query(ContactPerson)
            .filter(ContactPerson.client_company_id.in_(flagged_company_uuids))
            .all()
        )
        company_name_by_hex_id = {c.id.hex: c.name for c in flagged_companies}

        with PRUEFLISTE_KONTAKTE_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=[*CONTACT_PERSON_COLUMNS, "pruefgrund", "firma_name"]
            )
            writer.writeheader()
            for contact in all_contacts:
                row = model_to_row(contact, CONTACT_PERSON_COLUMNS)
                row["pruefgrund"] = "Kontakt einer ausgelagerten Kanzlei"
                row["firma_name"] = company_name_by_hex_id.get(contact.client_company_id.hex, "")
                writer.writerow(row)
        print(f"Pruefliste_Kontakte_Runde2_20260715.csv geschrieben: {len(all_contacts)} Zeilen")

        # --- Loeschen: Kanzleien ohne verbleibende Submission/Mandat ---
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
    print(f"  gesamt entfernt: {contacts_before - contacts_after}")


if __name__ == "__main__":
    main()
