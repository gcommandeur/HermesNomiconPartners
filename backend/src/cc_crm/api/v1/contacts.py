import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.contact_person import (
    ContactPersonCreate,
    ContactPersonRead,
    ContactPersonUpdate,
)
from cc_crm.services.contacts import ContactPersonService

router = APIRouter(prefix="/contacts")


@router.get("", response_model=list[ContactPersonRead])
def list_contacts(
    session: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ContactPersonRead]:
    return [
        ContactPersonRead.model_validate(contact)
        for contact in ContactPersonService(session).list(offset=offset, limit=limit)
    ]


@router.post("", response_model=ContactPersonRead, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactPersonCreate,
    session: DatabaseSession,
) -> ContactPersonRead:
    return ContactPersonRead.model_validate(ContactPersonService(session).create(payload))


@router.get("/{contact_id}", response_model=ContactPersonRead)
def get_contact(contact_id: uuid.UUID, session: DatabaseSession) -> ContactPersonRead:
    return ContactPersonRead.model_validate(ContactPersonService(session).get(contact_id))


@router.patch("/{contact_id}", response_model=ContactPersonRead)
def update_contact(
    contact_id: uuid.UUID,
    payload: ContactPersonUpdate,
    session: DatabaseSession,
) -> ContactPersonRead:
    return ContactPersonRead.model_validate(
        ContactPersonService(session).update(contact_id, payload)
    )


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(contact_id: uuid.UUID, session: DatabaseSession) -> Response:
    ContactPersonService(session).delete(contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
