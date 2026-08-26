import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from cc_crm.models.enums import TaskPriority, TaskStatus
from cc_crm.schemas.base import EntityRead


class TaskBase(BaseModel):
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    candidate_submission_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    description: str | None = None
    due_at: datetime | None = None
    status: TaskStatus = TaskStatus.OPEN
    priority: TaskPriority = TaskPriority.NORMAL
    # Zustaendiger Mitarbeiter (Komfort-Filter, keine Sichtbarkeitsgrenze -
    # siehe models/candidate.py::owner_user_id).
    owner_user_id: uuid.UUID | None = None


class TaskCreate(TaskBase):
    source_mail_message_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = None
    due_at: datetime | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    owner_user_id: uuid.UUID | None = None


class TaskRead(TaskBase, EntityRead):
    snoozed_until: datetime | None = None
    source_mail_message_id: uuid.UUID | None = None
    resolution_outcome: str | None = None


class TaskSnoozeRequest(BaseModel):
    days: int = Field(ge=1, le=90)


class TaskResolveRequest(BaseModel):
    # "done": schlichtes Erledigt fuer alles, was keinen Kalendereintrag
    # braucht (abgearbeitet, anderweitig geklaert). "not_relevant": Fehl-
    # zuordnung (Werbemail, falscher Treffer) - eigener Wert statt unter
    # "no_response" mitzuzaehlen, damit spaeter auswertbar ist, wie oft der
    # Mail-Agent danebenliegt (Nutzer-Vorgabe).
    outcome: Literal["no_response", "meeting_scheduled", "done", "not_relevant"]
    # NUR bei outcome="meeting_scheduled" Pflicht - siehe TaskService.resolve.
    scheduled_at: datetime | None = None
    notes: str | None = None
