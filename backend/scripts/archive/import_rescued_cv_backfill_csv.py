"""Importiert die geretteten Ergebnisse aus einem fruehen, abgebrochenen
Lauf von backfill_cv_rollen_und_schwerpunkte.py, dessen Ergebnisse ohne den
damaligen Persistenz-Fix sonst komplett verloren gewesen waeren - der Lauf
selbst hat NICHTS in die DB geschrieben (Dry-Run macht volle, bezahlte
LLM-Calls, verwirft die Ergebnisse aber am Ende), einzig die Review-CSV
konnte aus dem S3-Bucket gerettet werden (Key siehe RESCUE_S3_KEY unten).

KEIN LLM-Call in diesem Skript - reiner CSV-zu-Spalte-Transfer aus bereits
vorhandenen *_vorschlag-Werten. Zeilen mit gesetztem "error" werden
uebersprungen (siehe Auswertung: 458 Guthaben-Fallback, 16 leerer CV-Text,
2 defekte PDFs - fuer die gibt es in der geretteten CSV keinen verwertbaren
Vorschlag). Fuer jede uebernommene Zeile wird zusaetzlich zu den
abgeleiteten Spalten ein rekonstruiertes cv_extraction_raw gesetzt, damit
diese Kandidaten kuenftig von backfill_cv_rollen_und_schwerpunkte.py
uebersprungen werden (siehe dortiger Persistenz-Fix) - die Rekonstruktion
ist NICHT das vollstaendige urspruengliche LLM-Ergebnis (die CSV enthaelt
z.B. kein edv_kenntnisse/erfahrungen_zusammenfassung, beide gab es zum
Zeitpunkt des geretteten Laufs noch nicht bzw. sind nicht Teil der
Review-CSV-Spalten), sondern nur das, was tatsaechlich in der CSV steht -
ausreichend, um den Kandidaten als bearbeitet zu markieren.

Gleiches Feld-fuer-Feld-Prinzip wie der Hauptbackfill: ein Wert
"(behalten - kein neuer Vorschlag)" bzw. eine leere Spalte bedeutet "Feld
nicht anfassen", der bestehende DB-Wert bleibt erhalten statt mit leer
ueberschrieben zu werden.

Dry-Run per Default: schreibt NICHTS, nur eine Review-Ausgabe + Zusammenfassung
(importiert / uebersprungen [Fehler in der Originalzeile] / uebersprungen
[Kandidat nicht gefunden oder bereits mit cv_extraction_raw] / fehlgeschlagen
[kaputte Zeile]). --apply fuer den echten Schreibvorgang. Row-Level-
Fehlerbehandlung: eine kaputte Zeile darf den Lauf nicht abbrechen.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/import_rescued_cv_backfill_csv.py
    python scripts/import_rescued_cv_backfill_csv.py --apply

    # Lokale Kopie der CSV statt aus S3 (z.B. wenn bereits heruntergeladen).
    python scripts/import_rescued_cv_backfill_csv.py --csv-path pfad/zur.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy.exc import DataError  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.services.storage import read_document_bytes  # noqa: E402

# S3-Key der geretteten Review-CSV (siehe Modul-Docstring) - liegt im selben
# Bucket wie die Kandidaten-Dokumente, read_document_bytes() liest per Key
# unabhaengig davon, ob es sich um ein "echtes" Document handelt.
RESCUE_S3_KEY = "rescue/cv_rollen_backfill_review.csv"

OUTPUT_PATH = Path(__file__).resolve().parent / "rescued_cv_backfill_import_review.csv"

# Sentinel-Wert aus backfill_cv_rollen_und_schwerpunkte.py fuer "kein neuer
# Vorschlag fuer dieses Feld" - wie eine leere Spalte zu behandeln.
NO_SUGGESTION_MARKER = "(behalten - kein neuer Vorschlag)"

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "status",
    "rollen_importiert",
    "current_employer_internal_importiert",
    "berufliche_stationen_importiert",
    "fachliche_schwerpunkte_importiert",
    "ausbildung_titel_importiert",
    "error",
]


def _parse_list_field(value: str) -> list[str]:
    if not value or value == NO_SUGGESTION_MARKER:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_optional_field(value: str) -> str | None:
    if not value or value == NO_SUGGESTION_MARKER:
        return None
    return value


def _parse_stationen_field(value: str) -> list[dict[str, Any]]:
    if not value or value == NO_SUGGESTION_MARKER:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("berufliche_stationen_vorschlag ist kein JSON-Array.")
    return parsed


def _fetch_csv_rows(csv_path: Path | None) -> list[dict[str, str]]:
    if csv_path is not None:
        raw_bytes = csv_path.read_bytes()
    else:
        raw_bytes = read_document_bytes(RESCUE_S3_KEY)
    text = raw_bytes.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def import_rows(*, apply: bool, rows: list[dict[str, str]]) -> dict[str, int]:
    with SessionLocal() as session:
        stats = {
            "rows_checked": len(rows),
            "imported": 0,
            "skipped_row_had_error": 0,
            "skipped_candidate_not_found_or_already_done": 0,
            "failed": 0,
            # DataError beim Schreiben (z.B. Wert zu lang) - Zeile
            # uebersprungen per rollback(), Import laeuft mit den restlichen
            # Zeilen weiter statt abzustuerzen.
            "skipped_data_error": 0,
        }
        review_rows: list[dict[str, object]] = []

        for row in rows:
            review_row: dict[str, object] = {
                "candidate_number": row.get("candidate_number", ""),
                "candidate_id": row.get("candidate_id", ""),
                "status": "",
                "rollen_importiert": "",
                "current_employer_internal_importiert": "",
                "berufliche_stationen_importiert": "",
                "fachliche_schwerpunkte_importiert": "",
                "ausbildung_titel_importiert": "",
                "error": "",
            }

            if row.get("error"):
                review_row["status"] = "uebersprungen (Fehler in Originalzeile)"
                review_row["error"] = row["error"][:300]
                stats["skipped_row_had_error"] += 1
                review_rows.append(review_row)
                continue

            try:
                candidate_id = uuid.UUID(row["candidate_id"])
            except (KeyError, ValueError) as exc:
                review_row["status"] = "fehlgeschlagen (candidate_id ungueltig)"
                review_row["error"] = str(exc)[:300]
                stats["failed"] += 1
                review_rows.append(review_row)
                continue

            candidate = session.get(Candidate, candidate_id)
            if candidate is None or candidate.cv_extraction_raw is not None:
                review_row["status"] = (
                    "uebersprungen (Kandidat nicht gefunden)"
                    if candidate is None
                    else "uebersprungen (bereits mit cv_extraction_raw)"
                )
                stats["skipped_candidate_not_found_or_already_done"] += 1
                review_rows.append(review_row)
                continue

            try:
                rollen = _parse_list_field(row.get("rollen_vorschlag", ""))
                employer = _parse_optional_field(row.get("current_employer_internal_vorschlag", ""))
                stationen = _parse_stationen_field(row.get("berufliche_stationen_vorschlag", ""))
                schwerpunkte = _parse_list_field(row.get("fachliche_schwerpunkte_vorschlag", ""))
                ausbildung = _parse_optional_field(row.get("ausbildung_titel_vorschlag", ""))
            except (ValueError, TypeError) as exc:  # noqa: BLE001
                review_row["status"] = "fehlgeschlagen (Zeile nicht parsebar)"
                review_row["error"] = str(exc)[:300]
                stats["failed"] += 1
                review_rows.append(review_row)
                continue

            review_row["rollen_importiert"] = ", ".join(rollen)
            review_row["current_employer_internal_importiert"] = employer or ""
            review_row["berufliche_stationen_importiert"] = json.dumps(
                stationen, ensure_ascii=False
            )
            review_row["fachliche_schwerpunkte_importiert"] = ", ".join(schwerpunkte)
            review_row["ausbildung_titel_importiert"] = ausbildung or ""

            if not apply:
                review_row["status"] = "wuerde importiert"
                review_rows.append(review_row)
                stats["imported"] += 1
                continue

            # Rekonstruiertes Rohergebnis - siehe Modul-Docstring, warum es
            # nicht das vollstaendige urspruengliche LLM-Ergebnis ist.
            candidate.cv_extraction_raw = {
                "rollen": rollen,
                "current_employer_internal": employer,
                "berufliche_stationen": stationen,
                "fachliche_schwerpunkte": schwerpunkte,
                "ausbildung_titel": ausbildung,
                "edv_kenntnisse": [],
                "source": "rescue_csv_import",
                "source_csv_confidence": row.get("confidence", ""),
            }
            # Gleiches Feld-fuer-Feld-Prinzip wie der Hauptbackfill: nur ein
            # tatsaechlich vorhandener Vorschlag ueberschreibt die Spalte.
            if rollen:
                candidate.rollen = rollen  # type: ignore[assignment]
            if employer:
                candidate.current_employer_internal = employer
            if stationen:
                candidate.berufliche_stationen = stationen
            if schwerpunkte:
                candidate.fachliche_schwerpunkte = schwerpunkte
            if ausbildung:
                candidate.ausbildung_titel = ausbildung
            try:
                session.commit()
            except DataError as exc:
                # Ohne rollback() wuerden alle nachfolgenden commits in
                # dieser Session ebenfalls fehlschlagen und den gesamten
                # Import abstuerzen lassen - stattdessen nur diese Zeile
                # ueberspringen und mit der naechsten weitermachen.
                session.rollback()
                review_row["status"] = "uebersprungen (DataError beim Schreiben)"
                review_row["error"] = str(exc)[:300]
                stats["skipped_data_error"] += 1
                review_rows.append(review_row)
                continue

            review_row["status"] = "importiert"
            review_rows.append(review_row)
            stats["imported"] += 1

        _write_review_csv(review_rows)
        return stats


def _write_review_csv(rows: list[dict[str, object]]) -> None:
    if OUTPUT_PATH.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.stem}_backup_{timestamp}.csv")
        suffix = 2
        while backup_path.exists():
            backup_path = OUTPUT_PATH.with_name(
                f"{OUTPUT_PATH.stem}_backup_{timestamp}_{suffix}.csv"
            )
            suffix += 1
        OUTPUT_PATH.rename(backup_path)
        print(f"Vorhandene Review-Datei gesichert nach: {backup_path}")

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Tatsächlich schreiben (Default: Dry-Run)"
    )
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=None,
        help="Lokale CSV-Datei statt aus S3 (RESCUE_S3_KEY) laden",
    )
    args = parser.parse_args()

    if args.apply:
        print(
            "!!! ACHTUNG: --apply schreibt echt in die Datenbank. Bitte VORHER ein "
            "Datenbank-Backup ueber die DO-Console ausgefuehrt haben. !!!\n"
        )

    source = str(args.csv_path) if args.csv_path else f"S3://{RESCUE_S3_KEY}"
    print(f"Quelle: {source}")
    rows = _fetch_csv_rows(args.csv_path)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Import gerettete CV-Backfill-Ergebnisse ({mode}) ===")
    print(f"Zeilen in der CSV: {len(rows)}\n")

    stats = import_rows(apply=args.apply, rows=rows)

    print("\n=== Zusammenfassung ===")
    print(f"Zeilen geprüft: {stats['rows_checked']}")
    verb = "importiert" if args.apply else "würden importiert"
    print(f"{verb}: {stats['imported']}")
    print(f"Übersprungen (Fehler in Originalzeile, z.B. Guthaben/leerer CV): "
          f"{stats['skipped_row_had_error']}")
    print(
        f"Übersprungen (Kandidat nicht gefunden oder bereits mit cv_extraction_raw): "
        f"{stats['skipped_candidate_not_found_or_already_done']}"
    )
    print(f"Fehlgeschlagen (Zeile nicht verarbeitbar): {stats['failed']}")
    print(
        f"Übersprungen (DataError beim Schreiben, z.B. Wert zu lang): "
        f"{stats['skipped_data_error']}"
    )
    print(f"\nReview-Datei: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-Datei prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
