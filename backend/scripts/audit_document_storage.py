"""Prüft für jedes Kandidaten-Dokument, ob das zugehörige Objekt im
Objektspeicher (S3-Bucket) tatsächlich existiert - reiner Lese-Vorgang,
schreibt nichts.

Hintergrund: live auf Produktion bestätigt (Python-Traceback direkt in der
DigitalOcean-App-Platform-Console), dass `generate_anonymous_profile` mit
`botocore.errorfactory.NoSuchKey` scheitert, weil die Datenbank-Zeile
(inkl. `storage_key`) existiert, das zugehörige Objekt im Produktions-Bucket
aber fehlt - vermutlich, weil bei der SQLite→Postgres-Migration bzw. dem
ursprünglichen lokalen Import die DB-Zeilen übernommen wurden, die
Dateien selbst aber nie in den Produktions-Bucket hochgeladen wurden (sie
liegen bislang nur lokal unter `backend/data/documents/`).

WICHTIG - zwei Durchläufe in zwei verschiedenen Umgebungen nötig:
Dieses Skript kann NICHT in einem einzigen Lauf alle drei Kategorien
ermitteln, weil die Produktions-S3-Zugangsdaten nur im Produktions-
Container verfügbar sind (DigitalOcean-Console), während die lokal
hochgeladenen Dateien (`backend/data/documents/`) nur auf dieser
Entwicklungsmaschine liegen - beides gleichzeitig ist technisch nicht an
einem Ort verfügbar, ohne echte Produktions-Zugangsdaten hier einzutragen
(bewusst vermieden - siehe Sicherheitsrichtlinie: keine Secrets aus der
Infrastruktur extrahieren).

Schritt 1 (in der DigitalOcean-Console der `hermescrm`-Komponente, hat
echte Produktions-DB- und S3-Zugangsdaten aus den App-Platform-
Umgebungsvariablen):

    python3 scripts/audit_document_storage.py --check-bucket

Gibt eine Liste der storage_keys aus, die NICHT im Produktions-Bucket
gefunden wurden (Kategorie "fehlt im Bucket") - Ausgabe kopieren und in
eine lokale Datei speichern, z.B. `missing_in_bucket.txt` (eine Zeile pro
storage_key, exakt wie ausgegeben).

Schritt 2 (lokal, hat Zugriff auf `backend/data/documents/`):

    python scripts/audit_document_storage.py --check-local missing_in_bucket.txt

Prüft für jeden storage_key aus Schritt 1, ob die Datei lokal existiert,
und gibt den finalen Bericht mit allen drei Kategorien aus:
  - Vorhanden im Bucket (kein Problem) - Zahl aus Schritt 1 abgeleitet.
  - Fehlt im Bucket, aber lokal vorhanden (reparierbar - Kandidat +
    lokaler Pfad werden aufgelistet für Schritt 2 des Hauptauftrags).
  - Fehlt sowohl im Bucket als auch lokal (Kandidat + Dokumentname werden
    aufgelistet, damit das CV ggf. manuell neu besorgt werden muss).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.core.config import get_settings  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.operational import Document  # noqa: E402
from cc_crm.services.storage import document_exists  # noqa: E402


def _candidate_documents(session: Session) -> list[Document]:
    return list(
        session.scalars(
            select(Document)
            .where(Document.owner_type == "candidate")
            .order_by(Document.created_at)
        ).all()
    )


def _candidate_label(session: Session, owner_id: object) -> str:
    candidate = session.get(Candidate, owner_id)
    if candidate is None:
        return f"(Kandidat {owner_id} nicht gefunden)"
    label = f"{candidate.first_name} {candidate.last_name}"
    if candidate.candidate_number:
        label += f" (#{candidate.candidate_number})"
    return label


def check_bucket() -> None:
    with SessionLocal() as session:
        documents = _candidate_documents(session)
        print(f"Geprüfte Kandidaten-Dokumente insgesamt: {len(documents)}\n")

        missing: list[Document] = []
        for document in documents:
            if not document_exists(document.storage_key):
                missing.append(document)

        present_count = len(documents) - len(missing)
        print(f"Vorhanden im Bucket: {present_count}")
        print(f"Fehlt im Bucket: {len(missing)}\n")

        if missing:
            print("--- storage_keys, die im Bucket fehlen (eine Zeile je Dokument) ---")
            for document in missing:
                print(document.storage_key)
            print("--- Ende der Liste ---\n")
            print(
                "Diese Ausgabe (nur die storage_key-Zeilen zwischen den beiden "
                "Trennzeilen) in eine lokale Datei kopieren und mit "
                "--check-local <datei> lokal weiterprüfen."
            )


def check_local(missing_keys_file: Path) -> None:
    storage_keys = [
        line.strip()
        for line in missing_keys_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"Zu prüfende storage_keys aus '{missing_keys_file}': {len(storage_keys)}\n")

    local_root = get_settings().resolved_documents_storage_dir
    with SessionLocal() as session:
        found_locally: list[tuple[str, Path]] = []
        missing_everywhere: list[str] = []

        for storage_key in storage_keys:
            # Der lokale Existenz-Check braucht KEINE lokale DB-Zeile - der
            # storage_key selbst ist bereits der vollstaendige relative Pfad
            # ("owner_type/owner_id/dateiname"). Eine DB-Zeile wird nur fuer
            # die huebschere Kandidaten-Beschriftung in der Ausgabe genutzt
            # (siehe unten) - ohne diese Trennung wurden storage_keys, die
            # es nur in der PRODUKTIONS-DB gibt (z.B. ein zweites, hier lokal
            # nie gesehenes Dokument desselben Kandidaten), bisher komplett
            # uebersprungen statt korrekt einer Kategorie zugeordnet.
            local_path = local_root / storage_key
            if local_path.is_file():
                found_locally.append((storage_key, local_path))
            else:
                missing_everywhere.append(storage_key)

        def _label_for(storage_key: str) -> str:
            document = session.scalar(select(Document).where(Document.storage_key == storage_key))
            if document is None:
                return "(kein lokaler DB-Eintrag - vermutlich nur in Produktion angelegt)"
            return f"{_candidate_label(session, document.owner_id)} - {document.filename}"

        print("=== Kategorie: fehlt im Bucket, aber lokal vorhanden (reparierbar) ===")
        print(f"Anzahl: {len(found_locally)}")
        for storage_key, local_path in found_locally:
            size = local_path.stat().st_size
            print(f"  {_label_for(storage_key)} ({size:,} Bytes) - {storage_key}")

        print(
            "\n=== Kategorie: fehlt sowohl im Bucket als auch lokal "
            "(nicht automatisch reparierbar) ==="
        )
        print(f"Anzahl: {len(missing_everywhere)}")
        for storage_key in missing_everywhere:
            print(f"  {_label_for(storage_key)} - {storage_key}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check-bucket",
        action="store_true",
        help="Schritt 1: in der Produktions-Console ausführen (prüft S3-Bucket).",
    )
    group.add_argument(
        "--check-local",
        metavar="DATEI",
        type=Path,
        help="Schritt 2: lokal ausführen (prüft backend/data/documents/ für die Liste "
        "aus Schritt 1).",
    )
    args = parser.parse_args()

    if args.check_bucket:
        check_bucket()
    else:
        check_local(args.check_local)


if __name__ == "__main__":
    main()
