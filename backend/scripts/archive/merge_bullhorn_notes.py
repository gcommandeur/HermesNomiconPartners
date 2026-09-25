"""Hängt die 328 Bullhorn-Notizen als Timeline-Aktivitäten an die ECHTEN,
bereits importierten Kandidaten (aus import_master_candidates.py) an - per
Namens-Match. Legt KEINE neuen Kandidaten an (das war der erste, vom Nutzer
korrigierte Ansatz in import_bullhorn_notes.py - "ich will doch ALLE meine
kandidaten [aus der Excel] und die aus den notizen sollen halt noch um die
notizen erweitert werden").

Voraussetzung: import_master_candidates.py wurde bereits erfolgreich
ausgeführt (die 2675 echten Kandidaten existieren in der DB).

Ausführen:
    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\merge_bullhorn_notes.py

Matching-Logik:
- Bullhorn-Notizen haben nur ein einzelnes "About"-Textfeld mit dem vollen
  Namen (z.B. "Max Mustermann"), die echten Kandidaten haben getrennte
  First-Name/Surname-Spalten. Es wird sowohl "Vorname Nachname" als auch
  "Nachname Vorname" (normalisiert, klein geschrieben) gegen die Kandidaten
  abgeglichen, da Bullhorn-Notizen die Reihenfolge nicht konsistent handhaben.
- Eindeutige Treffer -> Activity wird angelegt.
- Kein Treffer ODER mehrdeutiger Treffer (mehrere Kandidaten mit demselben
  Namen) -> wird NICHT automatisch verknüpft, sondern am Ende als Liste
  ausgegeben, damit der Nutzer selbst entscheidet (kein Rateschritt bei
  echten Kandidatendaten).
"""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models import Activity, Candidate  # noqa: E402

CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "imports" / "bullhorn_notes.csv"
EXPECTED_HEADER = [
    "Department",
    "Note Author",
    "Date Note Added",
    "Type",
    "Note Action",
    "About",
    "Status",
    "Note Body",
]


def normalise(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip()).casefold()


def parse_date(raw: str) -> datetime:
    return datetime.strptime(raw.strip(), "%m/%d/%Y")


def clean_body(raw: str) -> str:
    return raw.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n").strip()


def load_rows() -> list[list[str]]:
    with open(CSV_PATH, encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header_index = next(i for i, row in enumerate(rows) if row[:1] == ["Department"])
    if rows[header_index] != EXPECTED_HEADER:
        raise SystemExit(
            f"CSV-Header hat sich geändert: {rows[header_index]!r} - erwartet "
            f"{EXPECTED_HEADER!r}. Breche ab statt möglicherweise falsch "
            "ausgerichtete Spalten zu importieren."
        )
    return [row for row in rows[header_index + 1 :] if len(row) >= 8]


def build_name_index(candidates: list[Candidate]) -> dict[str, list[Candidate]]:
    index: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        forward = normalise(f"{candidate.first_name} {candidate.last_name}")
        backward = normalise(f"{candidate.last_name} {candidate.first_name}")
        index[forward].append(candidate)
        if backward != forward:
            index[backward].append(candidate)
    return index


def main() -> None:
    rows = load_rows()
    print(f"Notizen gelesen: {len(rows)}")

    session = SessionLocal()
    try:
        candidates = list(session.query(Candidate).all())
        print(f"Echte Kandidaten in der DB: {len(candidates)}")
        name_index = build_name_index(candidates)

        matched = 0
        ambiguous_names: set[str] = set()
        unmatched_names: set[str] = set()

        for row in rows:
            _, _author, date_raw, _type, action, about, note_status, body = row
            key = normalise(about)
            matches = name_index.get(key, [])

            if len(matches) == 1:
                candidate = matches[0]
                action_label = action.strip() or "Note"
                subject = (
                    f"{action_label} ({note_status.strip()})"
                    if note_status.strip()
                    else action_label
                )
                session.add(
                    Activity(
                        candidate_id=candidate.id,
                        activity_type=action_label,
                        subject=subject[:240],
                        details=clean_body(body) or None,
                        occurred_at=parse_date(date_raw),
                    )
                )
                matched += 1
            elif len(matches) > 1:
                ambiguous_names.add(about.strip())
            else:
                unmatched_names.add(about.strip())

        session.commit()

        print("---")
        print(f"Als Timeline-Eintrag verknüpft: {matched}")
        print(
            f"Mehrdeutig (mehrere Kandidaten gleichen Namens, nicht verknüpft): "
            f"{len(ambiguous_names)}"
        )
        for name in sorted(ambiguous_names):
            print(f"  - {name}")
        print(f"Kein passender Kandidat gefunden (nicht verknüpft): {len(unmatched_names)}")
        for name in sorted(unmatched_names):
            print(f"  - {name}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
