import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
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


def _coordinates(
    city: str | None, postal_code: str | None, seed: str
) -> tuple[float | None, float | None]:
    base = CITY_COORDINATES.get((city or "").strip().lower())
    if base is None and postal_code:
        base = PLZ_ZONE_COORDINATES.get(postal_code[:1])
    if base is None:
        return None, None
    dx, dy = _jitter(seed)
    return round(base[0] + dx, 5), round(base[1] + dy, 5)


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
            lat, lng = _coordinates(candidate.city, candidate.postal_code, str(candidate.id))
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
                )
            )

        clients = self.session.scalars(select(ClientCompany)).all()
        for client in clients:
            location = ", ".join(part for part in [client.postal_code, client.city] if part) or (
                "Ort unbekannt"
            )
            tags = [tag for tag in [client.focus, client.region] if tag]
            lat, lng = _coordinates(client.city, client.postal_code, str(client.id))
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
                )
            )
        return items
