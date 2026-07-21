from datetime import date
from typing import Literal

from pydantic import BaseModel


class GeoMappingResult(BaseModel):
    id: str
    kind: Literal["candidate", "client"]
    name: str
    location: str
    postal_code: str | None
    latitude: float | None = None
    longitude: float | None = None
    status: str
    tags: list[str]
    mailing_ready: bool
    email: str | None = None

    # Kandidaten-spezifische Filterfelder (bei kind="client" immer None) -
    # echte Modellfelder aus models/candidate.py, keine erfundenen Werte.
    role: str | None = None
    qualification: str | None = None
    salary_expectation: str | None = None
    notice_period: str | None = None
    available_from: date | None = None
    remote_preference: str | None = None

    # Kanzlei-spezifische Filterfelder (bei kind="candidate" immer None) -
    # echte Modellfelder aus models/client_company.py bzw. abgeleitet aus
    # contact_persons/job_mandates.
    terms_status: str | None = None
    fee_tier: str | None = None
    primary_contact_name: str | None = None
    active_vacancy_count: int | None = None
