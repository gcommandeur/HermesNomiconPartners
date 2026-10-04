import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProposalKind = Literal["note", "task", "mail_draft"]
ProposalStatus = Literal["pending", "approved", "rejected"]
TargetType = Literal["candidate", "client", "contact"]

MAX_TEXT = 5000
MAX_MAIL_BODY = 10000


class NotePayload(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)


class TaskPayload(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=MAX_TEXT)
    due_at: datetime | None = None


class MailDraftPayload(BaseModel):
    subject: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=MAX_MAIL_BODY)


PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "note": NotePayload,
    "task": TaskPayload,
    "mail_draft": MailDraftPayload,
}


class AiProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ProposalKind
    status: ProposalStatus
    target_type: TargetType | None
    target_id: uuid.UUID | None
    # Bezeichnung des Bezugsobjekts (Name des Kandidaten/der Kanzlei/des Kontakts).
    target_label: str | None = None
    # E-Mail des Empfaengers (nur mail_draft) - kommt aus dem Datensatz, nie von Claude.
    recipient_email: str | None = None
    payload: dict[str, Any]
    created_by_user_id: uuid.UUID
    created_by_name: str | None = None
    decided_by_user_id: uuid.UUID | None
    decided_at: datetime | None
    decision_note: str | None
    result_entity_type: str | None
    result_entity_id: uuid.UUID | None
    created_at: datetime


class AiProposalSummary(BaseModel):
    enabled: bool
    pending: int


class AiProposalApprove(BaseModel):
    """Freigabe; mit `payload` wird der Vorschlag vorher bearbeitet uebernommen."""

    payload: dict[str, Any] | None = None


class AiProposalReject(BaseModel):
    decision_note: str | None = Field(default=None, max_length=500)
