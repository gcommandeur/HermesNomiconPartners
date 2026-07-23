"""Laedt den statischen PLZ<->Ort-Referenzdatensatz fuer Deutschland
(Phase 4b, bidirektionales Ort/PLZ-Matching bei der Kanzleien-Suche).

Quelle: backend/data/reference/de_postal_codes.csv - eine auf eindeutige
(PLZ, Ort, Stadtbezirk, Ortsteil)-Kombinationen verdichtete Teilmenge von
`src/de/osm/streets.updated.csv` aus dem Repository
https://github.com/openpotato/openplzapi.data (Auswertung von OpenStreetMap-
Daten fuer Deutschland, Stand des Downloads: 2026-07-23).

Lizenz: ODbL-1.0 (Open Database License) - (c) OpenStreetMap-Mitwirkende.
Diese Zuordnung wird ausschliesslich intern fuer die Kanzleien-Suche
verwendet und nicht als Datenbank an Dritte weitergegeben/veroeffentlicht,
daher greift die ODbL-Share-Alike-Pflicht hier nicht - Attribution erfolgt
hier sowie im Docstring von models/postal_locality.py.

Idempotent: loescht bei jedem Lauf zunaechst alle vorhandenen Zeilen und
laedt den aktuellen CSV-Stand komplett neu (reine Referenzdaten ohne
Fremdschluessel-Abhaengigkeiten - kein Merge/Diff noetig).

Usage (aus backend/, mit aktiviertem venv):

    python scripts/import_postal_localities.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.postal_locality import PostalLocality  # noqa: E402

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "de_postal_codes.csv"


def load() -> int:
    with SessionLocal() as session:
        session.query(PostalLocality).delete()

        rows: list[PostalLocality] = []
        with CSV_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(
                    PostalLocality(
                        postal_code=row["postal_code"].strip(),
                        locality=row["locality"].strip(),
                        borough=row["borough"].strip() or None,
                        suburb=row["suburb"].strip() or None,
                    )
                )
        session.add_all(rows)
        session.commit()
        return len(rows)


def main() -> None:
    count = load()
    print(f"{count} PLZ<->Ort-Zeilen geladen aus {CSV_PATH}.")


if __name__ == "__main__":
    main()
