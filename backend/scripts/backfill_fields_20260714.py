"""Datenfelder-Backfill aus der geprüften Master-Datei
CVs_master_updated_corrected_20260714.csv (Phase M, Punkt 3 - Folgelauf).
Nachfolgerin von ..._20260713.csv - enthält dieselben PLZ/Ort/Telefon-Daten
plus 8 zusätzliche neue Kandidaten (#4325-#4332) aus einem zweiten
Downloads-Sweep.

Rollenteilung: dieses Skript trifft KEINE eigenen Entscheidungen über Werte,
es synchronisiert nur mechanisch, was in der Datei steht:

1. Für JEDE Zeile der CSV (unabhängig von Match_Konfidenz - wie im Vorlauf
   vom 2026-07-13 auf expliziten Nutzerwunsch von nur "corrected-*" auf alle
   Zeilen erweitert): falls Post Code/City/Mobile Phone in der CSV gesetzt
   ist, der DB-Datensatz (Match über candidate_number == CSV-Spalte "id")
   aber diese Felder leer hat, aus der CSV übernehmen - nur leere Felder,
   ein vorhandener DB-Wert wird nie überschrieben.
2. Kandidaten #4085 sowie #4325-#4332 existieren noch nicht in der DB -
   werden neu angelegt (voller Datensatz aus der CSV-Zeile inkl. CV-Anhang,
   falls die Datei im CV-Ordner gefunden wird - Datei-Endung wird toleranzt
   geprüft, da CV_Datei in der CSV bei #4326 ".pdf" nennt, die tatsächliche
   Datei aber ".docx" ist).

Ausführen:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\backfill_fields_20260714.py
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy.orm import Session  # noqa: E402

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
    r"\CVs_master_updated_corrected_20260714.csv"
)
CV_FOLDER = Path(r"C:\Users\comma\OneDrive - Commandeur Consulting GmbH\Desktop\CVs")

NEW_CANDIDATE_NUMBERS = {"4085", "4325", "4326", "4327", "4328", "4329", "4330", "4331", "4332"}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CV_EXTENSIONS = (".pdf", ".docx", ".doc", ".rtf", ".odt")
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".rtf": "application/rtf",
    ".odt": "application/vnd.oasis.opendocument.text",
}

_BACKFILL_FIELDS = {
    "postal_code": "Post Code",
    "city": "City",
    "phone": "Mobile Phone",
}

_DNU_STATUSES = {"dnu", "do not use"}


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


def _find_cv_file(cv_filename: str) -> Path | None:
    """CV_Datei in der CSV nennt manchmal die falsche Endung (z.B. #4326:
    CSV sagt .pdf, tatsaechliche Datei ist .docx) - probiert deshalb den
    exakten Namen zuerst, dann denselben Stamm mit anderen CV-Endungen."""
    exact = CV_FOLDER / cv_filename
    if exact.is_file():
        return exact
    stem = Path(cv_filename).stem
    for ext in _CV_EXTENSIONS:
        candidate = CV_FOLDER / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _status_for(raw_status: str | None) -> CandidateStatus:
    if raw_status and raw_status.strip().casefold() in _DNU_STATUSES:
        return CandidateStatus.BLOCKED
    return CandidateStatus.ACTIVE


def _attach_cv(session: Session, candidate: Candidate, cv_filename: str) -> bool:
    source = _find_cv_file(cv_filename)
    if source is None:
        return False
    content = source.read_bytes()
    storage_key = save_document_bytes(
        owner_type="candidate",
        owner_id=candidate.id,
        filename=source.name,
        content=content,
    )
    DocumentService(session).create(
        DocumentCreate(
            owner_type="candidate",
            owner_id=candidate.id,
            document_type="cv",
            filename=source.name,
            storage_key=storage_key,
            content_type=_CONTENT_TYPES.get(source.suffix.lower()),
            size_bytes=len(content),
            uploaded_by="backfill_fields_20260714.py",
        )
    )
    return True


def _build_freitext_notizen(row: dict[str, str]) -> str | None:
    parts: list[str] = []
    comments = _clean(row.get("General Comments"))
    if comments:
        parts.append(comments)
    herkunft = _clean(row.get("Herkunft"))
    if herkunft:
        parts.append(f"Herkunft: {herkunft}")
    current_company = _clean(row.get("Current Company"))
    if current_company:
        parts.append(f"Aktuelles Unternehmen (Quelldaten): {current_company}")
    return "\n\n".join(parts) if parts else None


def main() -> None:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    session = SessionLocal()
    candidates_by_number = {c.candidate_number: c for c in session.query(Candidate).all()}

    filled_counts = dict.fromkeys(_BACKFILL_FIELDS, 0)
    examples: list[tuple[str, str, str, str]] = []
    created: list[str] = []
    cv_attached: list[str] = []
    cv_missing: list[str] = []
    not_found: list[str] = []

    for row in rows:
        candidate_number = row["id"].strip()
        if candidate_number in NEW_CANDIDATE_NUMBERS:
            continue  # unten separat als Neuanlage behandelt

        candidate = candidates_by_number.get(candidate_number)
        if candidate is None:
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

    session.commit()

    candidate_service = CandidateService(session)
    for candidate_number in sorted(NEW_CANDIDATE_NUMBERS):
        if candidate_number in candidates_by_number:
            continue  # bereits vorhanden (z.B. #4324 aus dem Vorlauf), nicht anfassen
        matching_rows = [r for r in rows if r["id"].strip() == candidate_number]
        if not matching_rows:
            not_found.append(candidate_number)
            continue
        row = matching_rows[0]

        new_candidate = candidate_service.create(
            CandidateCreate(
                candidate_number=candidate_number,
                first_name=_clean(row["First Name"]) or "",
                last_name=_clean(row["Surname"]) or "",
                email=_valid_email(row["Personal Email"]),
                phone=_clean(row["Mobile Phone"]),
                job_title=_clean(row["Current Job Title"]),
                postal_code=_clean(row["Post Code"]),
                city=_clean(row["City"]),
                status=_status_for(row["Status"]),
                cv_available=True,
                freitext_notizen=_build_freitext_notizen(row),
            )
        )
        session.commit()
        created.append(candidate_number)

        cv_filename = row["CV_Datei"].strip()
        if cv_filename and _attach_cv(session, new_candidate, cv_filename):
            cv_attached.append(candidate_number)
        elif cv_filename:
            cv_missing.append(candidate_number)
        session.commit()

    print("Befüllte Felder (nur zuvor leer):")
    for field_name in _BACKFILL_FIELDS:
        print(f"  {field_name}: {filled_counts[field_name]}")

    print("\nBeispiele (vorher -> nachher):")
    for candidate_number, field_name, before, after in examples:
        print(f"  #{candidate_number} {field_name}: {before} -> {after!r}")

    print(f"\nNeu angelegt: {created}")
    print(f"CV angehängt: {cv_attached}")
    if cv_missing:
        print(f"CV-Datei nicht gefunden für: {cv_missing}")

    if not_found:
        print(
            f"\nWARNUNG: {len(not_found)} candidate_number aus der CSV nicht in der DB "
            f"gefunden (und nicht in NEW_CANDIDATE_NUMBERS gelistet): "
            f"{not_found[:20]}{' ...' if len(not_found) > 20 else ''}"
        )

    session.close()


if __name__ == "__main__":
    main()
