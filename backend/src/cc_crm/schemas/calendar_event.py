import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

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
    # Einladung per Outlook: Teilnehmer + eigener (kandidatenfreundlicher) Text.
    # Interne `notes` werden NIE an Teilnehmer geschickt. Setzt voraus, dass der
    # Terminbesitzer mit Microsoft angemeldet ist (sonst Fehler beim Anlegen).
    attendee_email: EmailStr | None = None
    attendee_name: str | None = Field(default=None, max_length=240)
    invite_message: str | None = None
    online_meeting: bool = False
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
    attendee_email: EmailStr | None = None
    attendee_name: str | None = Field(default=None, max_length=240)
    invite_message: str | None = None
    online_meeting: bool | None = None


class CalendarEventRead(CalendarEventBase, EntityRead):
    owner_user_id: uuid.UUID
    created_by_user_id: uuid.UUID
    # Nur informativ, nie ueber Create/Update setzbar - wird ausschliesslich
    # von RecruitingProcessService.create_interview automatisch befuellt.
    # Zeigt dem Frontend an, dass dieser Termin aus einem Interview stammt
    # (siehe calendar-event-modal.tsx: Hinweis + Link zum Prozess).
    source_interview_id: uuid.UUID | None = None
    attendee_email: str | None = None
    attendee_name: str | None = None
    invite_message: str | None = None
    online_meeting: bool = False
    online_meeting_url: str | None = None
    attendee_response: str | None = None
