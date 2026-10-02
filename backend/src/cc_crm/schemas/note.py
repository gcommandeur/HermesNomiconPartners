import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from cc_crm.schemas.base import EntityRead


class NoteBase(BaseModel):
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    candidate_submission_id: uuid.UUID | None = None
    body: str = Field(min_length=1)


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    body: str = Field(min_length=1)


class NoteRead(NoteBase, EntityRead):
    created_by_user_id: uuid.UUID | None = None
    # Anzeigename (Fallback E-Mail) des Autors - None bei Alt-/Systemnotizen.
    created_by_name: str | None = None


class CandidateCommentRead(BaseModel):
    """Eine Notiz ODER ein Prozess-Feedback zu einem Kandidaten, einheitlich
    mit Autor - Basis der Kandidaten-Timeline (GET /candidates/{id}/comments).
    Fuer alle Nutzer sichtbar (Kommentare sind gemeinsames Agenturwissen,
    kein Teil der Prozess-Sichtbarkeitsgrenze)."""

    kind: str  # "note" | "feedback"
    id: uuid.UUID
    occurred_at: datetime
    author: str | None
    text: str
    # Nur Feedback: Stufe, in der es erfasst wurde, und der Prozess.
    stage: str | None = None
    feedback_type: str | None = None
    submission_id: uuid.UUID | None = None
