import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from cc_crm.models.enums import ClosingStatus, SubmissionCancellationReason, SubmissionStatus
from cc_crm.schemas.base import EntityRead


class CandidateSubmissionBase(BaseModel):
    candidate_id: uuid.UUID
    client_company_id: uuid.UUID | None = None
    job_mandate_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None
    status: SubmissionStatus = SubmissionStatus.QUALIFICATION_CALL
    submitted_at: datetime | None = None
    summary: str | None = None
    sent_profile_text: str | None = None
    salary_at_submission: str | None = None
    fee_percentage: Decimal | None = None
    expected_fee: Decimal | None = None
    refund_terms: str | None = None
    feedback_summary: str | None = None
    next_step: str | None = None
    follow_up_at: datetime | None = None
    owner: str | None = None
    outlook_draft_created: bool = False
    email_sent: bool = False
    cancellation_reason: SubmissionCancellationReason | None = None


class CandidateSubmissionCreate(CandidateSubmissionBase):
    pass


class CandidateSubmissionUpdate(BaseModel):
    client_company_id: uuid.UUID | None = None
    job_mandate_id: uuid.UUID | None = None
    contact_person_id: uuid.UUID | None = None
    submitted_at: datetime | None = None
    summary: str | None = None
    sent_profile_text: str | None = None
    salary_at_submission: str | None = None
    fee_percentage: Decimal | None = None
    expected_fee: Decimal | None = None
    refund_terms: str | None = None
    feedback_summary: str | None = None
    next_step: str | None = None
    follow_up_at: datetime | None = None
    owner: str | None = None
    outlook_draft_created: bool | None = None
    email_sent: bool | None = None


class CandidateSubmissionTransition(BaseModel):
    status: SubmissionStatus
    client_company_id: uuid.UUID | None = None
    cancellation_reason: SubmissionCancellationReason | None = None
    reason: str | None = None
    changed_by: str | None = None


class CandidateSubmissionRead(CandidateSubmissionBase, EntityRead):
    last_activity_at: datetime
    closed_at: datetime | None
    pain_staerke: int | None = None
    entscheidungsklarheit: int | None = None
    markt_fit: int | None = None
    momentum: int | None = None
    closing_probability: float | None = None
    closing_status: ClosingStatus | None = None


class ClosingScoreInput(BaseModel):
    pain_staerke: int = Field(ge=0, le=5)
    entscheidungsklarheit: int = Field(ge=0, le=5)
    markt_fit: int = Field(ge=0, le=5)
    momentum: int | None = Field(default=None, ge=0, le=5)


class ClosingScoreRead(BaseModel):
    closing_probability: float
    closing_status: ClosingStatus
    action_recommendation: str
