import hashlib
import math
import re
import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.enums import JobStatus
from cc_crm.models.job_mandate import JobMandate
from cc_crm.schemas.geo import GeoMappingResult

# Centroids for German cities used in seed data / typical client input. This is a
# static lookup, not a live geocoding call - no API key required. See
# docs/GEO_MAPPING.md for how to plug in a real geocoding provider later.
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


def candidate_coordinates(
    city: str | None, postal_code: str | None, seed: str
) -> tuple[float | None, float | None]:
    """Oeffentlicher Name fuer die frueher private _coordinates() - wird
    bereits ausserhalb dieses Moduls gebraucht (services/vacancy_matching.py
    fuer den Vakanz->Kandidaten-Umkreis-Filter, services/candidates.py fuer
    den Kandidaten-eigenen PLZ+Umkreis-Filter) und war davor nur per
    Unterstrich-Konvention-Bruch importiert. Gilt fuer Kandidat UND Kanzlei
    gleichermassen (city/postal_code/seed sind generisch), der Name betont
    hier den Hauptverwendungszweck."""
    base = CITY_COORDINATES.get((city or "").strip().lower())
    if base is None and postal_code:
        base = PLZ_ZONE_COORDINATES.get(postal_code[:1])
    if base is None:
        return None, None
    dx, dy = _jitter(seed)
    return round(base[0] + dx, 5), round(base[1] + dy, 5)


_DIGITS_RE = re.compile(r"\d+")


def resolve_place_query(query: str | None) -> tuple[float | None, float | None]:
    """Resolves a free-text place query (city name, postal code, or 'PLZ Ort')
    to approximate lat/lng, using the same static city/PLZ-zone lookup as
    candidate_coordinates() above. Used both by the /geo-mapping/geocode
    endpoint (Ort/PLZ-Eingabe als Umkreis-Zentrum, siehe geo-results-table.tsx)
    and by the Vakanz->Kandidaten-Matching (services/vacancy_matching.py), wo
    die Vakanz nur ein freies location-Textfeld statt getrennter city/
    postal_code-Spalten hat.

    Bewusst OHNE den _jitter()-Offset von candidate_coordinates(): der
    Jitter existiert nur, damit mehrere Kandidaten-/Kanzlei-Pins in derselben
    Stadt auf der Karte nicht exakt uebereinander liegen - fuer ein Umkreis-
    Zentrum wuerde er die Suche unnoetig (und nicht nachvollziehbar) vom
    echten Stadt-Mittelpunkt wegverschieben.
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return None, None
    digits = "".join(_DIGITS_RE.findall(cleaned))
    postal_code = digits if len(digits) >= 5 else None
    city_part = _DIGITS_RE.sub(" ", cleaned).strip(" ,-")
    base = CITY_COORDINATES.get(city_part.lower())
    if base is None and postal_code:
        base = PLZ_ZONE_COORDINATES.get(postal_code[:1])
    if base is None:
        return None, None
    return round(base[0], 5), round(base[1], 5)


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
    """Aggregates Kandidaten/Kanzleien for the Geo Mapping list, map and filters."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def results(self) -> list[GeoMappingResult]:
        items: list[GeoMappingResult] = []
        candidates = self.session.scalars(select(Candidate)).all()
        for candidate in candidates:
            location = (
                ", ".join(part for part in [candidate.postal_code, candidate.city] if part)
                or "Ort unbekannt"
            )
            tags = [tag for tag in [candidate.qualification, candidate.job_title] if tag]
            lat, lng = candidate_coordinates(
                candidate.city, candidate.postal_code, str(candidate.id)
            )
            items.append(
                GeoMappingResult(
                    id=str(candidate.id),
                    kind="candidate",
                    name=f"{candidate.first_name} {candidate.last_name}",
                    location=location,
                    postal_code=candidate.postal_code,
                    latitude=lat,
                    longitude=lng,
                    status=candidate.status.value,
                    tags=tags,
                    mailing_ready=candidate.status.value not in {"blocked", "archived"},
                    email=candidate.email,
                    role=candidate.job_title,
                    qualification=candidate.qualification,
                    salary_expectation=candidate.salary_expectation,
                    notice_period=candidate.notice_period,
                    available_from=candidate.available_from,
                    remote_preference=candidate.remote_teilzeit_wuensche,
                )
            )

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
            lat, lng = candidate_coordinates(client.city, client.postal_code, str(client.id))
            items.append(
                GeoMappingResult(
                    id=str(client.id),
                    kind="client",
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
