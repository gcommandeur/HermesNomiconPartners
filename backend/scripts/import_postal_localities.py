"""Laedt den statischen PLZ<->Ort-Referenzdatensatz fuer Deutschland
(Phase 4b, bidirektionales Ort/PLZ-Matching bei der Kanzleien-Suche) UND
(seit der PLZ-Koordinaten-Erweiterung) die zugehoerigen PLZ-genauen
Koordinaten fuer die Umkreissuche.

Quelle 1 (postal_code/locality/borough/suburb):
backend/data/reference/de_postal_codes.csv - eine auf eindeutige (PLZ, Ort,
Stadtbezirk, Ortsteil)-Kombinationen verdichtete Teilmenge von
`src/de/osm/streets.updated.csv` aus dem Repository
https://github.com/openpotato/openplzapi.data (Auswertung von OpenStreetMap-
Daten fuer Deutschland, Stand des Downloads: 2026-07-23).
Lizenz: ODbL-1.0 (Open Database License) - (c) OpenStreetMap-Mitwirkende.

Quelle 2 (latitude/longitude):
backend/data/reference/de_postal_coordinates.csv - Geonames-Daten aus
https://github.com/zauberware/postal-codes-json-xml-csv (DE-Datensatz,
23.297 Eintraege, Stand des Downloads: 2026-09-27), Spalten
postal_code/place/latitude/longitude (aus der Original-Spaltenmenge
country_code/zipcode/place/state/state_code/province/province_code/
community/community_code/latitude/longitude auf die vier benoetigten
reduziert). Lizenz: CC-BY-4.0 - Namensnennung "zauberware" bzw. GeoNames
(https://www.geonames.org/), hier sowie im Docstring von
models/postal_locality.py erfuellt.

Beide Quellen landen in DERSELBEN Tabelle (siehe models/postal_locality.py) -
Zuordnung ueber die PLZ: hat eine PLZ in Quelle 2 mehrere Zeilen (mehrere
Orte/Firmensitze unter derselben PLZ - kommt bei sogenannten
Grosskunden-PLZ haeufig vor), wird nach Moeglichkeit die Zeile mit
uebereinstimmendem Ortsnamen (locality aus Quelle 1) gewaehlt, sonst die
ERSTE Zeile dieser PLZ aus Quelle 2 genommen. Eine PLZ ohne jeden Treffer in
Quelle 2 bleibt bei latitude/longitude = None (Fallback auf die groebere
Stadt-/PLZ-Zonen-Naeherung bleibt in services/geo.py bestehen).

Idempotent: loescht bei jedem Lauf zunaechst alle vorhandenen Zeilen und
laedt den aktuellen CSV-Stand komplett neu (reine Referenzdaten ohne
Fremdschluessel-Abhaengigkeiten - kein Merge/Diff noetig).

Usage (aus backend/, mit aktiviertem venv):

    python scripts/import_postal_localities.py
"""

from __future__ import annotations

import csv
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.postal_locality import PostalLocality  # noqa: E402

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "reference" / "de_postal_codes.csv"
COORDINATES_CSV_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "reference" / "de_postal_coordinates.csv"
)


def _normalize_name(value: str) -> str:
    """Vereinfachter Vergleichs-Schluessel fuer Ortsnamen - entfernt Umlaute/
    Akzente und Gross-/Kleinschreibung, damit z.B. "München" (Quelle 1) und
    "Muenchen"/"MÜNCHEN" (Quelle 2) trotzdem als Treffer erkannt werden."""
    decomposed = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _load_coordinates_by_plz() -> dict[str, list[tuple[str, float, float]]]:
    """Gruppiert Quelle 2 nach PLZ - eine PLZ kann mehrere (Ort, lat, lng)-
    Eintraege haben (siehe Modul-Docstring)."""
    by_plz: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    with COORDINATES_CSV_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            plz = row["postal_code"].strip()
            try:
                lat = float(row["latitude"])
                lng = float(row["longitude"])
            except (TypeError, ValueError):
                continue
            by_plz[plz].append((row["place"].strip(), lat, lng))
    return by_plz


def _match_coordinates(
    candidates: list[tuple[str, float, float]], locality: str
) -> tuple[float, float, bool] | None:
    """Bevorzugt eine Zeile mit uebereinstimmendem Ortsnamen, sonst die
    erste Zeile dieser PLZ (siehe Modul-Docstring). Drittes Tupelelement
    zeigt an, ob es ein Namenstreffer war (fuer die Lauf-Statistik)."""
    if not candidates:
        return None
    normalized_locality = _normalize_name(locality)
    for place, lat, lng in candidates:
        if _normalize_name(place) == normalized_locality:
            return lat, lng, True
    _, first_lat, first_lng = candidates[0]
    return first_lat, first_lng, False


def load() -> tuple[int, int]:
    coordinates_by_plz = _load_coordinates_by_plz()
    matched_by_name = 0
    matched_by_fallback = 0

    with SessionLocal() as session:
        session.query(PostalLocality).delete()

        rows: list[PostalLocality] = []
        with CSV_PATH.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                postal_code = row["postal_code"].strip()
                locality = row["locality"].strip()
                candidates = coordinates_by_plz.get(postal_code, [])
                match = _match_coordinates(candidates, locality)
                if match is not None:
                    if match[2]:
                        matched_by_name += 1
                    else:
                        matched_by_fallback += 1
                rows.append(
                    PostalLocality(
                        postal_code=postal_code,
                        locality=locality,
                        borough=row["borough"].strip() or None,
                        suburb=row["suburb"].strip() or None,
                        latitude=match[0] if match else None,
                        longitude=match[1] if match else None,
                    )
                )
        session.add_all(rows)
        session.commit()
        return len(rows), matched_by_name + matched_by_fallback


def main() -> None:
    total, with_coordinates = load()
    without_coordinates = total - with_coordinates
    print(f"{total} PLZ<->Ort-Zeilen geladen aus {CSV_PATH}.")
    print(
        f"{with_coordinates} davon mit Koordinaten aus {COORDINATES_CSV_PATH} "
        f"({without_coordinates} ohne Treffer - Fallback auf Stadt-/PLZ-Zonen-Naeherung)."
    )


if __name__ == "__main__":
    main()
