"""Backfill fuer bestehende Kandidaten mit laengst hochgeladenem CV, deren
Zielfelder (PLZ, Ort, Telefon, Rolle, Qualifikation, Ausbildung, fachliche
Schwerpunkte) noch leer sind. Legt dabei zusaetzlich - falls noch nicht
vorhanden - eine automatische Profilzusammenfassungs-Notiz an und speichert
das komplette CV-Extraktionsergebnis (cv_extraction_raw), exakt wie beim
regulaeren CV-Upload (siehe CandidateService.auto_fill_from_cv).

CandidateService.auto_fill_from_cv() wird bislang nur unmittelbar nach einem
NEUEN Upload angewendet (siehe document-panel.tsx::handleFileSelected) - nie
rueckwirkend fuer die ca. 2900 bereits bestehenden Kandidaten mit laengst
hochgeladenem CV. Dieses Skript holt fuer jeden betroffenen Kandidaten das
(neueste) CV-Dokument, extrahiert den Text und wendet dieselbe Logik an.

Wie beim Master-Excel-Bulk-Import (services/imports.py::
_candidate_field_updates): NUR aktuell leere Felder werden befuellt, ein
bereits vorhandener Wert wird nie ueberschrieben.

Dry-Run per Default (zeigt nur, was geaendert wuerde, ohne zu schreiben,
inkl. ob eine Profilzusammenfassungs-Notiz angelegt wuerde) - --apply fuer
den echten Lauf (nutzt dafuer denselben Code-Pfad wie ein echter CV-Upload,
CandidateService.auto_fill_from_cv, statt eigene Persistenz-Logik zu
duplizieren).

Usage (aus backend/, mit aktiviertem venv):

    python scripts/backfill_cv_fields.py
    python scripts/backfill_cv_fields.py --apply
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.operational import Document  # noqa: E402
from cc_crm.services.candidates import CandidateService  # noqa: E402
from cc_crm.services.cv_extraction import (  # noqa: E402
    CV_STRUCTURED_FIELDS,
    extract_text_from_bytes,
)
from cc_crm.services.storage import read_document_bytes  # noqa: E402

# Zentrale Registry aus cv_extraction.py statt einer eigenen, separat
# gepflegten Liste - siehe Kommentar dort zur Begruendung.
TARGET_FIELDS = list(CV_STRUCTURED_FIELDS)


def _is_empty(value: object) -> bool:
    """Generische "leer"-Pruefung fuer TARGET_FIELDS ueber beide bisher
    vorkommenden Feldtypen hinweg: String-Felder sind leer, wenn None (ihr
    DB-Default); Listenfelder wie fachliche_schwerpunkte sind NIE None
    (DB-Default ist []), sondern leer, wenn die Liste selbst leer ist. Eine
    reine "is None"-Pruefung wuerde ein leeres Listenfeld also nie als "zu
    befuellen" erkennen - ein zukuenftiges weiteres Listenfeld braucht dank
    dieser generischen Pruefung keine eigene Sonderbehandlung mehr."""
    if value is None:
        return True
    if isinstance(value, list):
        return len(value) == 0
    return False


def _candidates_with_cv_and_empty_fields(session: Session) -> list[Candidate]:
    candidate_ids_with_cv = set(
        session.scalars(
            select(Document.owner_id).where(
                Document.owner_type == "candidate", Document.document_type == "cv"
            )
        ).all()
    )
    if not candidate_ids_with_cv:
        return []
    candidates = session.scalars(
        select(Candidate).where(Candidate.id.in_(candidate_ids_with_cv))
    ).all()
    return [
        candidate
        for candidate in candidates
        if any(_is_empty(getattr(candidate, field)) for field in TARGET_FIELDS)
    ]


def _latest_cv_document(session: Session, candidate_id: uuid.UUID) -> Document | None:
    return session.scalar(
        select(Document)
        .where(
            Document.owner_type == "candidate",
            Document.owner_id == candidate_id,
            Document.document_type == "cv",
        )
        .order_by(Document.created_at.desc())
        .limit(1)
    )


def backfill(*, apply: bool) -> dict[str, int]:
    with SessionLocal() as session:
        candidates = _candidates_with_cv_and_empty_fields(session)
        service = CandidateService(session)
        candidates_updated = 0
        total_fields_filled = 0
        notes_created = 0

        for candidate in candidates:
            document = _latest_cv_document(session, candidate.id)
            if document is None:
                continue
            try:
                content = read_document_bytes(document.storage_key)
                cv_text = extract_text_from_bytes(document.filename, content)
                if apply:
                    # Gleicher Code-Pfad wie ein echter CV-Upload (Felder +
                    # cv_extraction_raw + ggf. Profilzusammenfassungs-Notiz,
                    # alles in einem Commit) - keine eigene Persistenz-Logik
                    # hier im Skript.
                    notes_before = len(service.notes.filtered(candidate_id=candidate.id))
                    suggestion = service.auto_fill_from_cv(
                        candidate.id, cv_text, filename=document.filename, content=content
                    )
                    notes_after = len(service.notes.filtered(candidate_id=candidate.id))
                    note_created = notes_after > notes_before
                else:
                    extracted, suggestion = service.preview_cv_extraction(
                        candidate.id, cv_text, filename=document.filename, content=content
                    )
                    note_created = service.would_create_profile_summary_note(
                        candidate.id, extracted
                    )
            except Exception as exception:  # noqa: BLE001 - Einzelner Kandidat darf den Lauf nicht abbrechen
                print(
                    f"  Übersprungen ({candidate.first_name} {candidate.last_name}, "
                    f"{document.filename}): {exception}"
                )
                continue

            updates = {
                field: value
                for field, value in suggestion.model_dump().items()
                if field in TARGET_FIELDS and not _is_empty(value)
            }
            if note_created:
                notes_created += 1
            if not updates and not note_created:
                continue

            candidates_updated += 1
            total_fields_filled += len(updates)
            action = "GESETZT" if apply else "WÜRDE SETZEN"
            label = f"{candidate.first_name} {candidate.last_name}"
            if candidate.candidate_number:
                label += f" (#{candidate.candidate_number})"
            note_hint = " + Profilzusammenfassungs-Notiz" if note_created else ""
            print(f"{action}: {label} -> {updates}{note_hint}")

        return {
            "candidates_checked": len(candidates),
            "candidates_updated": candidates_updated,
            "fields_filled": total_fields_filled,
            "notes_created": notes_created,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Tatsächlich schreiben (Default: Dry-Run)"
    )
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== CV-Feld-Backfill ({mode}) ===\n")
    stats = backfill(apply=args.apply)

    print("\n=== Zusammenfassung ===")
    checked, updated = stats["candidates_checked"], stats["candidates_updated"]
    print(f"Kandidaten mit CV + mindestens einem leeren Zielfeld geprüft: {checked}")
    print(f"Kandidaten mit mindestens einem befüllten Feld oder neuer Notiz: {updated}")
    if updated:
        average = stats["fields_filled"] / updated
        print(f"Felder je betroffenem Kandidat im Schnitt: {average:.1f}")
    verb = "angelegt" if args.apply else "würden angelegt"
    print(f"Profilzusammenfassungs-Notizen {verb}: {stats['notes_created']}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
