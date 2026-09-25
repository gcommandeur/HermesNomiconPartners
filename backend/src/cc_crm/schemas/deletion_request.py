import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from cc_crm.schemas.base import ORMModel


class DeletionRequestCreate(BaseModel):
    candidate_id: uuid.UUID
    requested_via: str = Field(min_length=1, max_length=240)


class DeletionRequestRead(ORMModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    requested_at: datetime
    requested_via: str
    deadline: datetime
    completed_at: datetime | None
    completed_by_user_id: uuid.UUID | None
    # Denormalisiert aus Candidate (siehe DeletionRequestService.list_open/
    # list_all) - erspart dem Frontend, fuer die Anzeige zusaetzlich den
    # kompletten Kandidatenbestand zu laden, nur um Namen aufzuloesen.
    candidate_first_name: str
    candidate_last_name: str
    candidate_number: str | None
