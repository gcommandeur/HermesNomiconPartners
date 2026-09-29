import hashlib
import math
import re
import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.enums import JobStatus
from cc_crm.models.job_mandate import JobMandate
from cc_crm.models.postal_locality import PostalLocality
from cc_crm.schemas.geo import GeoMappingResult

# Centroids for German cities used in seed data / typical client input, AND
# als letzter Fallback, falls eine PLZ in postal_localities keine Koordinaten
# hat (siehe _postal_locality_coordinates() unten - die eigentliche, PLZ-
# genaue Quelle seit der PLZ-Koordinaten-Erweiterung). Kein API-Key noetig.
CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "muenchen": (48.1372, 11.5755),
    "münchen": (48.1372, 11.5755),
    "frankfurt am main": (50.1109, 8.6821),
    "frankfurt": (50.1109, 8.6821),
    "duesseldorf": (51.2277, 6.7735),
    "düsseldorf": (51.2277, 6.7735),
    "hamburg": (53.5511, 9.9937),
    "koeln": (50.9375, 6.9603),
    "köln": (50.9375, 6.9603),
    "stuttgart": (48.7758, 9.1829),
    "berlin": (52.5200, 13.4050),
    "mannheim": (49.4875, 8.4660),
    "nuernberg": (49.4521, 11.0767),
    "nürnberg": (49.4521, 11.0767),
    "essen": (51.4556, 7.0116),
    "leipzig": (51.3397, 12.3731),
    "hannover": (52.3759, 9.7320),
    "bremen": (53.0793, 8.8017),
    "dortmund": (51.5136, 7.4653),
    "dresden": (51.0504, 13.7373),
    # Ergaenzt nach der Wiesbaden-Regression (200km-Umkreissuche lieferte 0
    # Treffer, weil diese Mittelstaedte weder hier noch - bei fehlender
    # postal_localities-Koordinate fuer die konkret eingegebene PLZ - ueber
    # den neuen Ortsnamen-Fallback aufloesbar waren) - reines Sicherheitsnetz
    # fuer den Fall, dass eine Stadt auch in postal_localities gar nicht
    # vorkommt, dieselbe grobe Praezision wie die urspruengliche Liste oben.
    "wiesbaden": (50.0782, 8.2398),
    "mainz": (49.9929, 8.2473),
    "bonn": (50.7374, 7.0982),
    "augsburg": (48.3705, 10.8978),
    "bielefeld": (52.0302, 8.5325),
    "karlsruhe": (49.0069, 8.4037),
    "freiburg": (47.9990, 7.8421),
    "muenster": (51.9607, 7.6261),
    "münster": (51.9607, 7.6261),
    "wuerzburg": (49.7913, 9.9534),
    "würzburg": (49.7913, 9.9534),
    "regensburg": (49.0134, 12.1016),
    "heidelberg": (49.3988, 8.6724),
    "darmstadt": (49.8728, 8.6512),
    "kassel": (51.3127, 9.4797),
    "trier": (49.7596, 6.6441),
    "koblenz": (50.3569, 7.5890),
    "saarbruecken": (49.2401, 6.9969),
    "saarbrücken": (49.2401, 6.9969),
    "potsdam": (52.3906, 13.0645),
    "erfurt": (50.9848, 11.0299),
    "rostock": (54.0887, 12.1400),
    "kiel": (54.3233, 10.1228),
    "luebeck": (53.8655, 10.6866),
    "lübeck": (53.8655, 10.6866),
    "braunschweig": (52.2689, 10.5268),
    "chemnitz": (50.8278, 12.9214),
    "halle": (51.4825, 11.9691),
    "magdeburg": (52.1205, 11.6276),
    "ulm": (48.3984, 9.9916),
    "reutlingen": (48.4914, 9.2043),
    "goettingen": (51.5413, 9.9158),
    "göttingen": (51.5413, 9.9158),
    "paderborn": (51.7189, 8.7575),
    "ingolstadt": (48.7665, 11.4258),
    "wolfsburg": (52.4227, 10.7865),
    "fuerth": (49.4769, 10.9887),
    "fürth": (49.4769, 10.9887),
    "erlangen": (49.5897, 11.0119),
    "siegen": (50.8748, 8.0243),
    "jena": (50.9271, 11.5892),
    "hildesheim": (52.1508, 9.9511),
}

# Fallback centroid per first PLZ digit (Germany's postal code zones), used
# when the city name isn't in CITY_COORDINATES but a postal code is known.
PLZ_ZONE_COORDINATES: dict[str, tuple[float, float]] = {
    "0": (51.05, 13.74),  # Dresden/Leipzig area
    "1": (52.52, 13.40),  # Berlin area
    "2": (53.55, 10.00),  # Hamburg area
    "3": (52.38, 9.73),  # Hannover area
    "4": (51.46, 7.01),  # Ruhrgebiet
    "5": (50.94, 6.96),  # Koeln/Bonn area
    "6": (50.11, 8.68),  # Frankfurt area
    "7": (48.78, 9.18),  # Stuttgart area
    "8": (48.14, 11.58),  # Muenchen area
    "9": (49.45, 11.08),  # Nuernberg area
}


def _jitter(seed: str, spread: float = 0.06) -> tuple[float, float]:
    """Small deterministic offset so multiple pins in the same city don't overlap."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    dx = (int(digest[:8], 16) / 0xFFFFFFFF - 0.5) * spread
    dy = (int(digest[8:16], 16) / 0xFFFFFFFF - 0.5) * spread
    return dx, dy


def _locality_coordinates_by_name(
    session: Session, city_normalized: str
) -> tuple[float, float] | None:
    """Ortsnamen-Fallback ueber den `locality`-Index (siehe models/
    postal_locality.py) - case-insensitive exakter Namensvergleich (kein
    LIKE/Teilstring, um z.B. 'Wiesbaden' nicht faelschlich mit 'Wiesbaden-
    Biebrich' zu verwechseln). Deckt zwei Faelle ab, die die reine PLZ-
    Abfrage in _postal_locality_coordinates() strukturell nicht abdecken
    kann (Regression nach dem Praezisions-Fix, siehe dessen Docstring):
    (a) eine reine Ortsnamen-Suche ohne PLZ-Ziffern, (b) eine PLZ, deren
    eigene Zeile keine Koordinate hat, aber eine ANDERE Zeile mit demselben
    Ortsnamen (typischerweise eine Nachbar-PLZ derselben Stadt) schon -
    fuer eine ohnehin nicht strassengenaue Umkreissuche eine voellig
    ausreichende Ersatzkoordinate (ueblicherweise <5km Unterschied), klar
    praeziser als der PLZ_ZONE_COORDINATES-Fallback (100+ km moeglich)."""
    statement = select(PostalLocality).where(
        func.lower(PostalLocality.locality) == city_normalized,
        PostalLocality.latitude.is_not(None),
        PostalLocality.longitude.is_not(None),
    )
    row = session.scalars(statement).first()
    if row is None:
        return None
    return row.latitude, row.longitude  # type: ignore[return-value]


def _postal_locality_coordinates(
    session: Session, postal_code: str | None, city: str | None = None
) -> tuple[float, float] | None:
    """Echte, PLZ-genaue Koordinaten aus postal_localities (siehe PLZ-
    Koordinaten-Erweiterung) - deutlich praeziser als die vorherige Stadt-/
    PLZ-Zonen-Naeherung (CITY_COORDINATES/PLZ_ZONE_COORDINATES bleiben nur
    als Fallback fuer PLZ ohne Koordinaten-Treffer, siehe candidate_
    coordinates()/resolve_place_query() unten).

    Mehrere Zeilen fuer dieselbe PLZ sind moeglich (Stadtbezirke/Ortsteile) -
    bei bekanntem Ortsnamen wird zuerst eine Zeile mit uebereinstimmendem
    locality gesucht, sonst die erste Zeile mit gesetzten Koordinaten fuer
    diese PLZ genommen.

    Regressions-Fix (nach dem Praezisions-Fix in 3acc0cb fiel z.B. Wiesbaden
    komplett auf 0 Treffer statt auf den Zonen-Fallback zurueckzufallen -
    NICHT weil precise=False jetzt zu streng waere, sondern weil diese
    Funktion selbst zu eng abgefragt hat, siehe drei Luecken unten):
    - Hat die exakte PLZ KEINE eigene Koordinatenzeile, aber die Tabelle
      kennt trotzdem einen Ortsnamen dafuer (Zeile ohne Koordinate, z.B. aus
      der OSM-Quelle), wird ueber diesen Namen per _locality_coordinates_
      by_name() nach einer Nachbar-PLZ mit Koordinate gesucht.
    - Ist gar keine (gueltige) PLZ gegeben, aber ein Ortsname (reine
      Namenssuche, z.B. "Wiesbaden" ohne Ziffern), wird direkt per Namen
      gesucht statt die Tabelle komplett zu umgehen und sofort auf
      CITY_COORDINATES/Zone zu springen."""
    valid_postal_code = bool(postal_code and len(postal_code) == 5 and postal_code.isdigit())
    city_normalized = city.strip().lower() if city else None

    if valid_postal_code:
        statement = select(PostalLocality).where(
            PostalLocality.postal_code == postal_code,
            PostalLocality.latitude.is_not(None),
            PostalLocality.longitude.is_not(None),
        )
        rows = session.scalars(statement).all()
        if rows:
            if city_normalized:
                for row in rows:
                    if row.locality.strip().lower() == city_normalized:
                        return row.latitude, row.longitude  # type: ignore[return-value]
            first = rows[0]
            return first.latitude, first.longitude  # type: ignore[return-value]

        # Exakte PLZ hat keine eigene Koordinate - falls kein Ortsname
        # mitgegeben wurde, ueber eine beliebige (auch koordinatenlose)
        # Zeile fuer diese PLZ herausfinden, wie der Ort heisst.
        if not city_normalized:
            name_row = session.scalars(
                select(PostalLocality).where(PostalLocality.postal_code == postal_code)
            ).first()
            if name_row is not None:
                city_normalized = name_row.locality.strip().lower()

    if city_normalized:
        return _locality_coordinates_by_name(session, city_normalized)

    return None


def candidate_coordinates(
    session: Session,
    city: str | None,
    postal_code: str | None,
    seed: str,
    *,
    apply_jitter: bool = True,
) -> tuple[float | None, float | None, bool]:
    """Oeffentlicher Name fuer die frueher private _coordinates() - wird
    bereits ausserhalb dieses Moduls gebraucht (services/vacancy_matching.py
    fuer den Vakanz->Kandidaten-Umkreis-Filter, services/candidates.py fuer
    den Kandidaten-eigenen PLZ+Umkreis-Filter) und war davor nur per
    Unterstrich-Konvention-Bruch importiert. Gilt fuer Kandidat UND Kanzlei
    gleichermassen (city/postal_code/seed sind generisch), der Name betont
    hier den Hauptverwendungszweck.

    Reihenfolge seit der PLZ-Koordinaten-Erweiterung: zuerst exakte PLZ aus
    postal_localities, erst wenn das nichts liefert Fallback auf CITY_
    COORDINATES, erst wenn auch das nichts liefert Fallback auf die grobe
    PLZ_ZONE_COORDINATES-Naeherung (ein einziger Punkt pro erster PLZ-Ziffer
    fuer ganz Deutschland - kann 100+ km danebenliegen, siehe Vorfall
    "Illingen/Saar (PLZ 66557, Zone '6') faelschlich im 25km-Radius um
    Wiesbaden").

    Gibt zusaetzlich `precise` zurueck: True nur fuer die ersten beiden,
    PLZ-/Stadt-genauen Quellen, False fuer den Zonen-Fallback (und wenn gar
    keine Koordinate aufloesbar war, zusammen mit lat=lng=None). Ein harter
    Umkreis-Filter (candidates.py::_list_filtered_by_radius, vacancy_
    matching.py, clients.py::list_near_candidate) MUSS `precise=False`
    genauso wie `None` behandeln (raus aus den Ergebnissen) - alles andere
    wuerde Kandidaten anhand einer strukturell zu groben Naeherung ein-/
    ausschliessen, kein Rundungsfehler.

    `apply_jitter` steuert den deterministischen Kartenversatz (_jitter,
    bis zu ~0.06 Grad ≈ 5-7km): nur fuer die Kartendarstellung sinnvoll
    (GeoMappingService.results(), verhindert exakt uebereinanderliegende
    Pins), in JEDER Distanzberechnung fuer einen harten Radius-Filter muss
    er False sein - sonst kann derselbe Kandidat je nach Seed um bis zu 5-7km
    verschoben werden und bei einem knappen Radius inkonsistent rein-/
    rausfallen."""
    base = _postal_locality_coordinates(session, postal_code, city)
    precise = base is not None
    if base is None:
        base = CITY_COORDINATES.get((city or "").strip().lower())
        precise = base is not None
    if base is None and postal_code:
        base = PLZ_ZONE_COORDINATES.get(postal_code[:1])
        precise = False
    if base is None:
        return None, None, False
    if not apply_jitter:
        return round(base[0], 5), round(base[1], 5), precise
    dx, dy = _jitter(seed)
    return round(base[0] + dx, 5), round(base[1] + dy, 5), precise


_DIGITS_RE = re.compile(r"\d+")


def resolve_place_query(
    session: Session, query: str | None
) -> tuple[float | None, float | None, bool]:
    """Resolves a free-text place query (city name, postal code, or 'PLZ Ort')
    to precise lat/lng, using postal_localities first and falling back to the
    same static city/PLZ-zone lookup as candidate_coordinates() above. Used
    both by the /geo-mapping/geocode endpoint (Ort/PLZ-Eingabe als Umkreis-
    Zentrum, siehe geo-results-table.tsx) and by der Vakanz->Kandidaten-
    Matching (services/vacancy_matching.py), wo die Vakanz nur ein freies
    location-Textfeld statt getrennter city/postal_code-Spalten hat.

    Bewusst OHNE den _jitter()-Offset von candidate_coordinates(): der
    Jitter existiert nur, damit mehrere Kandidaten-/Kanzlei-Pins in derselben
    Stadt auf der Karte nicht exakt uebereinander liegen - fuer ein Umkreis-
    Zentrum wuerde er die Suche unnoetig (und nicht nachvollziehbar) vom
    echten Stadt-Mittelpunkt wegverschieben.

    Gibt zusaetzlich `precise` zurueck (siehe candidate_coordinates()
    Docstring) - ein SUCHZENTRUM aus dem groben Zonen-Fallback ist fuer einen
    harten Umkreis-Filter genauso ungeeignet wie eine unpraezise Kandidaten-/
    Kanzlei-Koordinate: die Aufrufer in candidates.py/clients.py behandeln
    `precise=False` daher wie "kein Zentrum aufloesbar" (0 Treffer statt
    eines irrefuehrenden groben Zentrums).
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return None, None, False
    digits = "".join(_DIGITS_RE.findall(cleaned))
    postal_code = digits if len(digits) >= 5 else None
    city_part = _DIGITS_RE.sub(" ", cleaned).strip(" ,-")
    base = _postal_locality_coordinates(session, postal_code, city_part or None)
    precise = base is not None
    if base is None:
        base = CITY_COORDINATES.get(city_part.lower())
        precise = base is not None
    if base is None and postal_code:
        base = PLZ_ZONE_COORDINATES.get(postal_code[:1])
        precise = False
    if base is None:
        return None, None, False
    return round(base[0], 5), round(base[1], 5), precise


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Grosskreis-Distanz in km zwischen zwei Koordinaten - gleiche Formel wie
    haversineKm() in frontend/geo-results-table.tsx, hier serverseitig fuer
    das Vakanz->Kandidaten-Umkreis-Matching (services/vacancy_matching.py)."""
    earth_radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )
    return earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class GeoMappingService:
    """Aggregates Kanzleien for die Geo-Mapping-Liste, Karte und Filter -
    reine Kanzleien-Umkreissuche (die kandidatenzentrierte Umkreissuche
    uebernimmt die "CV Out"-Kampagne direkt am Kandidaten)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def results(self) -> list[GeoMappingResult]:
        items: list[GeoMappingResult] = []

        # Primaerer Ansprechpartner je Kanzlei (is_primary, sonst der erste
        # gefundene) und Anzahl offener Vakanzen (JobStatus.OPEN) - einmalig
        # ueber alle Kanzleien gebuendelt statt einer Einzel-Query pro Zeile.
        primary_contact_by_client: dict[uuid.UUID, str] = {}
        fallback_contact_by_client: dict[uuid.UUID, str] = {}
        for contact in self.session.scalars(select(ContactPerson)).all():
            name = f"{contact.first_name} {contact.last_name}"
            if contact.is_primary:
                primary_contact_by_client.setdefault(contact.client_company_id, name)
            else:
                fallback_contact_by_client.setdefault(contact.client_company_id, name)

        open_vacancy_counts = Counter(
            mandate.client_company_id
            for mandate in self.session.scalars(select(JobMandate)).all()
            if mandate.status == JobStatus.OPEN and mandate.client_company_id is not None
        )

        clients = self.session.scalars(select(ClientCompany)).all()
        for client in clients:
            location = ", ".join(part for part in [client.postal_code, client.city] if part) or (
                "Ort unbekannt"
            )
            tags = [tag for tag in [client.focus, client.region] if tag]
            # Kartendarstellung, kein Umkreis-Filter - Jitter bleibt hier
            # bewusst aktiv (verhindert uebereinanderliegende Pins), die
            # Praezision der Koordinatenquelle spielt fuer eine reine Anzeige
            # keine Rolle.
            lat, lng, _precise = candidate_coordinates(
                self.session, client.city, client.postal_code, str(client.id)
            )
            items.append(
                GeoMappingResult(
                    id=str(client.id),
                    name=client.name,
                    location=location,
                    postal_code=client.postal_code,
                    latitude=lat,
                    longitude=lng,
                    status=client.status.value,
                    tags=tags,
                    mailing_ready=client.status.value != "blocked",
                    email=client.email,
                    terms_status=client.terms_status,
                    fee_tier=client.honorar_stufe.value,
                    primary_contact_name=(
                        primary_contact_by_client.get(client.id)
                        or fallback_contact_by_client.get(client.id)
                    ),
                    active_vacancy_count=open_vacancy_counts.get(client.id, 0),
                )
            )
        return items
