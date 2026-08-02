"""ENDGUELTIGE, UNWIDERRUFLICHE Loeschung des ungeprueften CC-Archiv-Altbestands
(1357 Kandidaten) - Ergebnis des Reviews in cc_archiv_deletion_review.csv
(siehe audit_cc_archiv_deletion_candidates.py), von Gege final freigegeben
nach eigener Gegenrechnung.

Verarbeitet GENAU die Zeilen mit wuerde_geloescht=="ja" aus der Review-CSV:
loescht pro Kandidat zuerst alle Document-Zeilen + die zugehoerigen
S3-Objekte (kein DB-Fremdschluessel dafuer, siehe Audit-Skript-Docstring -
muss explizit passieren), danach die Candidate-Zeile selbst (CASCADE fuer
Notes/Activities/Tasks, SET NULL fuer CalendarEvents/SourcingLeads/
EmailDraftLogs, siehe models/*.py).

BEWUSST DAUERHAFT AUSGESCHLOSSEN (hartkodiert als zweite Sicherheitsebene,
zusaetzlich zur bereits korrekten "nein"-Markierung in der Review-CSV - siehe
_HARD_EXCLUDED_MASTER_CSV_IDS unten fuer die Begruendung je ID):
  - 206, 692, 803, 941, 1695, 1742: candidate_number wurde nach dem alten
    Archiv-Export fuer einen VOELLIG ANDEREN, echten Kandidaten neu vergeben
    (die urspruengliche Archiv-Zeile enthielt gar keinen Personennamen,
    sondern Firmen-/Ortsangaben wie "Oerlikon BarmagRemscheid" oder
    "Allianz TechnologyMunchen") - ein Loeschen nach ID wuerde hier die
    falsche Person treffen.
  - 1817 (Christian Schwarze): hat einen laufenden Interview-Prozess
    (candidate_submissions, Status "interview") - technisch ohnehin durch
    ondelete=RESTRICT blockiert, zusaetzlich aber bewusst dauerhaft von
    Gege ausgenommen, AUCH wenn der Prozess irgendmal abgeschlossen/
    abgebrochen wird. Bei einem spaeteren Aufraeumlauf NICHT automatisch
    wieder in eine Loeschliste aufnehmen, ohne das erneut mit Gege
    abzustimmen.

Dry-Run per Default: schreibt NICHTS, simuliert nur und schreibt ein
Ergebnis-Log. --apply fuer den echten Loeschvorgang (DB + S3).

Das eigentliche --apply-Ausfuehren gegen die Produktions-DB macht
AUSSCHLIESSLICH Gege selbst ueber die DO-Console - dieses Skript loest
weder automatisch aus noch macht es selbst ein Backup.

Usage (aus backend/, mit aktiviertem venv):

    # Dry-Run (Standard) - nichts wird geschrieben, nur simuliert + geloggt.
    python scripts/delete_cc_archiv_altbestand.py

    # Echte Loeschung - ERST nach vollstaendigem DB-Backup ueber die
    # DO-Console (siehe Warnhinweis unten, dieses Skript loest kein Backup
    # aus).
    python scripts/delete_cc_archiv_altbestand.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.operational import Document  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.services.storage import delete_document_bytes  # noqa: E402

REVIEW_CSV = Path(__file__).resolve().parent / "cc_archiv_deletion_review.csv"
LOG_OUTPUT_PATH = Path(__file__).resolve().parent / "cc_archiv_deletion_result.csv"

# Siehe Modul-Docstring fuer die Begruendung je ID - zweite, hartkodierte
# Sicherheitsebene zusaetzlich zur Review-CSV, damit diese IDs auch bei einem
# versehentlich veralteten/manipulierten CSV-Stand nie geloescht werden.
_HARD_EXCLUDED_MASTER_CSV_IDS = {"206", "692", "803", "941", "1695", "1742", "1817"}

LOG_FIELDS = [
    "master_csv_id",
    "candidate_id",
    "first_name",
    "last_name",
    "document_storage_keys",
    "status",
    "grund",
]


def _load_rows_to_delete() -> list[dict[str, str]]:
    with REVIEW_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if row["wuerde_geloescht"].strip().lower() == "ja"]


def delete_candidate(
    session: Session, csv_row: dict[str, str], *, apply: bool
) -> dict[str, object]:
    master_csv_id = csv_row["master_csv_id"].strip()
    log_row: dict[str, object] = {
        "master_csv_id": master_csv_id,
        "candidate_id": "",
        "first_name": csv_row["csv_first_name"],
        "last_name": csv_row["csv_surname"],
        "document_storage_keys": "",
        "status": "",
        "grund": "",
    }

    if master_csv_id in _HARD_EXCLUDED_MASTER_CSV_IDS:
        log_row["status"] = "uebersprungen"
        log_row["grund"] = "hartkodiert dauerhaft ausgeschlossen (siehe Modul-Docstring)"
        return log_row

    # Erneute Live-Pruefung zum Zeitpunkt des --apply-Laufs, nicht blind der
    # (ggf. seither veralteten) Review-CSV vertrauen - der Audit-Lauf kann
    # Tage/Wochen zurueckliegen.
    candidate = session.scalar(select(Candidate).where(Candidate.candidate_number == master_csv_id))
    if candidate is None:
        log_row["status"] = "uebersprungen"
        log_row["grund"] = "candidate_number zum Zeitpunkt des Laufs nicht (mehr) in der DB"
        return log_row

    log_row["candidate_id"] = str(candidate.id)
    log_row["first_name"] = candidate.first_name
    log_row["last_name"] = candidate.last_name

    name_still_matches = (
        candidate.first_name or ""
    ).strip().casefold() == csv_row["db_first_name"].strip().casefold() and (
        candidate.last_name or ""
    ).strip().casefold() == csv_row["db_last_name"].strip().casefold()
    if not name_still_matches:
        log_row["status"] = "uebersprungen"
        log_row["grund"] = (
            "Name weicht vom Stand der Review-CSV ab - seither veraendert, manuell pruefen"
        )
        return log_row

    has_submission = (
        session.scalar(
            select(CandidateSubmission.id).where(CandidateSubmission.candidate_id == candidate.id)
        )
        is not None
    )
    if has_submission:
        log_row["status"] = "uebersprungen"
        log_row["grund"] = (
            "hat inzwischen (seit dem Audit-Lauf) eine Submission/einen Prozess - RESTRICT"
        )
        return log_row

    documents = session.scalars(
        select(Document).where(
            Document.owner_type == "candidate", Document.owner_id == candidate.id
        )
    ).all()
    storage_keys = [d.storage_key for d in documents]
    log_row["document_storage_keys"] = "; ".join(storage_keys)

    if not apply:
        log_row["status"] = "wuerde_geloescht"
        return log_row

    try:
        for document in documents:
            delete_document_bytes(document.storage_key)
            session.delete(document)
        session.flush()
        session.delete(candidate)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        log_row["status"] = "fehler"
        log_row["grund"] = f"IntegrityError beim Loeschen: {str(exc)[:200]}"
        return log_row

    log_row["status"] = "geloescht"
    return log_row


def run(*, apply: bool) -> dict[str, int]:
    rows_to_process = _load_rows_to_delete()
    stats = {
        "total": len(rows_to_process),
        "deleted": 0,
        "would_delete": 0,
        "skipped": 0,
        "errors": 0,
    }
    log_rows: list[dict[str, object]] = []

    with SessionLocal() as session:
        for csv_row in rows_to_process:
            log_row = delete_candidate(session, csv_row, apply=apply)
            log_rows.append(log_row)
            if log_row["status"] == "geloescht":
                stats["deleted"] += 1
            elif log_row["status"] == "wuerde_geloescht":
                stats["would_delete"] += 1
            elif log_row["status"] == "fehler":
                stats["errors"] += 1
            else:
                stats["skipped"] += 1

    with LOG_OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_FIELDS)
        writer.writeheader()
        for row in log_rows:
            writer.writerow(row)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Tatsaechlich loeschen (Default: Dry-Run)"
    )
    args = parser.parse_args()

    if args.apply:
        print(
            "!!! ACHTUNG: --apply loescht ENDGUELTIG und UNWIDERRUFLICH Kandidaten-Datensaetze "
            "UND deren CV-Dateien aus dem S3-Speicher. Ein vollstaendiges Datenbank-Backup ueber "
            "die DO-Console ist ZWINGEND erforderlich, BEVOR dieser Lauf gestartet wird - nicht "
            "optional. Dieses Skript loest selbst KEIN Backup aus. !!!\n"
        )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== CC-Archiv-Altbestand Loeschung ({mode}) ===")
    excluded_sorted = sorted(_HARD_EXCLUDED_MASTER_CSV_IDS, key=int)
    print(f"Hartkodiert dauerhaft ausgeschlossen: {excluded_sorted}\n")

    stats = run(apply=args.apply)

    print("=== Zusammenfassung ===")
    print(f"Zeilen aus Review-CSV mit wuerde_geloescht=ja: {stats['total']}")
    if args.apply:
        print(f"Tatsaechlich geloescht (Kandidat + Dokumente/S3): {stats['deleted']}")
    else:
        print(f"Wuerden geloescht werden (Kandidat + Dokumente/S3): {stats['would_delete']}")
    print(f"Uebersprungen (Ausschluss/Drift seit Audit-Lauf): {stats['skipped']}")
    print(f"Fehler: {stats['errors']}")
    print(f"\nErgebnis-Log: {LOG_OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geloescht.")
        print("Nach Pruefung: --apply erneut ausfuehren, um tatsaechlich zu loeschen.")


if __name__ == "__main__":
    main()
