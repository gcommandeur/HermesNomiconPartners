"""Anbindung des oeffentlichen WPK-Berufsregisters (Wirtschaftsprueferkammer,
https://www.wpk.de/berufsregister/ - jedermann zugaenglich, keine Anmeldung).

Live am 2026-07-23 verifiziert:
- Die Register-Suche ist eine kleine SPA; die eigentliche Suche laeuft als
  POST auf /berufsregister/backend/search (Formularfelder registernummer/
  name/vorname/ort/plz/country/type, urlencoded wird akzeptiert).
- WICHTIG: type="1" ("alle" Gruppen) muss gesetzt sein - mit leerem type
  antwortet das Backend mit einer leeren Liste.
- Eine Suche NUR mit PLZ oder Ort funktioniert (Listen-/Gebietssuche) und
  liefert strukturiertes JSON zurueck: istPerson, name (Nachname, ggf. mit
  "Dr."-Titel), vorname, strasse, plz, ort, klassifizierungBRO (WP/vBP/WPG/
  ...), registernummer, statusTxt ("aktiv"). PLZ 70173: 57 Eintraege.
- Gesellschaften (istPerson=false) werden uebersprungen - Leads sind
  Personen. Es gibt keine Detail-URL pro Person, nur die Registernummer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

REGISTER_URL = "https://www.wpk.de/berufsregister/"
SEARCH_URL = "https://www.wpk.de/berufsregister/backend/search"

USER_AGENT = "HermesCRM-Sourcing/1.0 (Commandeur Consulting; Recruiting-Research)"
REQUEST_TIMEOUT_SECONDS = 30.0

# Berufsbezeichnung je Register-Klassifizierung natuerlicher Personen.
_PERSON_KLASSIFIZIERUNGEN = {
    "WP": "Wirtschaftsprüfer/in",
    "vBP": "vereidigte/r Buchprüfer/in",
}

# Akademische Titel, die das Register in das Nachnamensfeld mischt
# ("Dr. Hacker", "Prof. Dr. Muster").
_TITLE_PREFIX_RE = re.compile(r"^((?:prof\.?|dr\.?|dipl\.[-\w.]*|h\.c\.)\s+)+", re.IGNORECASE)


@dataclass
class WpkPerson:
    first_name: str
    last_name: str
    beruf: str
    akademische_grade: str | None
    street: str | None
    postal_code: str | None
    city: str | None
    registernummer: int | None
    status: str | None


def fetch_search_results(plz_or_ort: str) -> list[dict[str, Any]]:
    """Ein einzelner Such-Request (nur PLZ ODER Ort). Aufrufer pausiert
    zwischen mehreren Aufrufen (hoefliches Crawling)."""
    value = plz_or_ort.strip()
    is_plz = value.isdigit()
    response = httpx.post(
        SEARCH_URL,
        data={
            "registernummer": "",
            "name": "",
            "vorname": "",
            "ort": "" if is_plz else value,
            "plz": value if is_plz else "",
            "country": "",
            # "1" == Gruppe "alle" - Pflichtfeld, sonst leere Antwort (s.o.).
            "type": "1",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    response.raise_for_status()
    rows: list[dict[str, Any]] = response.json()
    return rows


def parse_persons(rows: list[dict[str, Any]]) -> list[WpkPerson]:
    """Nur aktive natuerliche Personen (WP/vBP) - Gesellschaften und
    erloschene Eintraege werden uebersprungen."""
    persons: list[WpkPerson] = []
    for row in rows:
        if not row.get("istPerson"):
            continue
        klassifizierung = str(row.get("klassifizierungBRO") or "")
        beruf = _PERSON_KLASSIFIZIERUNGEN.get(klassifizierung)
        if beruf is None:
            continue
        status = str(row.get("statusTxt") or "")
        if status and status != "aktiv":
            continue
        grade, last_name = _split_title(str(row.get("name") or ""))
        first_name = str(row.get("vorname") or "").strip()
        if not first_name or not last_name:
            continue
        persons.append(
            WpkPerson(
                first_name=first_name,
                last_name=last_name,
                beruf=beruf,
                akademische_grade=grade,
                street=str(row.get("strasse") or "") or None,
                postal_code=str(row.get("plz") or "") or None,
                city=str(row.get("ort") or "") or None,
                registernummer=row.get("registernummer"),
                status=status or None,
            )
        )
    return persons


def _split_title(name: str) -> tuple[str | None, str]:
    """ "Dr. Hacker" -> ("Dr.", "Hacker"); "Berninger" -> (None, "Berninger")."""
    value = name.strip()
    match = _TITLE_PREFIX_RE.match(value)
    if match is None:
        return None, value
    return match.group(0).strip(), value[match.end() :].strip()
