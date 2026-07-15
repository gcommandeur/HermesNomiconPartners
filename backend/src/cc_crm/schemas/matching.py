import uuid

from pydantic import BaseModel, Field

from cc_crm.models.enums import SubmissionStatus
from cc_crm.schemas.client_company import ClientCompanyRead


class ClientMatchRead(BaseModel):
    client: ClientCompanyRead
    score: int
    reasons: list[str]
    already_submitted: bool


class BulkSubmitRequest(BaseModel):
    client_company_ids: list[uuid.UUID] = Field(min_length=1)
    target_status: SubmissionStatus = SubmissionStatus.CV_OUT
    owner: str | None = None


class BulkSubmitResultItem(BaseModel):
    client_company_id: uuid.UUID
    outcome: str
    submission_id: uuid.UUID | None = None
    reason: str | None = None


class BulkSubmitResponse(BaseModel):
    results: list[BulkSubmitResultItem]
    created_count: int
    skipped_count: int
