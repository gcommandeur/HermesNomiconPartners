import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from cc_crm.schemas.base import ORMModel


class ActivityCreate(BaseModel):
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    candidate_submission_id: uuid.UUID | None = None
    activity_type: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=240)
    details: str | None = None
    occurred_at: datetime | None = None


class ActivityUpdate(BaseModel):
    activity_type: str | None = Field(default=None, min_length=1, max_length=80)
    subject: str | None = Field(default=None, min_length=1, max_length=240)
    details: str | None = None
    occurred_at: datetime | None = None


class ActivityRead(ActivityCreate, ORMModel):
    id: uuid.UUID
    occurred_at: datetime
    # Wer die Aktivitaet ausgeloest hat (z.B. Mailversand) - None bei
    # automatischen/eingehenden. Basis der Autorenanzeige in der Timeline.
    sent_by_user_id: uuid.UUID | None = None
