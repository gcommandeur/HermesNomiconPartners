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
