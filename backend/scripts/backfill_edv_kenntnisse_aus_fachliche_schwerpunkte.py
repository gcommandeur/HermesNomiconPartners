"""Trennt Software-/IT-Tool-Nennungen regelbasiert aus fachliche_schwerpunkte
heraus und verschiebt sie nach edv_kenntnisse - fuer Kandidaten, die bereits
VOR der Einfuehrung von edv_kenntnisse als eigenem Feld verarbeitet wurden
(cv_extraction_raw gesetzt, edv_kenntnisse aber leer). Betrifft insbesondere
die per import_rescued_cv_backfill_csv.py importierten 652 Kandidaten, wo
DATEV/SAP/etc. noch als Teil von fachliche_schwerpunkte drinstecken (allein
DATEV 297x, SAP 33x laut Auswertung der geretteten CSV).

KEIN LLM-Call - reine Vokabelliste (SOFTWARE_VOCABULARY unten) + Substring-
Match (case-insensitiv, Wortgrenzen) gegen die vorhandenen
fachliche_schwerpunkte-Eintraege. Ein Eintrag, der einen Vokabel-Treffer
enthaelt, wird KOMPLETT nach edv_kenntnisse verschoben (nicht aufgesplittet) -
die Prompt-Vorgabe fuer fachliche_schwerpunkte ("kurz gehalten, 2-6 Woerter")
macht gemischte Eintraege ("Umsatzsteuer und DATEV-Kenntnisse") in der Praxis
selten; die Vokabelliste ist bewusst erweiterbar, nicht als vollstaendig
gedacht.

Aktualisiert sowohl die abgeleiteten Spalten (fachliche_schwerpunkte/
edv_kenntnisse) ALS AUCH die entsprechenden Schluessel in
cv_extraction_raw - sonst wuerde ein spaeterer Blick ins Rohergebnis einen
Stand zeigen, der nicht mehr zu den abgeleiteten Spalten passt.

Dry-Run per Default, --apply-Gate, Review-CSV, Row-Level-Fehlerbehandlung.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/backfill_edv_kenntnisse_aus_fachliche_schwerpunkte.py
    python scripts/backfill_edv_kenntnisse_aus_fachliche_schwerpunkte.py --apply
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "edv_kenntnisse_backfill_review.csv"

# Erweiterbare Vokabelliste gaengiger Steuer-/WP-/Kanzlei-Software - bewusst
# NICHT als vollstaendig gedacht (siehe Modul-Docstring). Case-insensitiver
# Wortgrenzen-Match (siehe _matches_vocabulary), daher hier in der
# natuerlichen Schreibweise.
SOFTWARE_VOCABULARY: tuple[str, ...] = (
    "DATEV",
    "SAP",
    "Lexware",
    "Addison",
    "Sage",
    "WISO",
    "Agenda",
    "BMD",
    "Diamant",
    "RA-MICRO",
    "Advoware",
    "ELSTER",
    "MS Office",
    "Microsoft Office",
    "MS Excel",
    "Excel",
    "MS Word",
    "Word",
    "PowerPoint",
    "Outlook",
    "Wolters Kluwer",
)

_VOCABULARY_PATTERNS = [
    re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in SOFTWARE_VOCABULARY
]

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "fachliche_schwerpunkte_vorher",
    "fachliche_schwerpunkte_nachher",
    "edv_kenntnisse_vorher",
    "edv_kenntnisse_verschoben",
    "error",
]


def _matches_vocabulary(entry: str) -> bool:
    return any(pattern.search(entry) for pattern in _VOCABULARY_PATTERNS)


def split_software_entries(entries: list[str]) -> tuple[list[str], list[str]]:
    """Teilt eine fachliche_schwerpunkte-Liste in (Rest, Software-Treffer)."""
    remaining: list[str] = []
    moved: list[str] = []
    for entry in entries:
        if _matches_vocabulary(entry):
            moved.append(entry)
        else:
            remaining.append(entry)
    return remaining, moved


def _candidates_to_check(session: Session) -> list[Candidate]:
    """Kandidaten mit cv_extraction_raw (irgendeine Quelle - Hauptbackfill,
    CSV-Import, manueller Upload) UND noch leerem edv_kenntnisse -
    fachliche_schwerpunkte leer waere ohnehin nichts zu verschieben."""
    return list(
        session.scalars(
            select(Candidate)
            .where(Candidate.cv_extraction_raw.isnot(None))
            .order_by(Candidate.candidate_number)
        ).all()
    )


def backfill(*, apply: bool, candidates: list[Candidate]) -> dict[str, int]:
    with SessionLocal() as session:
        stats = {
            "candidates_checked": len(candidates),
            "candidates_updated": 0,
            "skipped_edv_kenntnisse_already_set": 0,
            "skipped_nothing_to_move": 0,
            "errors": 0,
        }
        rows: list[dict[str, object]] = []

        for candidate_stub in candidates:
            candidate = session.get(Candidate, candidate_stub.id)
            assert candidate is not None
            row: dict[str, object] = {
                "candidate_number": candidate.candidate_number or "",
                "candidate_id": str(candidate.id),
                "fachliche_schwerpunkte_vorher": "",
                "fachliche_schwerpunkte_nachher": "",
                "edv_kenntnisse_vorher": "",
                "edv_kenntnisse_verschoben": "",
                "error": "",
            }
            try:
                if candidate.edv_kenntnisse:
                    # Schon getrennt (z.B. von einem echten LLM-Lauf nach
                    # Einfuehrung des Felds) - nicht anfassen, verhindert
                    # eine doppelte/wiederholte Verschiebung bei erneutem
                    # Skriptlauf.
                    stats["skipped_edv_kenntnisse_already_set"] += 1
                    continue

                current = list(candidate.fachliche_schwerpunkte or [])
                remaining, moved = split_software_entries(current)
                row["fachliche_schwerpunkte_vorher"] = ", ".join(current)
                row["edv_kenntnisse_vorher"] = ", ".join(candidate.edv_kenntnisse or [])

                if not moved:
                    stats["skipped_nothing_to_move"] += 1
                    continue

                row["fachliche_schwerpunkte_nachher"] = ", ".join(remaining)
                row["edv_kenntnisse_verschoben"] = ", ".join(moved)
                stats["candidates_updated"] += 1

                if apply:
                    candidate.fachliche_schwerpunkte = remaining
                    candidate.edv_kenntnisse = moved
                    # cv_extraction_raw konsistent mitziehen - siehe
                    # Modul-Docstring.
                    raw = dict(candidate.cv_extraction_raw or {})
                    raw["fachliche_schwerpunkte"] = remaining
                    raw["edv_kenntnisse"] = moved
                    candidate.cv_extraction_raw = raw
                    session.commit()
            except Exception as exc:  # noqa: BLE001 - ein Kandidat darf den Lauf nicht abbrechen
                session.rollback()
                row["error"] = str(exc)[:300]
                stats["errors"] += 1

            rows.append(row)

        _write_review_csv(rows)
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
            "Datenbank-Backup ueber die DO-Console ausgefuehrt haben. !!!\n"
        )

    with SessionLocal() as session:
        candidates = _candidates_to_check(session)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== EDV-Kenntnisse-Backfill aus fachliche_schwerpunkte ({mode}) ===")
    print(f"Kandidaten mit cv_extraction_raw im Lauf: {len(candidates)}\n")

    stats = backfill(apply=args.apply, candidates=candidates)

    print("\n=== Zusammenfassung ===")
    print(f"Kandidaten geprüft: {stats['candidates_checked']}")
    verb = "aktualisiert" if args.apply else "würden aktualisiert"
    print(f"Kandidaten mit verschobenen Einträgen ({verb}): {stats['candidates_updated']}")
    print(f"Übersprungen (edv_kenntnisse bereits gesetzt): "
          f"{stats['skipped_edv_kenntnisse_already_set']}")
    print(f"Übersprungen (nichts zu verschieben): {stats['skipped_nothing_to_move']}")
    print(f"Fehler: {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
