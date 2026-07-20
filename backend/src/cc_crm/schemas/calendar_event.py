import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from cc_crm.models.enums import CalendarEventType
from cc_crm.schemas.base import EntityRead


class CalendarEventBase(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    event_type: CalendarEventType = CalendarEventType.OTHER
    start_at: datetime
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=240)
    notes: str | None = None
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    candidate_submission_id: uuid.UUID | None = None
    reminder_minutes_before: int = Field(default=30, ge=0)


class CalendarEventCreate(CalendarEventBase):
    # Vom Client optional mitgeschickt, aber serverseitig ueberschrieben fuer
    # Nicht-Admins (siehe CalendarEventService.create) - Admins duerfen damit
    # einen Termin fuer einen anderen Nutzer anlegen.
    owner_user_id: uuid.UUID | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    event_type: CalendarEventType | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str | None = Field(default=None, max_length=240)
    notes: str | None = None
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    candidate_submission_id: uuid.UUID | None = None
    reminder_minutes_before: int | None = Field(default=None, ge=0)


class CalendarEventRead(CalendarEventBase, EntityRead):
    owner_user_id: uuid.UUID
    created_by_user_id: uuid.UUID
    # Nur informativ, nie ueber Create/Update setzbar - wird ausschliesslich
    # von RecruitingProcessService.create_interview automatisch befuellt.
    # Zeigt dem Frontend an, dass dieser Termin aus einem Interview stammt
    # (siehe calendar-event-modal.tsx: Hinweis + Link zum Prozess).
    source_interview_id: uuid.UUID | None = None
