import uuid

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
    pass
