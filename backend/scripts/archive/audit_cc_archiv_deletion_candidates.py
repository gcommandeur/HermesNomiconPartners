"""READ-ONLY Analyse fuer die geplante endgueltige Loeschung des ungeprueften
CC-Archiv-Altbestands (1506 von 1512 Kandidaten, 6 mit Namenstreffer in
Bullhorn/Downloads-Ordner/-Archiv bleiben unangetastet, siehe
backend/scripts/data/cc_archiv_keep_overlap.csv).

Schreibt/loescht NICHTS - reine Bestandsaufnahme gegen die Live-DB (nicht
gegen die beiliegende, ggf. veraltete CSV vertrauen) als Basis fuer die
manuelle Freigabe, bevor das eigentliche Loesch-Skript geschrieben wird.

Verifizierte Annahme (siehe Auftrag): master_csv_id aus der historischen
Import-CSV == candidate_number im aktuellen Candidate-Modell - stichprobenartig
gegen 6 Werte (3x to_archive, 3x keep_overlap) direkt in der DB bestaetigt.

Ermittelte Fremdschluessel-Beziehungen auf candidates (Code-Audit, nicht
geraten - siehe models/*.py):
  - candidate_submissions.candidate_id -> RESTRICT (blockiert die Loeschung
    komplett, WENN AUCH NUR EINE Submission existiert - unabhaengig vom
    Status, auch eine laengst abgeschlossene/abgebrochene. Das bestehende
    CandidateService.delete() faengt das als IntegrityError/ConflictError ab,
    loescht also so einen Kandidaten gar nicht erst.)
  - notes.candidate_id, activities.candidate_id, tasks.candidate_id -> CASCADE
    (werden beim Loeschen automatisch mitentfernt, rein kandidat-interne
    Artefakte, kein Grund zur Einzelpruefung)
  - calendar_events.candidate_id, sourcing_leads.duplicate_of_candidate_id,
    sourcing_leads.created_candidate_id, email_draft_logs.candidate_id ->
    SET NULL (bleiben als loser Datensatz ohne Kandidatenbezug stehen)
  - documents.owner_id (owner_type="candidate") -> KEIN DB-Fremdschluessel
    (polymorphe Zuordnung ueber owner_type/owner_id) - wird weder kaskadiert
    noch blockiert. CandidateService.delete() raeumt diese NICHT auf (nur
    CandidateService.anonymize() tut das) - das geplante Loesch-Skript muss
    Document-Zeilen UND die zugehoerigen S3-Objekte EXPLIZIT selbst entfernen.
  - audit_logs.entity_id -> polymorph (entity_type="candidate"), kein FK,
    bleibt als historischer Log-Eintrag bewusst bestehen (kein Blocker).

Usage (aus backend/, mit aktiviertem venv):

    python scripts/audit_cc_archiv_deletion_candidates.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy import func, select  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.activity import Activity  # noqa: E402
from cc_crm.models.calendar_event import CalendarEvent  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.note import Note  # noqa: E402
from cc_crm.models.operational import Document, EmailDraftLog  # noqa: E402
from cc_crm.models.sourcing_lead import SourcingLead  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.models.task import Task  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TO_ARCHIVE_CSV = DATA_DIR / "cc_archiv_to_archive.csv"
KEEP_OVERLAP_CSV = DATA_DIR / "cc_archiv_keep_overlap.csv"
OUTPUT_PATH = Path(__file__).resolve().parent / "cc_archiv_deletion_review.csv"
S3_KEYS_OUTPUT_PATH = Path(__file__).resolve().parent / "cc_archiv_deletion_s3_keys.txt"

CSV_FIELDS = [
    "master_csv_id",
    "csv_first_name",
    "csv_surname",
    "gefunden_in_db",
    "db_first_name",
    "db_last_name",
    "name_stimmt_ueberein",
    "hat_submissions_prozesse",
    "submission_status_liste",
    "notes_anzahl",
    "activities_anzahl",
    "tasks_anzahl",
    "calendar_events_anzahl",
    "sourcing_lead_referenzen",
    "email_draft_logs_anzahl",
    "document_anzahl",
    "document_storage_keys",
    "wuerde_geloescht",
    "grund_falls_nein",
]


def _normalize(value: str | None) -> str:
    return (value or "").strip().casefold()


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def audit() -> None:
    to_archive_rows = _load_csv(TO_ARCHIVE_CSV)
    keep_overlap_rows = _load_csv(KEEP_OVERLAP_CSV)
    keep_overlap_ids = {row["master_csv_id"].strip() for row in keep_overlap_rows}

    accidental_overlap = [
        row["master_csv_id"]
        for row in to_archive_rows
        if row["master_csv_id"].strip() in keep_overlap_ids
    ]
    if accidental_overlap:
        print(
            f"!!! ACHTUNG: {len(accidental_overlap)} master_csv_id(s) stehen in BEIDEN "
            f"CSVs: {accidental_overlap} - diese werden aus der Loeschliste entfernt, "
            "bitte manuell pruefen!"
        )

    duplicate_ids_in_to_archive = {
        mid for mid in (row["master_csv_id"].strip() for row in to_archive_rows)
        if [r["master_csv_id"].strip() for r in to_archive_rows].count(mid) > 1
    }
    if duplicate_ids_in_to_archive:
        print(
            f"!!! ACHTUNG: master_csv_id(s) mehrfach in cc_archiv_to_archive.csv: "
            f"{sorted(duplicate_ids_in_to_archive)}"
        )

    rows: list[dict[str, object]] = []
    all_storage_keys: list[str] = []
    stats = {
        "checked": 0,
        "not_found_in_db": 0,
        "name_mismatch": 0,
        "blocked_by_submission": 0,
        "skipped_keep_overlap": 0,
        "would_delete": 0,
    }

    with SessionLocal() as session:
        for csv_row in to_archive_rows:
            master_csv_id = csv_row["master_csv_id"].strip()
            stats["checked"] += 1

            if master_csv_id in keep_overlap_ids:
                stats["skipped_keep_overlap"] += 1
                continue

            row: dict[str, object] = {
                "master_csv_id": master_csv_id,
                "csv_first_name": csv_row["first_name"],
                "csv_surname": csv_row["surname"],
                "gefunden_in_db": "nein",
                "db_first_name": "",
                "db_last_name": "",
                "name_stimmt_ueberein": "",
                "hat_submissions_prozesse": "",
                "submission_status_liste": "",
                "notes_anzahl": "",
                "activities_anzahl": "",
                "tasks_anzahl": "",
                "calendar_events_anzahl": "",
                "sourcing_lead_referenzen": "",
                "email_draft_logs_anzahl": "",
                "document_anzahl": "",
                "document_storage_keys": "",
                "wuerde_geloescht": "nein",
                "grund_falls_nein": "",
            }

            candidate = session.scalar(
                select(Candidate).where(Candidate.candidate_number == master_csv_id)
            )
            if candidate is None:
                stats["not_found_in_db"] += 1
                row["grund_falls_nein"] = "candidate_number nicht (mehr) in der DB gefunden"
                rows.append(row)
                continue

            row["gefunden_in_db"] = "ja"
            row["db_first_name"] = candidate.first_name
            row["db_last_name"] = candidate.last_name

            name_matches = _normalize(candidate.first_name) == _normalize(
                csv_row["first_name"]
            ) and _normalize(candidate.last_name) == _normalize(csv_row["surname"])
            row["name_stimmt_ueberein"] = "ja" if name_matches else "nein"
            if not name_matches:
                stats["name_mismatch"] += 1

            submissions = session.scalars(
                select(CandidateSubmission).where(
                    CandidateSubmission.candidate_id == candidate.id
                )
            ).all()
            row["hat_submissions_prozesse"] = "ja" if submissions else "nein"
            row["submission_status_liste"] = ", ".join(s.status.value for s in submissions)

            notes_count = session.scalar(
                select(func.count()).select_from(Note).where(Note.candidate_id == candidate.id)
            )
            activities_count = session.scalar(
                select(func.count())
                .select_from(Activity)
                .where(Activity.candidate_id == candidate.id)
            )
            tasks_count = session.scalar(
                select(func.count()).select_from(Task).where(Task.candidate_id == candidate.id)
            )
            calendar_count = session.scalar(
                select(func.count())
                .select_from(CalendarEvent)
                .where(CalendarEvent.candidate_id == candidate.id)
            )
            sourcing_refs = session.scalar(
                select(func.count())
                .select_from(SourcingLead)
                .where(
                    (SourcingLead.duplicate_of_candidate_id == candidate.id)
                    | (SourcingLead.created_candidate_id == candidate.id)
                )
            )
            email_draft_count = session.scalar(
                select(func.count())
                .select_from(EmailDraftLog)
                .where(EmailDraftLog.candidate_id == candidate.id)
            )
            documents = session.scalars(
                select(Document).where(
                    Document.owner_type == "candidate", Document.owner_id == candidate.id
                )
            ).all()

            row["notes_anzahl"] = notes_count
            row["activities_anzahl"] = activities_count
            row["tasks_anzahl"] = tasks_count
            row["calendar_events_anzahl"] = calendar_count
            row["sourcing_lead_referenzen"] = sourcing_refs
            row["email_draft_logs_anzahl"] = email_draft_count
            row["document_anzahl"] = len(documents)
            row["document_storage_keys"] = "; ".join(d.storage_key for d in documents)
            all_storage_keys.extend(d.storage_key for d in documents)

            reasons = []
            if not name_matches:
                reasons.append(
                    f"Name in DB weicht ab (CSV: {csv_row['first_name']} {csv_row['surname']}, "
                    f"DB: {candidate.first_name} {candidate.last_name}) - candidate_number "
                    "vermutlich zwischenzeitlich neu vergeben, manuell pruefen"
                )
            if submissions:
                reasons.append(
                    f"hat {len(submissions)} Submission(s)/Prozess(e) "
                    f"({row['submission_status_liste']}) - DB blockiert Loeschung per RESTRICT, "
                    "unabhaengig vom Status. Einzeln pruefen, ob der Prozess mitgeloescht "
                    "werden soll."
                )
                stats["blocked_by_submission"] += 1

            if reasons:
                row["wuerde_geloescht"] = "nein"
                row["grund_falls_nein"] = " | ".join(reasons)
            else:
                row["wuerde_geloescht"] = "ja"
                stats["would_delete"] += 1

            rows.append(row)

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with S3_KEYS_OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        for key in all_storage_keys:
            handle.write(key + "\n")

    print("=== CC-Archiv-Loeschung: Read-only Audit gegen die Live-DB ===")
    print(f"Geprueft (cc_archiv_to_archive.csv): {stats['checked']}")
    print(
        f"Davon aus Versehen auch in keep_overlap.csv (uebersprungen): "
        f"{stats['skipped_keep_overlap']}"
    )
    print(f"In der DB nicht (mehr) gefunden: {stats['not_found_in_db']}")
    print(f"Namensabweichung ggue. CSV: {stats['name_mismatch']}")
    print(f"Blockiert durch vorhandene Submission(s)/Prozess(e): {stats['blocked_by_submission']}")
    print(f"Wuerde geloescht werden (Kandidat + Dokumente/S3): {stats['would_delete']}")
    print(f"\nS3-/Storage-Objekte, die mitgeloescht wuerden: {len(all_storage_keys)}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    print(f"S3-Objekt-Liste: {S3_KEYS_OUTPUT_PATH}")
    print(
        "\nHinweis: dieser Lauf prueft gegen die LOKALE Dev-Datenbank (cc_crm_local.db) - "
        "die beste hier verfuegbare Naeherung an die Live-Produktions-DB, auf die kein "
        "direkter Zugriff besteht. Vor dem tatsaechlichen Loeschen in Produktion sollte "
        "Gege denselben Audit-Lauf (oder zumindest eine Stichprobe) gegen die echte "
        "Produktions-DB wiederholen."
    )


if __name__ == "__main__":
    audit()
