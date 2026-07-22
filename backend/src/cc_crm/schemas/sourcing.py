import uuid
from datetime import datetime
from typing import Any

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
