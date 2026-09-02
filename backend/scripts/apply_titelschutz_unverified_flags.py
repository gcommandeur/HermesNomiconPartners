"""Setzt Candidate.rollen_unbestaetigt fuer die vom Audit gefundenen Faelle
(Konsolidierter Auftrag "Titelschutz-Korrektur ohne Datenverlust + Rollen-
Herkunft + Rechtsgebiete", Schritt 2: Markieren statt Aendern).

Wiederverwendet DIESELBE Beleg-Pruefung wie das read-only Audit (siehe
scripts/audit_titelschutz_unverified_roles.py::audit) - keine eigene, ggf.
abweichende Logik. Aendert NUR das neue Flag rollen_unbestaetigt auf True;
"rollen" selbst bleibt in JEDEM Fall unangetastet (kein Datenverlust, siehe
Auftrag). Ein bereits gesetztes Flag wird nicht erneut geloggt (idempotent -
ein wiederholter Lauf ist gefahrlos, z.B. nach neu hinzugekommenen
Kandidaten).

Schreibt pro tatsaechlich geaenderter Zeile einen AuditLog-Eintrag (action
"rollen_unbestaetigt_markiert", changed_by=None - automatisiert ausgeloest,
kein Nutzer dahinter, gleiches Muster wie andere Skript-Aktionen in diesem
Ordner), damit die Markierung in der Kandidaten-Aenderungshistorie sichtbar
ist.

Dry-Run per Default, --apply-Gate, Review-CSV, Row-Level-Fehlerbehandlung -
gleiches Muster wie die anderen Backfill-/Cleanup-Skripte in diesem Ordner.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/apply_titelschutz_unverified_flags.py
    python scripts/apply_titelschutz_unverified_flags.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
# Fuer den Import von scripts.audit_titelschutz_unverified_roles unten -
# noetig, damit "scripts" als (implizites Namespace-)Paket auffindbar ist,
# wenn dieses Skript direkt ausgefuehrt wird (python scripts/apply_....py
# legt sonst nur scripts/ selbst, nicht dessen Elternverzeichnis, auf
# sys.path). BEWUSST als qualifizierter "scripts."-Import (nicht ein bare
# "from audit_titelschutz_unverified_roles import audit") - ein bare Import
# wuerde unter Pytest ein ZWEITES, eigenstaendiges Modulobjekt neben
# scripts.audit_titelschutz_unverified_roles erzeugen, dessen SessionLocal
# von den Tests dort nicht mehr gepatcht werden koennte.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.exc import DataError  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.repositories.recruiting import AuditLogRepository  # noqa: E402
from scripts.audit_titelschutz_unverified_roles import audit  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "apply_titelschutz_unverified_flags_review.csv"

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "geschuetzte_rolle_ohne_beleg",
    "herkunft",
    "bereits_markiert",
    "error",
]


def apply_flags(*, apply: bool, rows: list[dict[str, object]]) -> dict[str, int]:
    with SessionLocal() as session:
        audit_logs = AuditLogRepository(session)
        stats = {
            "candidates_checked": len(rows),
            "candidates_newly_flagged": 0,
            "already_flagged": 0,
            "errors": 0,
            "skipped_data_error": 0,
        }
        out_rows: list[dict[str, object]] = []

        for row in rows:
            candidate_id = uuid.UUID(str(row["candidate_id"]))
            out_row: dict[str, object] = {
                "candidate_number": row["candidate_number"],
                "candidate_id": row["candidate_id"],
                "geschuetzte_rolle_ohne_beleg": row["geschuetzte_rolle_ohne_beleg"],
                "herkunft": row["herkunft"],
                "bereits_markiert": "",
                "error": "",
            }
            try:
                candidate = session.get(Candidate, candidate_id)
                assert candidate is not None
                if candidate.rollen_unbestaetigt:
                    out_row["bereits_markiert"] = "ja"
                    stats["already_flagged"] += 1
                    out_rows.append(out_row)
                    continue

                stats["candidates_newly_flagged"] += 1
                if apply:
                    candidate.rollen_unbestaetigt = True
                    audit_logs.create(
                        {
                            "entity_type": "candidate",
                            "entity_id": candidate.id,
                            "action": "rollen_unbestaetigt_markiert",
                            "changed_by": None,
                            "old_values": {"rollen_unbestaetigt": False},
                            "new_values": {
                                "rollen_unbestaetigt": True,
                                "geschuetzte_rolle_ohne_beleg": row["geschuetzte_rolle_ohne_beleg"],
                            },
                        }
                    )
                    try:
                        session.commit()
                    except DataError as exc:
                        session.rollback()
                        out_row["error"] = f"DataError beim Schreiben: {exc}"[:300]
                        stats["skipped_data_error"] += 1
                        stats["candidates_newly_flagged"] -= 1
            except Exception as exc:  # noqa: BLE001 - ein Kandidat darf den Lauf nicht abbrechen
                session.rollback()
                out_row["error"] = str(exc)[:300]
                stats["errors"] += 1
                stats["candidates_newly_flagged"] -= 1

            out_rows.append(out_row)

        _write_review_csv(out_rows)
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

    rows = audit()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Titelschutz: rollen_unbestaetigt setzen ({mode}) ===")
    print("rollen selbst wird NICHT geaendert - nur das Flag.\n")
    print(f"Vom Audit gefundene Faelle: {len(rows)}\n")

    stats = apply_flags(apply=args.apply, rows=rows)

    print("\n=== Zusammenfassung ===")
    print(f"Kandidaten geprüft: {stats['candidates_checked']}")
    verb = "markiert" if args.apply else "würden markiert"
    print(f"Neu {verb}: {stats['candidates_newly_flagged']}")
    print(f"Bereits markiert (übersprungen): {stats['already_flagged']}")
    print(f"Übersprungen (DataError beim Schreiben): {stats['skipped_data_error']}")
    print(f"Fehler: {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
