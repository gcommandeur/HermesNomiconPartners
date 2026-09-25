"""Rueckwirkender Nachtrag fuer Kandidaten, die VOR dem approve_lead()-Fix
(services/sourcing.py) aus einem SourcingLead uebernommen wurden - der Fix
selbst wirkt nur vorwaerts, auf kuenftige approve()-Aufrufe.

Fuer jeden Kandidaten, der ueber SourcingLead.created_candidate_id mit einem
approved Lead verknuepft ist, wird dieselbe Logik wie im gefixten
approve_lead() rueckwirkend angewendet: current_employer_internal <- lead.
current_employer, job_title/rollen aus lead.raw_data abgeleitet, Telefon nur
falls in raw_data vorhanden. Ausschliesslich bisher LEERE Felder werden
befuellt - ein bereits gesetzter Wert (z.B. manuell nachgetragen) wird NIE
ueberschrieben.

Kein LLM-Call, keine Kosten - reine Ableitung aus bereits vorhandenen
lead.current_employer/lead.raw_data (siehe services/sourcing.py::
_job_title_from_raw_data/_rollen_from_text/_phone_from_raw_data, hier direkt
wiederverwendet statt dupliziert).

Row-Level-Fehlerbehandlung: ein kaputter Datensatz darf den Lauf nicht
abbrechen (gleiche Robustheit wie beim CSV-Import).

Dry-Run per Default, --apply fuer den echten Schreibvorgang.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/backfill_sourcing_candidates_structured_fields.py
    python scripts/backfill_sourcing_candidates_structured_fields.py --apply
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
from cc_crm.models.enums import SourcingLeadStatus  # noqa: E402
from cc_crm.models.sourcing_lead import SourcingLead  # noqa: E402
from cc_crm.services.sourcing import (  # noqa: E402
    _job_title_from_raw_data,
    _phone_from_raw_data,
    _rollen_from_text,
)

OUTPUT_PATH = Path(__file__).resolve().parent / "sourcing_candidates_structured_backfill_review.csv"

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "source_type",
    "current_employer_internal_aktuell",
    "current_employer_internal_aus_lead",
    "job_title_aktuell",
    "job_title_aus_lead",
    "rollen_aktuell",
    "rollen_aus_lead",
    "phone_aktuell",
    "phone_aus_lead",
    "felder_uebernommen",
    "error",
]


def _approved_candidate_lead_pairs(session: Session) -> list[tuple[Candidate, SourcingLead]]:
    rows = session.execute(
        select(Candidate, SourcingLead)
        .join(SourcingLead, SourcingLead.created_candidate_id == Candidate.id)
        .where(SourcingLead.status == SourcingLeadStatus.APPROVED)
        .order_by(Candidate.candidate_number)
    ).all()
    return [(row[0], row[1]) for row in rows]


def backfill(*, apply: bool, pairs: list[tuple[Candidate, SourcingLead]]) -> dict[str, int]:
    with SessionLocal() as session:
        stats = {"candidates_checked": len(pairs), "updated": 0, "skipped": 0, "errors": 0}
        rows: list[dict[str, object]] = []

        for candidate_stub, lead_stub in pairs:
            row: dict[str, object] = {
                "candidate_number": candidate_stub.candidate_number or "",
                "candidate_id": str(candidate_stub.id),
                "source_type": lead_stub.source_type.value if lead_stub.source_type else "",
                "current_employer_internal_aktuell": "",
                "current_employer_internal_aus_lead": "",
                "job_title_aktuell": "",
                "job_title_aus_lead": "",
                "rollen_aktuell": "",
                "rollen_aus_lead": "",
                "phone_aktuell": "",
                "phone_aus_lead": "",
                "felder_uebernommen": "",
                "error": "",
            }
            try:
                candidate = session.get(Candidate, candidate_stub.id)
                lead = session.get(SourcingLead, lead_stub.id)
                assert candidate is not None and lead is not None

                row["current_employer_internal_aktuell"] = candidate.current_employer_internal or ""
                row["job_title_aktuell"] = candidate.job_title or ""
                row["rollen_aktuell"] = ", ".join(candidate.rollen or [])
                row["phone_aktuell"] = candidate.phone or ""

                job_title = _job_title_from_raw_data(lead.raw_data)
                rollen = _rollen_from_text(job_title)
                phone = _phone_from_raw_data(lead.raw_data)

                applied: list[str] = []
                if not candidate.current_employer_internal and lead.current_employer:
                    row["current_employer_internal_aus_lead"] = lead.current_employer
                    applied.append("current_employer_internal")
                    if apply:
                        candidate.current_employer_internal = lead.current_employer
                if not candidate.job_title and job_title:
                    row["job_title_aus_lead"] = job_title
                    applied.append("job_title")
                    if apply:
                        candidate.job_title = job_title
                if not candidate.rollen and rollen:
                    row["rollen_aus_lead"] = ", ".join(r.value for r in rollen)
                    applied.append("rollen")
                    if apply:
                        candidate.rollen = rollen
                if not candidate.phone and phone:
                    row["phone_aus_lead"] = phone
                    applied.append("phone")
                    if apply:
                        candidate.phone = phone

                row["felder_uebernommen"] = ", ".join(applied)
                if applied:
                    stats["updated"] += 1
                    if apply:
                        session.commit()
                else:
                    stats["skipped"] += 1
            except Exception as exc:  # noqa: BLE001 - ein Datensatz darf den Lauf nicht abbrechen
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
            "Datenbank-Backup ueber die DO-Console ausgefuehrt haben (dieses Skript "
            "loest kein Backup aus). !!!\n"
        )

    with SessionLocal() as session:
        pairs = _approved_candidate_lead_pairs(session)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Rueckwirkender Nachtrag: Sourcing-Kandidaten ({mode}) ===")
    print("Kein LLM-Call - reine Ableitung aus lead.current_employer/lead.raw_data.\n")
    print(f"Ueber SourcingLead verknuepfte, approved Kandidaten: {len(pairs)}\n")

    stats = backfill(apply=args.apply, pairs=pairs)

    print("\n=== Zusammenfassung ===")
    print(f"Kandidaten geprüft: {stats['candidates_checked']}")
    verb = "aktualisiert" if args.apply else "würden aktualisiert"
    print(f"Kandidaten mit mindestens einer Änderung ({verb}): {stats['updated']}")
    print(f"Übersprungen (Lead lieferte nichts Neues): {stats['skipped']}")
    print(f"Fehlgeschlagen (Datensatz übersprungen): {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
