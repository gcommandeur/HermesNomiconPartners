"""Convert a LinkedIn data export CSV into the CC CRM candidates import template.

LinkedIn does not offer a general recruiting API for ordinary accounts, and
scraping linkedin.com violates its Terms of Service, so this script does not
talk to LinkedIn at all. Instead it converts a file YOU already exported
through LinkedIn's own legitimate "Get a copy of your data" feature
(Settings & Privacy -> Data privacy -> Get a copy of your data -> Connections)
or a Sales Navigator / Recruiter list export into the column layout that
POST /api/v1/import/candidates/preview expects, so it can go through the
existing, validated CSV import (duplicate detection, error report, explicit
confirmation before commit).

Usage:

    python scripts/convert_linkedin_export.py Connections.csv candidates_ready.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Case-insensitive source column name -> our candidates template column.
COLUMN_ALIASES = {
    "first name": "first_name",
    "last name": "last_name",
    "email address": "email",
    "position": "job_title",
    "company": "qualification",
    "location": "city",
}
TARGET_COLUMNS = [
    "candidate_number",
    "first_name",
    "last_name",
    "email",
    "phone",
    "job_title",
    "qualification",
    "postal_code",
    "city",
    "salary_expectation",
    "notice_period",
    "status",
]


def find_header_row(lines: list[str]) -> int:
    """LinkedIn's export prepends a few notes/blank lines before the real header."""
    for index, line in enumerate(lines):
        lowered = line.lower()
        if "first name" in lowered and "last name" in lowered:
            return index
    raise ValueError("Konnte keine LinkedIn-Kopfzeile mit 'First Name'/'Last Name' finden.")


def convert(source_path: Path, target_path: Path) -> int:
    raw_lines = source_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    header_index = find_header_row(raw_lines)
    reader = csv.DictReader(raw_lines[header_index:])

    written = 0
    with target_path.open("w", encoding="utf-8-sig", newline="") as target_file:
        writer = csv.DictWriter(target_file, fieldnames=TARGET_COLUMNS)
        writer.writeheader()
        for source_row in reader:
            mapped = {"status": "active"}
            for source_col, value in source_row.items():
                target_col = COLUMN_ALIASES.get((source_col or "").strip().lower())
                if target_col and value:
                    mapped[target_col] = value.strip()
            if not mapped.get("first_name") or not mapped.get("last_name"):
                continue
            writer.writerow(mapped)
            written += 1
    return written


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    source_path, target_path = Path(sys.argv[1]), Path(sys.argv[2])
    count = convert(source_path, target_path)
    print(f"{count} Kandidaten nach {target_path} konvertiert.")
    print("Naechster Schritt: ueber den Import-Assistenten (Kandidaten) oder")
    print("POST /api/v1/import/candidates/preview hochladen und pruefen, dann bestaetigen.")


if __name__ == "__main__":
    main()
