from pydantic import BaseModel


class GeocodeResult(BaseModel):
    """Ergebnis der Ort/PLZ-Aufloesung (services/geo.py::resolve_place_query)
    fuer die freie Umkreis-Suche - beide Felder None, wenn der Query-String
    weder als bekannte Stadt noch als PLZ-Zone aufloesbar war."""

    latitude: float | None
    longitude: float | None


class GeoMappingResult(BaseModel):
    """Geo Mapping ist seit der Vereinfachung eine reine Kanzleien-
    Umkreissuche (die kandidatenzentrierte Umkreissuche uebernimmt die neue
    "CV Out"-Kampagne direkt am Kandidaten) - kein `kind`-Feld mehr noetig,
    jedes Ergebnis ist implizit eine Kanzlei."""

    id: str
    name: str
    location: str
    postal_code: str | None
    latitude: float | None = None
    longitude: float | None = None
    status: str
    tags: list[str]
    mailing_ready: bool
    email: str | None = None

    # Echte Modellfelder aus models/client_company.py bzw. abgeleitet aus
    # contact_persons/job_mandates.
    terms_status: str | None = None
    fee_tier: str | None = None
    primary_contact_name: str | None = None
    active_vacancy_count: int | None = None
