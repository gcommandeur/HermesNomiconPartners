"""Benennt hochgeladene Kandidaten-Dokumente im Bucket UND in der DB auf die
Konvention "Kandidaten-Nr." um, statt der bisherigen
"<zufälliger Hash>_<Originalname>"-Form (z.B. "ddd4ce82_1823_Kroll_Simon.pdf"
-> "1823.pdf").

WICHTIG: muss dort laufen, wo GLEICHZEITIG echter Schreibzugriff auf die
Produktions-Datenbank UND den Produktions-Bucket besteht - das ist nur die
DigitalOcean-App-Platform-Console der `hermescrm`-Komponente (dieselbe
Umgebung, in der auch der Diagnose-Traceback und `audit_document_storage.py
--check-bucket` liefen). Nicht lokal ausführbar (lokal fehlt der
Produktions-DB-Zugriff, siehe Chat-Verlauf).

Namenskonvention (vorher per --dry-run gegen die echte Produktions-DB
geprüft, nicht angenommen):
  - Genau 1 Dokument für den Kandidaten:      "<Kandidaten-Nr>.<ext>"
  - Mehrere Dokumente, unterschiedliche Typen: "<Kandidaten-Nr>_<document_type>.<ext>"
  - Mehrere Dokumente, GLEICHER Typ (z.B. 2x "cv" durch Re-Upload, siehe
    Kandidat 1823/Simon Kroll auf Produktion): zusätzlich fortlaufende Nummer
    nach Upload-Datum sortiert: "<Kandidaten-Nr>_<document_type>_2.<ext>", usw.
    Das älteste Dokument je Typ bekommt KEINE Nummer (bleibt "..._cv.<ext>"),
    ab dem zweiten "_2", "_3", ...

Kandidaten ohne candidate_number werden übersprungen (können nicht sinnvoll
umbenannt werden) und am Ende separat aufgelistet.

Prüft vor jedem Schreiben:
  - Kollisionsfreiheit über ALLE geplanten Zielnamen hinweg (bricht ohne zu
    schreiben ab, falls zwei Dokumente auf denselben Zielschlüssel fallen
    würden).
  - Dass das Quellobjekt im Bucket tatsächlich existiert (überspringt sonst
    mit Warnung, statt zu crashen - z.B. die auf Produktion bekannte
    verwaiste Kandidat-1823-Dupliakt-Zeile ohne Bucket-Objekt).

Ablauf beim Umbenennen (--apply): S3 copy_object auf den neuen Schlüssel,
per head_object verifizieren, dann DB-Zeile (storage_key + filename)
aktualisieren, erst danach das alte S3-Objekt löschen - in dieser
Reihenfolge geht bei einem Abbruch mittendrin nie eine Datei komplett
verloren (im schlimmsten Fall existiert sie kurzzeitig doppelt).

Dry-Run per Default. Usage (in der Produktions-Console, aus /app/backend):

    python3 scripts/rename_documents_to_candidate_number.py
    python3 scripts/rename_documents_to_candidate_number.py --apply
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.core.config import get_settings  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.operational import Document  # noqa: E402
from cc_crm.services.storage import (  # noqa: E402
    _safe_type_segment,  # noqa: F401 - re-exportiert fuer bestehende Tests/Aufrufer dieses Skripts
    candidate_document_filenames,
    document_exists,
    has_generic_filename,
    rename_document_bytes,
)


def plan_renames(session: Session) -> tuple[list[tuple[Document, str]], list[Document]]:
    """Gibt (geplante Umbenennungen, Kandidaten ohne candidate_number) zurück.
    Jede geplante Umbenennung ist (Document, neuer_storage_key). Die eigentliche
    Namenskonvention lebt in services/storage.py::candidate_document_filenames -
    von dort UND vom Upload-Endpunkt gemeinsam genutzt, damit beide garantiert
    dieselbe Logik anwenden."""
    documents = list(
        session.scalars(
            select(Document)
            .where(Document.owner_type == "candidate")
            .order_by(Document.owner_id, Document.created_at)
        ).all()
    )

    by_candidate: dict[object, list[Document]] = defaultdict(list)
    for document in documents:
        by_candidate[document.owner_id].append(document)

    renames: list[tuple[Document, str]] = []
    skipped_no_number: list[Document] = []

    for owner_id, docs in by_candidate.items():
        candidate = session.get(Candidate, owner_id)
        if candidate is None or not candidate.candidate_number:
            skipped_no_number.extend(docs)
            continue

        filenames_by_id = candidate_document_filenames(list(docs), candidate.candidate_number)
        by_id = {document.id: document for document in docs}
        for document_id, new_filename in filenames_by_id.items():
            document = by_id[document_id]
            renames.append((document, f"candidate/{owner_id}/{new_filename}"))

    return renames, skipped_no_number


def rename_documents(*, apply: bool) -> None:
    settings = get_settings()
    if not settings.s3_bucket:
        print("FEHLER: kein S3-Bucket konfiguriert (CC_CRM_S3_BUCKET) - abgebrochen.")
        raise SystemExit(1)

    with SessionLocal() as session:
        renames, skipped_no_number = plan_renames(session)

        print(f"Kandidaten-Dokumente insgesamt geplant zu prüfen: {len(renames)}")
        print(f"Übersprungen (Kandidat ohne candidate_number): {len(skipped_no_number)}")
        for document in skipped_no_number:
            print(f"  KEINE KANDIDATEN-NR: owner_id={document.owner_id} - {document.filename}")

        # Kollisionsfreiheit über ALLE geplanten Zielschlüssel hinweg prüfen,
        # bevor irgendetwas geschrieben wird.
        target_keys = [new_key for _, new_key in renames]
        duplicates = {key for key in target_keys if target_keys.count(key) > 1}
        if duplicates:
            print(
                "\nFEHLER: Kollidierende Zielschlüssel erkannt - "
                "kein einziger Schreibvorgang ausgeführt:"
            )
            for key in sorted(duplicates):
                print(f"  {key}")
            raise SystemExit(1)

        renamed = 0
        skipped_missing_object = 0
        skipped_already_named = 0
        failed = 0

        for document, new_key in renames:
            old_key = document.storage_key
            if old_key == new_key:
                skipped_already_named += 1
                continue

            if not document_exists(old_key):
                skipped_missing_object += 1
                print(f"  ÜBERSPRUNGEN (Quellobjekt fehlt im Bucket): {old_key}")
                continue

            action = "UMBENANNT" if apply else "WÜRDE UMBENENNEN"
            print(f"  {action}: {old_key} -> {new_key}")

            if not apply:
                continue

            try:
                rename_document_bytes(old_storage_key=old_key, new_storage_key=new_key)

                new_filename = Path(new_key).name
                document.storage_key = new_key
                document.filename = new_filename
                document.has_generic_filename = has_generic_filename(new_filename)
                session.commit()
                renamed += 1
            except Exception as exception:  # noqa: BLE001 - ein Fehlschlag darf den Lauf nicht abbrechen
                session.rollback()
                failed += 1
                print(f"    FEHLER bei {old_key}: {exception}")

        print("\n=== Zusammenfassung ===")
        print(f"geplante Umbenennungen: {len(renames)}")
        print(f"bereits korrekt benannt (übersprungen): {skipped_already_named}")
        print(f"Quellobjekt fehlt im Bucket (übersprungen): {skipped_missing_object}")
        print(f"ohne candidate_number (übersprungen): {len(skipped_no_number)}")
        print(f"umbenannt: {renamed}")
        print(f"fehlgeschlagen: {failed}")
        if not apply:
            print("\nDies war ein Dry-Run - nichts wurde umbenannt.")
            print("Mit --apply erneut ausführen, um zu übernehmen.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--apply", action="store_true", help="Tatsächlich umbenennen (Default: Dry-Run)"
    )
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Dokument-Umbenennung auf Kandidaten-Nr.-Konvention ({mode}) ===\n")
    rename_documents(apply=args.apply)


if __name__ == "__main__":
    main()
