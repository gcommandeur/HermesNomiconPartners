"""LLM-basiertes Rolle/Arbeitgeber-Backfill fuer Kandidaten mit leerem
Current-Job-Title (Phase M, Punkt 4) - ca. 1.800 Kandidaten betroffen. Eine
Regex-Testauswertung an ~450 dieser Kandidaten war zu unzuverlaessig fuer
einen Bulk-Import (falsche Rolle/Firma-Trennung, OCR-Artefakte) und wurde
verworfen - dieses Skript nutzt stattdessen denselben LLM-Baustein wie der
Profil-Generator (Phase 2) bzw. der CV-Parser aus Punkt 2
(services/cv_extraction.py::extract_last_role).

WICHTIG: Schreibt NICHTS in die Live-DB. Ergebnis landet in einer Review-CSV
(Spalten: id, aktuelle Werte, LLM-Vorschlag, Konfidenz) - die Uebernahme
entscheidet der Nutzer manuell, genau wie bei den bisherigen
Namenskorrekturen. Dieselbe Bewerberprofil-Erkennung wie in Punkt 2
(Commandeur-Briefkopf) wird angewendet: liefert bei einem anonymisierten
Bewerberprofil ggf. noch verwertbare Rolle/Qualifikation (der generische
"Arbeitgeber-Typ" aus dem Profil selbst, kein erfundener Name).

Batch-Verarbeitung mit Fortschrittsspeicherung: die Review-CSV wird
zeilenweise angehaengt, ein erneuter Lauf ueberspringt candidate_number, die
bereits in der Ausgabedatei stehen - kann also in Tranchen (--limit) und bei
Unterbrechung fortgesetzt werden, ohne bereits verarbeitete Kandidaten
doppelt abzurechnen.

Ausfuehren (Beispiel: erste 10 Kandidaten als Testlauf):
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\backfill_job_titles_review.py --limit 10

Voller Lauf (kein --limit):
    .\\.venv\\Scripts\\python.exe scripts\\backfill_job_titles_review.py
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cc_crm.core.errors import AIProviderError  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models import Candidate, Document  # noqa: E402
from cc_crm.services.cv_extraction import (  # noqa: E402
    extract_last_role,
    extract_text_from_bytes,
    is_agency_letterhead,
)
from cc_crm.services.storage import read_document_bytes  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "job_title_backfill_review.csv"

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "current_job_title",
    "current_qualification",
    "current_ausbildung_titel",
    "suggested_job_title",
    "suggested_employer",
    "suggested_qualification",
    "suggested_ausbildung_titel",
    "confidence",
    "source_is_agency_profile",
    "error",
]


def _already_processed(output_path: Path) -> set[str]:
    if not output_path.is_file():
        return set()
    with output_path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["candidate_number"] for row in csv.DictReader(handle)}


def _confidence_for(suggestion: dict[str, object], is_agency: bool) -> str:
    has_job_title = bool(suggestion.get("job_title"))
    has_employer = bool(suggestion.get("employer"))
    if not has_job_title:
        return "low"
    if is_agency:
        return "medium"  # Arbeitgeber ist im Bewerberprofil ohnehin generisch beschrieben
    return "high" if has_employer else "medium"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Nur die ersten N noch offenen Kandidaten verarbeiten",
    )
    args = parser.parse_args()

    session = SessionLocal()
    processed_numbers = _already_processed(OUTPUT_PATH)
    print(f"Bereits in der Review-Datei erfasst: {len(processed_numbers)}")

    candidates = (
        session.query(Candidate)
        .filter((Candidate.job_title.is_(None)) | (Candidate.job_title == ""))
        .order_by(Candidate.candidate_number)
        .all()
    )
    pending = [c for c in candidates if c.candidate_number not in processed_numbers]
    print(f"Offene Kandidaten mit leerem Job-Title: {len(pending)}")

    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"Werden in diesem Lauf verarbeitet: {len(pending)}")

    file_exists = OUTPUT_PATH.is_file()
    with OUTPUT_PATH.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()

        skipped_no_cv = 0
        succeeded = 0
        failed = 0

        for candidate in pending:
            document = (
                session.query(Document)
                .filter(Document.owner_id == candidate.id, Document.document_type == "cv")
                .order_by(Document.created_at.desc())
                .first()
            )
            if document is None:
                skipped_no_cv += 1
                continue

            row = {
                "candidate_number": candidate.candidate_number,
                "candidate_id": str(candidate.id),
                "current_job_title": candidate.job_title or "",
                "current_qualification": candidate.qualification or "",
                "current_ausbildung_titel": candidate.ausbildung_titel or "",
                "suggested_job_title": "",
                "suggested_employer": "",
                "suggested_qualification": "",
                "suggested_ausbildung_titel": "",
                "confidence": "",
                "source_is_agency_profile": "",
                "error": "",
            }
            try:
                content = read_document_bytes(document.storage_key)
                cv_text = extract_text_from_bytes(document.filename, content)
                is_agency = is_agency_letterhead(cv_text)
                suggestion = extract_last_role(cv_text)
                row["suggested_job_title"] = suggestion.get("job_title") or ""
                row["suggested_employer"] = suggestion.get("employer") or ""
                row["suggested_qualification"] = suggestion.get("qualification") or ""
                row["suggested_ausbildung_titel"] = suggestion.get("ausbildung_titel") or ""
                row["confidence"] = _confidence_for(suggestion, is_agency)
                row["source_is_agency_profile"] = str(is_agency)
                succeeded += 1
            except (AIProviderError, ValueError, OSError) as exc:
                row["error"] = str(exc)[:300]
                failed += 1

            writer.writerow(row)
            handle.flush()
            time.sleep(0.2)  # sanftes Rate-Limiting, kein Sturmlauf auf die Anthropic-API

    print(f"\nErfolgreich verarbeitet: {succeeded}")
    print(f"Fehlgeschlagen (siehe 'error'-Spalte): {failed}")
    print(f"Übersprungen (kein CV-Dokument vorhanden): {skipped_no_cv}")
    print(f"Review-Datei: {OUTPUT_PATH}")
    session.close()


if __name__ == "__main__":
    main()
