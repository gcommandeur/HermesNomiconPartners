"""Bereinigung bestehender rechtsgebiete-Eintraege bei Nicht-Jurist:innen
(Konsolidierter Auftrag "Titelschutz-Korrektur ohne Datenverlust + Rollen-
Herkunft + Rechtsgebiete", Schritt 4).

rechtsgebiete ist als Unterscheidungsmerkmal fuer Jurist:innen gedacht -
wenn "Steuerrecht" bei fast jedem Steuerberater steht, ist es als Filter
wertlos (man filtert damit auf die halbe Kandidatendatenbank). Die
Ableitung selbst wird bereits an zwei Stellen auf rechtsanwalt/
rechtsfachangestellte eingegrenzt (siehe cv_extraction.py::
_normalize_rechtsgebiete fuer neue Extraktionen und
derive_rechtsgebiete_from_schwerpunkte fuer den Backfill,
backfill_ausbildung_kuerzung_abschluesse_rechtsgebiete.py) - dieses Skript
raeumt die dadurch nicht erfassten BESTEHENDEN Eintraege auf, die vor dieser
Eingrenzung entstanden sind.

Unkritisch: die fachliche Einordnung eines Nicht-Juristen (z.B. "Steuerrecht"
bei einem Steuerberater) steht bereits redundant in fachliche_schwerpunkte -
das Leeren von rechtsgebiete hier verliert also keine Information.

Aktualisiert sowohl die Spalte rechtsgebiete ALS AUCH den entsprechenden
Schluessel in cv_extraction_raw (falls vorhanden) - gleiches Prinzip wie
backfill_ausbildung_kuerzung_abschluesse_rechtsgebiete.py, sonst wuerde ein
spaeterer Blick ins Rohergebnis einen Stand zeigen, der nicht mehr zur
Spalte passt.

Dry-Run per Default, --apply-Gate, Review-CSV, Row-Level-Fehlerbehandlung
(DataError beim Schreiben eines Kandidaten -> rollback() + Zeile
uebersprungen, Lauf laeuft weiter) - gleiches Muster wie die anderen
Backfill-/Cleanup-Skripte in diesem Ordner.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/cleanup_rechtsgebiete_non_legal_roles.py
    python scripts/cleanup_rechtsgebiete_non_legal_roles.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import DataError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.services.cv_extraction import JURISTISCHE_ROLLEN  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "cleanup_rechtsgebiete_non_legal_roles_review.csv"

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "rollen",
    "rechtsgebiete_vorher",
    "fachliche_schwerpunkte",
    "error",
]


def _candidates_to_check(session: Session) -> list[Candidate]:
    """Kandidaten mit gesetztem rechtsgebiete UND ohne juristische Rolle -
    genau die Gruppe, die zu bereinigen ist. Ein direkter SQL-Filter auf den
    JSON-Inhalt waere DB-spezifisch (Postgres vs. SQLite) - stattdessen
    grob auf "rechtsgebiete nicht leer" vorfiltern und die Rollenpruefung in
    Python machen (Kandidatenzahl ist unkritisch fuer diesen einmaligen
    Lauf)."""
    candidates = session.scalars(
        select(Candidate)
        .where(Candidate.rechtsgebiete.isnot(None))
        .order_by(Candidate.candidate_number)
    ).all()
    return [
        candidate
        for candidate in candidates
        if candidate.rechtsgebiete and not (JURISTISCHE_ROLLEN & set(candidate.rollen or []))
    ]


def cleanup(*, apply: bool, candidates: list[Candidate]) -> dict[str, int]:
    with SessionLocal() as session:
        stats = {
            "candidates_checked": len(candidates),
            "candidates_updated": 0,
            "errors": 0,
            "skipped_data_error": 0,
        }
        rows: list[dict[str, object]] = []

        for candidate_stub in candidates:
            candidate = session.get(Candidate, candidate_stub.id)
            assert candidate is not None
            row: dict[str, object] = {
                "candidate_number": candidate.candidate_number or "",
                "candidate_id": str(candidate.id),
                "rollen": ", ".join(candidate.rollen or []),
                "rechtsgebiete_vorher": ", ".join(candidate.rechtsgebiete or []),
                "fachliche_schwerpunkte": ", ".join(candidate.fachliche_schwerpunkte or []),
                "error": "",
            }
            try:
                stats["candidates_updated"] += 1
                if apply:
                    candidate.rechtsgebiete = []
                    if candidate.cv_extraction_raw is not None:
                        raw = dict(candidate.cv_extraction_raw)
                        if "rechtsgebiete" in raw:
                            raw["rechtsgebiete"] = []
                            candidate.cv_extraction_raw = raw
                    try:
                        session.commit()
                    except DataError as exc:
                        session.rollback()
                        row["error"] = f"DataError beim Schreiben: {exc}"[:300]
                        stats["skipped_data_error"] += 1
                        stats["candidates_updated"] -= 1
            except Exception as exc:  # noqa: BLE001 - ein Kandidat darf den Lauf nicht abbrechen
                session.rollback()
                row["error"] = str(exc)[:300]
                stats["errors"] += 1
                stats["candidates_updated"] -= 1

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
    print(f"=== Bereinigung rechtsgebiete bei Nicht-Jurist:innen ({mode}) ===")
    print("Kein LLM-Call - reine Rollen-Pruefung.\n")
    print(
        f"Betroffene Kandidaten (rechtsgebiete gesetzt, keine juristische Rolle): "
        f"{len(candidates)}\n"
    )

    stats = cleanup(apply=args.apply, candidates=candidates)

    print("\n=== Zusammenfassung ===")
    print(f"Kandidaten geprüft: {stats['candidates_checked']}")
    verb = "bereinigt" if args.apply else "würden bereinigt"
    print(f"Kandidaten {verb}: {stats['candidates_updated']}")
    print(f"Übersprungen (DataError beim Schreiben): {stats['skipped_data_error']}")
    print(f"Fehler: {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
