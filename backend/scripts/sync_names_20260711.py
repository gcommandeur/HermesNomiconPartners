"""Namens-Resync aus der geprüften Master-Datei CVs_master_updated_corrected_
20260711.csv (Phase L, Punkt 4). Nachfolgerin von
CVs_master_updated_corrected_20260710.csv - enthält zusätzliche, bereits
außerhalb dieses Skripts geprüfte Korrekturen an First Name/Surname.

Rollenteilung: dieses Skript trifft KEINE eigenen Entscheidungen über Namen,
es synchronisiert nur mechanisch, was in der Datei steht:

1. Für jede Zeile mit Match_Konfidenz beginnend "corrected-": falls
   First Name/Surname vom aktuellen DB-Wert (Match über candidate_number ==
   CSV-Spalte "id") abweicht, wird first_name/last_name auf den CSV-Wert
   gesetzt (nur diese beiden Felder).
2. Für jede Zeile mit Data_Action beginnend "review:smashed_name": der Name
   bleibt unangetastet, es wird nur ein sichtbarer Hinweis an
   freitext_notizen angehängt (gleiches Feld/Muster wie bereits in
   import_master_candidates.py für unsichere Namen verwendet) - keine
   Löschung, keine Dubletten-Markierung.

Ausführen:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\sync_names_20260711.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models import Candidate  # noqa: E402

CSV_PATH = Path(
    r"C:\Users\comma\Claude\Projects\Commandeur Consulting GmbH"
    r"\CVs_master_updated_corrected_20260711.csv"
)

REVIEW_NOTE = "Name unklar — CV manuell prüfen (Match_Konfidenz-Review 2026-07-11)"


def main() -> None:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    session = SessionLocal()
    candidates_by_number = {c.candidate_number: c for c in session.query(Candidate).all()}

    updated: list[tuple[str, str, str, str, str]] = []
    flagged: list[tuple[str, str, str]] = []
    not_found: list[str] = []

    for row in rows:
        candidate_number = row["id"].strip()
        candidate = candidates_by_number.get(candidate_number)

        confidence = row["Match_Konfidenz"].strip()
        data_action = row["Data_Action"].strip()

        if confidence.startswith("corrected-"):
            if candidate is None:
                not_found.append(candidate_number)
                continue
            csv_first = row["First Name"].strip()
            csv_last = row["Surname"].strip()
            if candidate.first_name != csv_first or candidate.last_name != csv_last:
                updated.append(
                    (
                        candidate_number,
                        f"{candidate.first_name} {candidate.last_name}",
                        f"{csv_first} {csv_last}",
                        confidence,
                        "",
                    )
                )
                candidate.first_name = csv_first
                candidate.last_name = csv_last
        elif data_action.startswith("review:smashed_name"):
            if candidate is None:
                not_found.append(candidate_number)
                continue
            if REVIEW_NOTE not in (candidate.freitext_notizen or ""):
                candidate.freitext_notizen = (
                    f"{candidate.freitext_notizen}\n\n{REVIEW_NOTE}"
                    if candidate.freitext_notizen
                    else REVIEW_NOTE
                )
                flagged.append(
                    (candidate_number, f"{candidate.first_name} {candidate.last_name}", data_action)
                )

    session.commit()

    print(f"Aktualisierte Namen: {len(updated)}")
    for candidate_number, before, after, confidence, _ in updated[:10]:
        print(f"  #{candidate_number}: {before!r} -> {after!r} ({confidence})")
    if len(updated) > 10:
        print(f"  ... ({len(updated) - 10} weitere)")

    print(f"\nNeu markierte Review-Faelle: {len(flagged)}")
    for candidate_number, name, data_action in flagged[:10]:
        print(f"  #{candidate_number}: {name!r} ({data_action})")
    if len(flagged) > 10:
        print(f"  ... ({len(flagged) - 10} weitere)")

    if not_found:
        print(f"\nWARNUNG: {len(not_found)} candidate_number aus der CSV nicht in der DB gefunden: "
              f"{not_found[:20]}{' ...' if len(not_found) > 20 else ''}")

    session.close()


if __name__ == "__main__":
    main()
