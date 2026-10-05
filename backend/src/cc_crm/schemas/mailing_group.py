import uuid
from typing import Literal

from pydantic import BaseModel, Field

from cc_crm.schemas.base import EntityRead


class MailingRecipient(BaseModel):
    kind: Literal["candidate", "client", "contact"]
    id: str
    name: str
    email: str | None = None


class MailingGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    recipients: list[MailingRecipient] = Field(default_factory=list)
    template_key: str | None = None
    context_candidate_id: uuid.UUID | None = None


class MailingGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    recipients: list[MailingRecipient] | None = None
    template_key: str | None = None


class MailingGroupRead(MailingGroupCreate, EntityRead):
    pass


class MailingGroupMergeRequest(BaseModel):
    """Vereinigt mehrere bestehende Gruppen (per ID) nach E-Mail-Adresse
    dedupliziert zu einer neuen oder ueberschriebenen Gruppe."""

    group_ids: list[str] = Field(min_length=1)
    target_name: str = Field(min_length=1, max_length=160)
    overwrite_group_id: str | None = None
