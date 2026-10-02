import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.schemas.note import NoteCreate, NoteRead, NoteUpdate
from cc_crm.services.notes import NoteService

router = APIRouter(prefix="/notes")


@router.get("", response_model=list[NoteRead])
def list_notes(
    session: DatabaseSession,
    candidate_id: uuid.UUID | None = None,
    client_company_id: uuid.UUID | None = None,
    submission_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[NoteRead]:
    # Ohne candidate_id/client_company_id/submission_id weiterhin die volle,
    # ungefilterte Liste (bisheriges Verhalten). Mit candidate_id, aber ohne
    # submission_id, liefert NoteRepository.filtered() gezielt nur die
    # allgemeinen (nicht prozessgebundenen) Notizen - Basis fuer den
    # "Notizen"-Tab am Kandidaten.
    if candidate_id is None and client_company_id is None and submission_id is None:
        notes = NoteService(session).list(offset=offset, limit=limit)
    else:
        notes = NoteService(session).notes.filtered(
            candidate_id=candidate_id,
            client_company_id=client_company_id,
            submission_id=submission_id,
            offset=offset,
            limit=limit,
        )
    return NoteService(session).read_many(notes)


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate, session: DatabaseSession, current_user: CurrentUser
) -> NoteRead:
    service = NoteService(session)
    return service.read_one(service.create(payload, current_user.id))


@router.get("/{note_id}", response_model=NoteRead)
def get_note(note_id: uuid.UUID, session: DatabaseSession) -> NoteRead:
    service = NoteService(session)
    return service.read_one(service.get(note_id))


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdate,
    session: DatabaseSession,
) -> NoteRead:
    service = NoteService(session)
    return service.read_one(service.update(note_id, payload))


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: uuid.UUID, session: DatabaseSession) -> Response:
    NoteService(session).delete(note_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
