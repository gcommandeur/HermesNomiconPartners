"""Schritt 1 des CV-Reparse-Auftrags (Neufassung, urspruenglicher Plan
claude_code_prompt_cv_reparse_gesamt.md nicht mehr auffindbar): fuer
Kandidaten, deren letzte CV-Extraktion bereits als Rohergebnis in
Candidate.cv_extraction_raw liegt (siehe CandidateService.auto_fill_from_cv),
aber deren einzelne Spalten rollen/current_employer_internal/
berufliche_stationen/fachliche_schwerpunkte (noch) leer sind, werden die
fehlenden Werte direkt aus dem bereits vorhandenen JSON uebernommen - KEIN
erneuter LLM-Call, kein API-Guthaben-Verbrauch. Die JSON-Schluessel sind
identisch zu den Spaltennamen (siehe cv_extraction.py::CV_STRUCTURED_FIELDS
und services/candidates.py::auto_fill_from_cv, das cv_extraction_raw = das
komplette Extraktionsergebnis setzt).

Kandidaten OHNE cv_extraction_raw (aeltere CVs, extrahiert bevor dieses Feld
eingefuehrt wurde, oder Faelle mit fehlgeschlagenem LLM-Call) sind hier
NICHT erfasst - fuer die braucht es einen echten Re-Parse (Schritt 2, siehe
backfill_cv_rollen_und_schwerpunkte.py - deckt das bereits vollstaendig ab,
inkl. Review-CSV/--apply-Gate/Rate-Limiting/Row-Level-Fehlerbehandlung, kein
neues Skript noetig).

Row-Level-Fehlerbehandlung wie beim CSV-Import: ein kaputter/unerwartet
geformter Datensatz darf den Lauf nicht abbrechen.

Dry-Run per Default: schreibt NICHTS, nur eine Review-CSV + Zusammenfassung
(aktualisiert / uebersprungen [kein passendes Feld im JSON] / fehlgeschlagen).
--apply fuer den echten Schreibvorgang.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/backfill_rollen_from_cv_extraction_raw.py
    python scripts/backfill_rollen_from_cv_extraction_raw.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "cv_extraction_raw_backfill_review.csv"

# Reihenfolge = Spaltenname = JSON-Schluessel in cv_extraction_raw (identisch,
# siehe Modul-Docstring) - EINZIGE Stelle, die diese Zuordnung kennen muss.
TARGET_FIELDS = (
    "rollen",
    "current_employer_internal",
    "berufliche_stationen",
    "fachliche_schwerpunkte",
)

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "rollen_aktuell",
    "rollen_aus_raw",
    "current_employer_internal_aktuell",
    "current_employer_internal_aus_raw",
    "berufliche_stationen_aus_raw",
    "fachliche_schwerpunkte_aktuell",
    "fachliche_schwerpunkte_aus_raw",
    "felder_uebernommen",
    "error",
]


def _candidates_with_raw_and_gap(session: Session) -> list[Candidate]:
    """Kandidaten mit gesetztem cv_extraction_raw UND mindestens einem der
    vier Zielfelder leer - genau die vom Auftrag angefragte Gruppe 1."""
    candidates = session.scalars(
        select(Candidate)
        .where(Candidate.cv_extraction_raw.isnot(None))
        .order_by(Candidate.candidate_number)
    ).all()
    return [
        c
        for c in candidates
        if not c.rollen
        or not c.current_employer_internal
        or not c.berufliche_stationen
        or not c.fachliche_schwerpunkte
    ]


def backfill(*, apply: bool, candidates: list[Candidate]) -> dict[str, int]:
    with SessionLocal() as session:
        stats = {"candidates_checked": len(candidates), "updated": 0, "skipped": 0, "errors": 0}
        rows: list[dict[str, object]] = []

        for candidate_stub in candidates:
            row: dict[str, object] = {
                "candidate_number": candidate_stub.candidate_number or "",
                "candidate_id": str(candidate_stub.id),
                "rollen_aktuell": "",
                "rollen_aus_raw": "",
                "current_employer_internal_aktuell": "",
                "current_employer_internal_aus_raw": "",
                "berufliche_stationen_aus_raw": "",
                "fachliche_schwerpunkte_aktuell": "",
                "fachliche_schwerpunkte_aus_raw": "",
                "felder_uebernommen": "",
                "error": "",
            }
            try:
                candidate = session.get(Candidate, candidate_stub.id)
                assert candidate is not None
                raw = candidate.cv_extraction_raw or {}
                if not isinstance(raw, dict):
                    raise TypeError(f"cv_extraction_raw ist kein Objekt: {type(raw)!r}")

                row["rollen_aktuell"] = ", ".join(candidate.rollen or [])
                row["current_employer_internal_aktuell"] = candidate.current_employer_internal or ""
                row["fachliche_schwerpunkte_aktuell"] = ", ".join(
                    candidate.fachliche_schwerpunkte or []
                )

                applied_fields: list[str] = []
                # Nur ein bisher LEERES Zielfeld wird befuellt - ein bereits
                # gesetzter Wert (z.B. aus einer manuellen Korrektur) wird
                # NIE mit dem JSON ueberschrieben, auch nicht wenn das JSON
                # etwas anderes enthaelt.
                if not candidate.rollen and raw.get("rollen"):
                    row["rollen_aus_raw"] = ", ".join(raw["rollen"])
                    applied_fields.append("rollen")
                    if apply:
                        candidate.rollen = raw["rollen"]
                if not candidate.current_employer_internal and raw.get(
                    "current_employer_internal"
                ):
                    row["current_employer_internal_aus_raw"] = raw["current_employer_internal"]
                    applied_fields.append("current_employer_internal")
                    if apply:
                        candidate.current_employer_internal = raw["current_employer_internal"]
                if not candidate.berufliche_stationen and raw.get("berufliche_stationen"):
                    row["berufliche_stationen_aus_raw"] = str(raw["berufliche_stationen"])
                    applied_fields.append("berufliche_stationen")
                    if apply:
                        candidate.berufliche_stationen = raw["berufliche_stationen"]
                if not candidate.fachliche_schwerpunkte and raw.get("fachliche_schwerpunkte"):
                    row["fachliche_schwerpunkte_aus_raw"] = ", ".join(
                        raw["fachliche_schwerpunkte"]
                    )
                    applied_fields.append("fachliche_schwerpunkte")
                    if apply:
                        candidate.fachliche_schwerpunkte = raw["fachliche_schwerpunkte"]

                row["felder_uebernommen"] = ", ".join(applied_fields)
                if applied_fields:
                    stats["updated"] += 1
                    if apply:
                        session.commit()
                else:
                    # cv_extraction_raw war gesetzt, enthielt fuer die noch
                    # leeren Spalten aber selbst nichts (z.B. weil die
                    # Extraktion damals fuer genau diese Felder nichts fand).
                    stats["skipped"] += 1
            except Exception as exc:  # noqa: BLE001 - ein Datensatz darf den Lauf nicht abbrechen
                session.rollback()
                row["error"] = str(exc)[:300]
                stats["errors"] += 1

            rows.append(row)

        _write_review_csv(rows)
        return stats


def _write_review_csv(rows: list[dict[str, object]]) -> None:
    """Sichert eine vorhandene Review-CSV vorher mit Zeitstempel weg statt
    sie stillschweigend zu ueberschreiben (gleiches Muster wie
    backfill_cv_rollen_und_schwerpunkte.py)."""
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
        print(f"Vorhandene Review-CSV gesichert nach: {backup_path}")

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
    args = parser.parse_args()

    if args.apply:
        print(
            "!!! ACHTUNG: --apply schreibt echt in die Datenbank. Bitte VORHER ein "
            "Datenbank-Backup ueber die DO-Console ausgefuehrt haben (dieses Skript "
            "loest kein Backup aus). !!!\n"
        )

    with SessionLocal() as session:
        candidates = _candidates_with_raw_and_gap(session)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Backfill aus vorhandenem cv_extraction_raw ({mode}) ===")
    print("Kein einziger LLM-Call in diesem Lauf - reiner JSON-zu-Spalte-Transfer.\n")
    print(f"Kandidaten mit cv_extraction_raw + mind. 1 leerem Zielfeld: {len(candidates)}\n")

    stats = backfill(apply=args.apply, candidates=candidates)

    print("\n=== Zusammenfassung ===")
    print(f"Kandidaten geprüft: {stats['candidates_checked']}")
    verb = "aktualisiert" if args.apply else "würden aktualisiert"
    print(f"Kandidaten mit mindestens einer Änderung ({verb}): {stats['updated']}")
    print(f"Übersprungen (JSON lieferte für die leeren Felder nichts): {stats['skipped']}")
    print(f"Fehlgeschlagen (Datensatz übersprungen): {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
