"""Importiert die neuen Kandidaten, die bei der Downloads-Ordner-Sichtung vom
2026-07-06 gefunden wurden (Nutzer-Auftrag: "such in meinem Download Ordner
nach neuen CVs und ergänze diese in unsere CVs, danach master Excel
entsprechend updaten, danach updaten wir alles im system").

Anders als import_master_candidates.py ist dieses Skript NICHT destruktiv:
es löscht nichts, sondern ergänzt ausschließlich die neuen Zeilen, die in
CVs_master_updated.csv mit Herkunft="Downloads-Ordner (Sichtung 2026-07-06)"
markiert sind (IDs 4053-4323, direkt im Anschluss an die bestehenden 2675
Kandidaten mit Nummern 192-4052).

Methodik der Namenserkennung (siehe /tmp/extract_names.py-Historie dieser
Session für die volle Herleitung, hier nur die Kurzfassung): 973 Dokumente im
Downloads-Ordner wurden per Hash + Dateiname gegen die bestehende CV-Ablage
(2245 Dateien) abgeglichen. Für die verbleibenden ~550 neuen Dateien wurde der
Text extrahiert (pdftotext, python-docx inkl. Tabellen/Textboxen, Tesseract-OCR
als Fallback für gescannte PDFs) und nach CV-Merkmalen klassifiziert. Der Name
wurde aus mehreren unabhängigen Signalen kombiniert:
  1. Explizite "Vorname:"/"Nachname:"-Felder im Dokument (höchste Priorität).
  2. Die verifizierte Bullhorn-Dateinamenskonvention "<id>_Nachname_Vorname"
     (an 20+ bestehenden CSV-Zeilen zu 100% bestätigt) - genutzt als Anker für
     nummerierte Dateien.
  3. Header-Zeilen im Dokument, E-Mail-Lokalteil als Gegenprobe.
Stimmen mehrere Signale überein, wurde Match_Konfidenz leer gelassen. Bei
Widersprüchen (z.B. Dateiname und Inhalt nennen unterschiedliche Namen),
unklarer Vorname/Nachname-Reihenfolge, oder wenn nur ein einzelnes,
unbestätigtes Signal vorlag, steht Match_Konfidenz=low-review und der Grund
in General Comments - diese Kandidaten bitte im CRM stichprobenartig
gegenprüfen (Namen sind dort direkt editierbar).

15 Dateien hatten weder aus Dateiname noch Inhalt einen erkennbaren Namen
(z.B. reine Scans ohne verwertbaren Text) - deren CVs liegen bereits in
Desktop/CVs, aber es wurde bewusst KEINE Kandidatenzeile angelegt (kein Raten
ohne jede Namensgrundlage). Diese sind in der Review-Tabelle gesondert
aufgeführt und müssen von Hand im CRM angelegt werden.

Ausführen:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\import_downloads_cvs.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.enums import CandidateStatus  # noqa: E402
from cc_crm.schemas.candidate import CandidateCreate, CandidateUpdate  # noqa: E402
from cc_crm.schemas.operational import DocumentCreate  # noqa: E402
from cc_crm.services.candidates import CandidateService  # noqa: E402
from cc_crm.services.operational import DocumentService  # noqa: E402
from cc_crm.services.storage import save_document_bytes  # noqa: E402

CSV_PATH = Path(
    r"C:\Users\comma\OneDrive - Commandeur Consulting GmbH\Desktop\CVs_master_updated.csv"
)
CV_FOLDER = Path(r"C:\Users\comma\OneDrive - Commandeur Consulting GmbH\Desktop\CVs")
HERKUNFT_MARKER = "Downloads-Ordner (Sichtung 2026-07-06)"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def valid_email(value: str | None) -> str | None:
    value = clean(value)
    if value and _EMAIL_RE.match(value):
        return value
    return None


def load_new_rows() -> list[dict[str, str]]:
    with open(CSV_PATH, encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if clean(row.get("Herkunft")) == HERKUNFT_MARKER]


def build_freitext_notizen(row: dict[str, str]) -> str | None:
    parts: list[str] = []
    comments = clean(row.get("General Comments"))
    if comments:
        parts.append(comments)
    parts.append(f"Herkunft: {HERKUNFT_MARKER}")
    konfidenz = clean(row.get("Match_Konfidenz"))
    if konfidenz and konfidenz.lower() == "low-review":
        parts.append(
            "⚠ INTERN: Match_Konfidenz=low-review beim automatischen CV-Namensabgleich - "
            "Name/Daten vor Kontaktaufnahme stichprobenartig gegenprüfen."
        )
    return "\n\n".join(parts) if parts else None


def attach_cv(session: Session, candidate: Candidate, cv_filename: str) -> bool:
    source_path = CV_FOLDER / cv_filename
    if not source_path.is_file():
        return False
    content = source_path.read_bytes()
    storage_key = save_document_bytes(
        owner_type="candidate",
        owner_id=candidate.id,
        filename=cv_filename,
        content=content,
    )
    DocumentService(session).create(
        DocumentCreate(
            owner_type="candidate",
            owner_id=candidate.id,
            document_type="cv",
            filename=cv_filename,
            storage_key=storage_key,
            content_type=_CONTENT_TYPES.get(source_path.suffix.lower()),
            size_bytes=len(content),
            uploaded_by="import_downloads_cvs.py",
        )
    )
    return True


def main() -> None:
    if not CSV_PATH.is_file():
        raise SystemExit(f"CSV nicht gefunden: {CSV_PATH}")
    if not CV_FOLDER.is_dir():
        raise SystemExit(f"CV-Ordner nicht gefunden: {CV_FOLDER}")

    rows = load_new_rows()
    print(f"Neue Zeilen in CSV (Herkunft-Marker): {len(rows)}")

    session = SessionLocal()
    created = 0
    already_exists = 0
    skipped_no_name = 0
    cv_attached = 0
    cv_missing = 0
    low_review = 0
    failed_rows: list[tuple[str, str]] = []

    try:
        candidate_service = CandidateService(session)

        for row in rows:
            row_id = clean(row.get("id")) or "?"
            first_name = clean(row.get("First Name"))
            last_name = clean(row.get("Surname"))
            if not first_name or not last_name:
                skipped_no_name += 1
                continue

            existing = (
                session.query(Candidate).filter_by(candidate_number=row_id).first()
                if row_id != "?"
                else None
            )
            if existing is not None:
                already_exists += 1
                continue

            try:
                raw_email = row.get("Personal Email") or row.get("Work Email")
                email = valid_email(raw_email)

                candidate = candidate_service.create(
                    CandidateCreate(
                        candidate_number=row_id,
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        phone=clean(row.get("Mobile Phone")) or clean(row.get("Work Phone")),
                        status=CandidateStatus.ACTIVE,
                        freitext_notizen=build_freitext_notizen(row),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - eine fehlerhafte Zeile darf den Rest nicht stoppen
                failed_rows.append((row_id, str(exc)))
                session.rollback()
                continue

            created += 1
            konfidenz = clean(row.get("Match_Konfidenz"))
            if konfidenz and konfidenz.lower() == "low-review":
                low_review += 1

            cv_filename = clean(row.get("CV_Datei"))
            if cv_filename:
                try:
                    if attach_cv(session, candidate, cv_filename):
                        candidate_service.update(candidate.id, CandidateUpdate(cv_available=True))
                        cv_attached += 1
                    else:
                        cv_missing += 1
                except Exception as exc:  # noqa: BLE001
                    failed_rows.append((f"{row_id} (CV-Anhang)", str(exc)))
                    session.rollback()

        session.commit()
    finally:
        session.close()

    print("---")
    print(f"Kandidaten angelegt: {created}")
    print(f"Bereits vorhanden (gleiche candidate_number, übersprungen): {already_exists}")
    print(f"Übersprungen (kein Name automatisch ermittelbar): {skipped_no_name}")
    print(f"Fehlgeschlagen: {len(failed_rows)}")
    print(f"CVs angehängt: {cv_attached}")
    print(f"CVs referenziert, aber Datei nicht gefunden: {cv_missing}")
    print(f"Intern markiert (Match_Konfidenz=low-review, bitte im CRM gegenprüfen): {low_review}")
    if failed_rows:
        print("---")
        print("Fehlgeschlagene Zeilen (CSV-id: Fehlermeldung):")
        for csv_id, message in failed_rows:
            print(f"  - {csv_id}: {message}")


if __name__ == "__main__":
    main()
