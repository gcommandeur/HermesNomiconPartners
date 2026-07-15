import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.note import NoteCreate, NoteRead, NoteUpdate
from cc_crm.services.notes import NoteService

router = APIRouter(prefix="/notes")


@router.get("", response_model=list[NoteRead])
def list_notes(
    session: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[NoteRead]:
    return [
        NoteRead.model_validate(note)
        for note in NoteService(session).list(offset=offset, limit=limit)
    ]


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteCreate, session: DatabaseSession) -> NoteRead:
    return NoteRead.model_validate(NoteService(session).create(payload))


@router.get("/{note_id}", response_model=NoteRead)
def get_note(note_id: uuid.UUID, session: DatabaseSession) -> NoteRead:
    return NoteRead.model_validate(NoteService(session).get(note_id))


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdate,
    session: DatabaseSession,
) -> NoteRead:
    return NoteRead.model_validate(NoteService(session).update(note_id, payload))


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: uuid.UUID, session: DatabaseSession) -> Response:
    NoteService(session).delete(note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
