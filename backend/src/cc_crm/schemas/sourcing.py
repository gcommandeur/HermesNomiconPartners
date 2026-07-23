import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from cc_crm.models.enums import SourcingLeadStatus, SourcingSourceType
from cc_crm.schemas.base import EntityRead


class SourcingLeadCreate(BaseModel):
    source_type: SourcingSourceType
    source_url: str | None = None
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    current_employer: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, max_length=160)
    postal_code: str | None = Field(default=None, max_length=20)
    raw_data: dict[str, Any] | None = None
    matched_client_company_id: uuid.UUID | None = None


class SourcingRunRequest(BaseModel):
    # Phase 2: nur das Steuerberaterverzeichnis; weitere Quellen (Team-Seiten,
    # WPK/BRAK) folgen in Phase 3 mit eigenen Parametern.
    source_type: Literal[SourcingSourceType.STEUERBERATERVERZEICHNIS]
    # Max. 20 Gebiete pro Lauf: der Lauf ist synchron (Ergebnis-Zahlen direkt
    # in der Antwort) und pausiert zwischen Requests - mehr Gebiete wuerden
    # den Request zu lange offen halten.
    plz_or_ort: list[str] = Field(min_length=1, max_length=20)


class SourcingRunResult(BaseModel):
    found: int = 0
    created: int = 0
    skipped_existing: int = 0
    possible_duplicates: int = 0
    errors: list[str] = Field(default_factory=list)


class SourcingLeadRead(EntityRead):
    source_type: SourcingSourceType
    source_url: str | None
    first_name: str
    last_name: str
    current_employer: str | None
    city: str | None
    postal_code: str | None
    raw_data: dict[str, Any] | None
    matched_client_company_id: uuid.UUID | None
    status: SourcingLeadStatus
    duplicate_of_candidate_id: uuid.UUID | None
    created_candidate_id: uuid.UUID | None
    found_at: datetime
    reviewed_at: datetime | None
    reviewed_by_user_id: uuid.UUID | None
