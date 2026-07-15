"""Datenfelder-Backfill aus der geprüften Master-Datei
CVs_master_updated_corrected_20260713.csv (Phase M, Punkt 3). Nachfolgerin von
..._20260711.csv - enthält zusätzlich PLZ (Post Code), Ort (City) und Telefon
(Mobile Phone) für ca. 1.400 Kandidaten, mechanisch aus CV-Dateien extrahiert
und gegen eine echte PLZ-Datenbank validiert.

Rollenteilung: dieses Skript trifft KEINE eigenen Entscheidungen über Werte,
es synchronisiert nur mechanisch, was in der Datei steht:

1. Für JEDE Zeile der CSV (unabhängig von Match_Konfidenz - auf expliziten
   Nutzerwunsch am 2026-07-13 von ursprünglich nur "corrected-*" auf alle
   Zeilen erweitert, da die meisten PLZ/Ort/Telefon-Daten in den Kategorien
   "high"/"medium"/"low-review"/leer liegen, nicht in "corrected-*"): falls
   Post Code/City/Mobile Phone in der CSV gesetzt ist, der DB-Datensatz
   (Match über candidate_number == CSV-Spalte "id") aber diese Felder leer
   hat, aus der CSV übernehmen - nur leere Felder, ein vorhandener DB-Wert
   wird nie überschrieben.
2. Kandidat #4324 (Julia Briede) existiert noch nicht in der DB - wird neu
   angelegt (voller Datensatz, da Neuanlage keine "Ist das schon befüllt?"-
   Frage ist) inkl. Verknüpfung des bereits vorliegenden CV
   (4324_Briede_Julia.pdf).

Ausführen:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\backfill_fields_20260713.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models import Candidate  # noqa: E402
from cc_crm.models.enums import CandidateStatus  # noqa: E402
from cc_crm.schemas.candidate import CandidateCreate  # noqa: E402
from cc_crm.schemas.operational import DocumentCreate  # noqa: E402
from cc_crm.services.candidates import CandidateService  # noqa: E402
from cc_crm.services.operational import DocumentService  # noqa: E402
from cc_crm.services.storage import save_document_bytes  # noqa: E402

CSV_PATH = Path(
    r"C:\Users\comma\Claude\Projects\Commandeur Consulting GmbH"
    r"\CVs_master_updated_corrected_20260713.csv"
)
CV_FOLDER = Path(r"C:\Users\comma\OneDrive - Commandeur Consulting GmbH\Desktop\CVs")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_BACKFILL_FIELDS = {
    "postal_code": "Post Code",
    "city": "City",
    "phone": "Mobile Phone",
}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _valid_email(value: str | None) -> str | None:
    value = _clean(value)
    if value and _EMAIL_RE.match(value):
        return value
    return None


def main() -> None:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    session = SessionLocal()
    candidates_by_number = {c.candidate_number: c for c in session.query(Candidate).all()}

    filled_counts = dict.fromkeys(_BACKFILL_FIELDS, 0)
    examples: list[tuple[str, str, str, str]] = []  # (candidate_number, field, before, after)
    created: list[str] = []
    not_found: list[str] = []

    for row in rows:
        candidate_number = row["id"].strip()

        candidate = candidates_by_number.get(candidate_number)
        if candidate is None:
            if candidate_number == "4324":
                continue  # separat unten als Neuanlage behandelt
            not_found.append(candidate_number)
            continue

        for field_name, csv_column in _BACKFILL_FIELDS.items():
            csv_value = _clean(row[csv_column])
            current_value = getattr(candidate, field_name)
            if csv_value and not current_value:
                if len(examples) < 10:
                    examples.append((candidate_number, field_name, repr(current_value), csv_value))
                setattr(candidate, field_name, csv_value)
                filled_counts[field_name] += 1

    # Kandidat #4324 (Julia Briede) - Neuanlage, existierte noch nicht.
    if "4324" not in candidates_by_number:
        row_4324 = next(row for row in rows if row["id"].strip() == "4324")
        candidate_service = CandidateService(session)
        new_candidate = candidate_service.create(
            CandidateCreate(
                candidate_number="4324",
                first_name=_clean(row_4324["First Name"]) or "",
                last_name=_clean(row_4324["Surname"]) or "",
                email=_valid_email(row_4324["Personal Email"]),
                phone=_clean(row_4324["Mobile Phone"]),
                job_title=_clean(row_4324["Current Job Title"]),
                postal_code=_clean(row_4324["Post Code"]),
                city=_clean(row_4324["City"]),
                status=CandidateStatus.ACTIVE,
                cv_available=True,
                freitext_notizen=(
                    f"Herkunft: {row_4324['Herkunft']}\n\n"
                    f"Aktuelles Unternehmen (Quelldaten): {row_4324['Current Company']}\n\n"
                    f"{row_4324['General Comments']}"
                ),
            )
        )
        session.commit()
        created.append("4324")

        cv_source = CV_FOLDER / row_4324["CV_Datei"]
        if cv_source.is_file():
            content = cv_source.read_bytes()
            storage_key = save_document_bytes(
                owner_type="candidate",
                owner_id=new_candidate.id,
                filename=cv_source.name,
                content=content,
            )
            DocumentService(session).create(
                DocumentCreate(
                    owner_type="candidate",
                    owner_id=new_candidate.id,
                    document_type="cv",
                    filename=cv_source.name,
                    storage_key=storage_key,
                    content_type="application/pdf",
                    size_bytes=len(content),
                    uploaded_by="backfill_fields_20260713.py",
                )
            )
            session.commit()

    session.commit()

    print("Befüllte Felder (nur zuvor leer):")
    for field_name in _BACKFILL_FIELDS:
        print(f"  {field_name}: {filled_counts[field_name]}")

    print("\nBeispiele (vorher -> nachher):")
    for candidate_number, field_name, before, after in examples:
        print(f"  #{candidate_number} {field_name}: {before} -> {after!r}")

    print(f"\nNeu angelegt: {created}")
    if not_found:
        print(
            f"\nWARNUNG: {len(not_found)} candidate_number aus der CSV nicht in der DB "
            f"gefunden: {not_found[:20]}{' ...' if len(not_found) > 20 else ''}"
        )

    session.close()


if __name__ == "__main__":
    main()
