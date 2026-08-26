import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from cc_crm.models.enums import (
    ClosingStatus,
    FeedbackType,
    SubmissionCancellationReason,
    SubmissionStatus,
)
from cc_crm.schemas.base import EntityRead
from cc_crm.schemas.recruiting import FeedbackRead


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
    # Zustaendiger Mitarbeiter (Komfort-Filter, keine Sichtbarkeitsgrenze -
    # siehe models/candidate.py::owner_user_id). Nicht zu verwechseln mit dem
    # bestehenden `owner`-Freitextfeld oben.
    owner_user_id: uuid.UUID | None = None


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
    owner_user_id: uuid.UUID | None = None


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
    # Expliziter Abschluss NACH einem Placement (siehe models/submission.py::
    # archived_at) - None ist der Normalfall, blendet den Prozess NUR aus
    # dem Kanban aus (client-seitig gefiltert), aendert sonst nichts.
    archived_at: datetime | None = None


class ClosingScoreInput(BaseModel):
    pain_staerke: int = Field(ge=0, le=5)
    entscheidungsklarheit: int = Field(ge=0, le=5)
    markt_fit: int = Field(ge=0, le=5)
    momentum: int | None = Field(default=None, ge=0, le=5)


class ClosingScoreRead(BaseModel):
    closing_probability: float
    closing_status: ClosingStatus
    action_recommendation: str


class CandidateQuickLogCreate(BaseModel):
    """Payload fuer POST /candidates/{id}/quick-log - legt bei Bedarf
    automatisch einen Prozess an (siehe RecruitingProcessService.quick_log),
    ohne dass vorher eine separate "Prozess erstellen"-Aktion noetig ist.
    `stage` ist auf qualification_call/cv_in/cv_out begrenzt (validiert
    in RecruitingProcessService.quick_log)."""

    stage: SubmissionStatus
    feedback_type: FeedbackType
    feedback_text: str = Field(min_length=1)
    received_at: datetime
    next_step: str | None = None


class CandidateQuickLogResult(BaseModel):
    submission: CandidateSubmissionRead
    feedback: FeedbackRead


class FeedbackCreateResult(BaseModel):
    """Antwort von POST /submissions/{id}/feedback - enthaelt neben der neu
    angelegten Notiz auch den (ggf. per `target_status` aktualisierten)
    Submission-Stand, damit das Frontend (feedback-panel.tsx) einen
    Statuswechsel ohne zusaetzlichen Request uebernehmen kann."""

    feedback: FeedbackRead
    submission: CandidateSubmissionRead


class CandidateStageSummary(BaseModel):
    """Anzahl erreichter Ereignisse je Stufe ueber ALLE Submissions eines
    Kandidaten hinweg (auch ueber mehrere Kanzleien) - Basis der Prozess-
    Timeline auf der Kandidat-Detailseite (siehe
    RecruitingProcessService.stage_summary)."""

    qualification_call: int = 0
    cv_in: int = 0
    cv_out: int = 0
    interview: int = 0
    offer: int = 0
    placement: int = 0
