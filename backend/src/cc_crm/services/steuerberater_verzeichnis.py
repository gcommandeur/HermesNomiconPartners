"""Anbindung des amtlichen Steuerberaterverzeichnisses der
Bundessteuerberaterkammer (https://steuerberaterverzeichnis.berufs-org.de/,
oeffentlich zugaenglich nach § 86b StBerG, keine Anmeldung noetig).

Live am 2026-07-22 verifiziert:
- Suchformular POSTet application/x-www-form-urlencoded an "/?lang=de" mit den
  Feldern nachnameOrFirmenname / ortFilter / plzFilter (kein CSRF-Token).
- Eine Suche NUR mit PLZ oder Ort liefert alle dort bestellten Personen/
  Gesellschaften als server-gerenderte Karten zurueck (PLZ 70173: 160
  Treffer in einer Antwort, keine Pagination).
- Jede Karte: <a class="link-to-detail" href="details/<ID>/?lang=de"> mit
  <p class="beruf">Steuerberater(in)</p>, <p class="akademische-grade">,
  <p class="name">Vorname Nachname</p> und <p class="address-display">
  Kanzlei<br>Strasse<br>PLZ Ort</p>. Gesellschaften haben KEIN beruf-<p>
  (bzw. keines, das mit "Steuerberater"/"Steuerbevollmaechtigt" beginnt)
  und werden uebersprungen - Leads sind Personen.
- Zu breite Suche (z.B. Ort "Berlin") liefert keine Karten, sondern die
  Meldung "Zu viele moegliche Treffer" - wird als Fehler zurueckgemeldet
  statt still 0 Treffer zu liefern.

Bewusst regex-basiertes Parsing der festen, server-gerenderten Klassen statt
einer neuen HTML-Parser-Dependency - gleiche Stdlib-Philosophie wie
services/name_matching.py.
"""

from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass, field

import httpx

BASE_URL = "https://steuerberaterverzeichnis.berufs-org.de"
SEARCH_URL = f"{BASE_URL}/?lang=de"

# Hoeflicher, identifizierbarer User-Agent fuer die Behoerdenseite (kein
# Verstecken hinter einem Browser-UA).
USER_AGENT = "HermesCRM-Sourcing/1.0 (Commandeur Consulting; Recruiting-Research)"

REQUEST_TIMEOUT_SECONDS = 30.0

_CARD_RE = re.compile(
    r'<a class="link-to-detail" href="(?P<href>[^"]+)">(?P<body>.*?)</a>', re.DOTALL
)
_FIELD_RES = {
    "beruf": re.compile(r'<p class="beruf text-wrap">\s*(?P<value>.*?)\s*</p>', re.DOTALL),
    "grade": re.compile(
        r'<p class="akademische-grade text-wrap">\s*(?P<value>.*?)\s*</p>', re.DOTALL
    ),
    "name": re.compile(r'<p class="name text-wrap">\s*(?P<value>.*?)\s*</p>', re.DOTALL),
    "address": re.compile(
        r'<p class="address-display text-wrap">\s*(?P<value>.*?)\s*</p>', re.DOTALL
    ),
}
_TOO_MANY_RE = re.compile(r"Zu viele m..?gliche Treffer")
_BR_RE = re.compile(r"<br\s*/?>")
_PLZ_ORT_RE = re.compile(r"^(?P<plz>\d{5})\s+(?P<ort>.+)$")
# Namenspartikel, die zum Nachnamen gehoeren ("Anna von der Heide").
_SURNAME_PARTICLES = {"von", "van", "de", "der", "den", "zu", "zur", "ten", "ter", "da", "di"}


class TooManyResultsError(Exception):
    """Suche war zu breit - das Verzeichnis verweigert die Ergebnisliste."""


@dataclass
class DirectoryPerson:
    first_name: str
    last_name: str
    beruf: str
    akademische_grade: str | None
    employer: str | None
    street: str | None
    postal_code: str | None
    city: str | None
    detail_url: str
    address_lines: list[str] = field(default_factory=list)


def fetch_search_html(plz_or_ort: str) -> str:
    """Ein einzelner Such-Request (nur PLZ ODER Ort, je nach Eingabeformat).
    Aufrufer ist fuer Pausen zwischen mehreren Aufrufen verantwortlich
    (hoefliches Crawling, siehe SourcingService.run_steuerberater_search)."""
    value = plz_or_ort.strip()
    is_plz = value.isdigit()
    data = {
        "nachnameOrFirmenname": "",
        "ortFilter": "" if is_plz else value,
        "plzFilter": value if is_plz else "",
    }
    response = httpx.post(
        SEARCH_URL,
        data=data,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def parse_persons(html: str) -> list[DirectoryPerson]:
    """Alle Personen-Karten der Ergebnisseite (Gesellschaften werden
    uebersprungen). Wirft TooManyResultsError bei zu breiter Suche."""
    if _TOO_MANY_RE.search(html):
        raise TooManyResultsError(
            "Verzeichnis meldet 'Zu viele mögliche Treffer' - bitte engere PLZ/Ort angeben"
        )
    persons: list[DirectoryPerson] = []
    for card in _CARD_RE.finditer(html):
        body = card.group("body")
        fields = {
            key: _clean_text(match.group("value")) if (match := regex.search(body)) else ""
            for key, regex in _FIELD_RES.items()
        }
        beruf = fields["beruf"]
        # Nur natuerliche Personen: Berufsausuebungsgesellschaften haben kein
        # (Personen-)beruf-Feld und der "name" ist der Firmenname.
        if not beruf.startswith(("Steuerberater", "Steuerbevollmächtigt")):
            continue
        first_name, last_name = _split_person_name(fields["name"])
        if not first_name or not last_name:
            continue
        address_lines = _address_lines(body)
        employer, street, plz, ort = _split_address(address_lines)
        persons.append(
            DirectoryPerson(
                first_name=first_name,
                last_name=last_name,
                beruf=beruf,
                akademische_grade=fields["grade"] or None,
                employer=employer,
                street=street,
                postal_code=plz,
                city=ort,
                detail_url=f"{BASE_URL}/{card.group('href').lstrip('/')}",
                address_lines=address_lines,
            )
        )
    return persons


def _address_lines(card_body: str) -> list[str]:
    match = _FIELD_RES["address"].search(card_body)
    if match is None:
        return []
    raw = match.group("value")
    return [cleaned for line in _BR_RE.split(raw) if (cleaned := _clean_text(line))]


def _split_address(
    lines: list[str],
) -> tuple[str | None, str | None, str | None, str | None]:
    """Letzte Zeile ist "PLZ Ort", davor die Strasse, alles davor der
    Kanzlei-/Gesellschaftsname (kann mehrzeilig sein, z.B. "Baker Tilly" +
    "Steuerberatungsgesellschaft mbH & Co. KG")."""
    if not lines:
        return None, None, None, None
    plz = ort = None
    remaining = list(lines)
    if (match := _PLZ_ORT_RE.match(remaining[-1])) is not None:
        plz, ort = match.group("plz"), match.group("ort")
        remaining.pop()
    street = remaining.pop() if remaining else None
    employer = " ".join(remaining) if remaining else None
    return employer, street, plz, ort


def _split_person_name(full_name: str) -> tuple[str, str]:
    """ "Christoph Arnold" -> ("Christoph", "Arnold"); Namenspartikel bleiben
    beim Nachnamen ("Anna von der Heide" -> ("Anna", "von der Heide"))."""
    tokens = full_name.split()
    if len(tokens) < 2:
        return "", ""
    split_at = len(tokens) - 1
    while split_at > 1 and tokens[split_at - 1].lower() in _SURNAME_PARTICLES:
        split_at -= 1
    return " ".join(tokens[:split_at]), " ".join(tokens[split_at:])


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html_module.unescape(value)).strip()
