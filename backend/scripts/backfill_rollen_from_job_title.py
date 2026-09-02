"""Einmaliges Nachziehen von rollen fuer bereits verarbeitete Kandidaten
(Zwischenthema "Rolle fehlt bei gefuelltem Jobtitel", dringender als der
Rest der Titelschutz-Feinarbeit): 443 von 1680 Kandidaten (Stand 26.08.)
haben job_title/qualification gefuellt, aber rollen leer - 439 davon nie
durch die CV-Extraktion gelaufen (kein cv_extraction_raw). Ursache: beim
manuellen Anlegen/Bearbeiten und bei der Sourcing-Uebernahme leitete bislang
NICHTS rollen aus job_title/qualification ab (nur der CV-Upload tat das,
ueber die LLM-Extraktion). Die Ursache selbst ist jetzt behoben (siehe
CandidateService.create()/update()/_maybe_derive_rollen) - dieses Skript
zieht die BESTEHENDEN Faelle einmalig nach.

Wiederverwendet dieselbe regelbasierte Ableitung wie die Ursachenbehebung
(cv_extraction.py::derive_rollen_from_text, KEIN LLM-Call, inkl. Tippfehler-
Toleranz und Titelschutz-Sicherung). Nur bisher LEERE rollen werden befuellt
- ein bereits gesetzter Wert wird NIE ueberschrieben (Nutzer-Vorgabe: "nur
ergaenzen, nie ueberschreiben").

Konservativ: fuer Kandidaten, bei denen die Ableitung KEIN Schluesselwort
findet, bleibt rollen leer - das ist kein Fehler dieses Skripts, sondern das
gewuenschte "im Zweifel keine Rolle vergeben statt einer falschen".

Dry-Run per Default, --apply-Gate, Review-CSV, Row-Level-Fehlerbehandlung -
gleiches Muster wie die anderen Backfill-Skripte in diesem Ordner.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/backfill_rollen_from_job_title.py
    python scripts/backfill_rollen_from_job_title.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import or_, select  # noqa: E402
from sqlalchemy.exc import DataError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.services.cv_extraction import derive_rollen_from_text  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "backfill_rollen_from_job_title_review.csv"

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "job_title",
    "qualification",
    "rollen_neu",
    "error",
]


def _candidates_to_check(session: Session) -> list[Candidate]:
    """job_title ODER qualification gefuellt UND rollen leer - genau die
    vom Nutzer nachgerechnete Gruppe (443 Kandidaten, Stand 26.08.)."""
    candidates = session.scalars(
        select(Candidate)
        .where(or_(Candidate.job_title.isnot(None), Candidate.qualification.isnot(None)))
        .order_by(Candidate.candidate_number)
    ).all()
    return [candidate for candidate in candidates if not candidate.rollen]


def backfill(*, apply: bool, candidates: list[Candidate]) -> dict[str, int]:
    with SessionLocal() as session:
        stats = {
            "candidates_checked": len(candidates),
            "candidates_updated": 0,
            "skipped_no_keyword_match": 0,
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
                "job_title": candidate.job_title or "",
                "qualification": candidate.qualification or "",
                "rollen_neu": "",
                "error": "",
            }
            try:
                derived = derive_rollen_from_text(candidate.job_title, candidate.qualification)
                if not derived:
                    stats["skipped_no_keyword_match"] += 1
                    rows.append(row)
                    continue

                row["rollen_neu"] = ", ".join(derived)
                stats["candidates_updated"] += 1

                if apply:
                    candidate.rollen = derived  # type: ignore[assignment]
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
    print(f"=== Rollen aus job_title/qualification nachziehen ({mode}) ===")
    print("Kein LLM-Call - reine Keyword-/Tippfehler-Ableitung.\n")
    print(f"Kandidaten mit job_title/qualification, aber leerem rollen: {len(candidates)}\n")

    stats = backfill(apply=args.apply, candidates=candidates)

    print("\n=== Zusammenfassung ===")
    print(f"Kandidaten geprüft: {stats['candidates_checked']}")
    verb = "bekommen eine Rolle" if args.apply else "würden eine Rolle bekommen"
    print(f"Davon {verb}: {stats['candidates_updated']}")
    print(f"Kein Schlüsselwort erkannt (bleibt leer): {stats['skipped_no_keyword_match']}")
    print(f"Übersprungen (DataError beim Schreiben): {stats['skipped_data_error']}")
    print(f"Fehler: {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
