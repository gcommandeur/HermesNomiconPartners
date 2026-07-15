import uuid

from fastapi import APIRouter, Response, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.mailing_group import (
    MailingGroupCreate,
    MailingGroupMergeRequest,
    MailingGroupRead,
    MailingGroupUpdate,
)
from cc_crm.services.mailing_group import MailingGroupService

router = APIRouter(prefix="/mailing-groups")


@router.get("", response_model=list[MailingGroupRead])
def list_mailing_groups(session: DatabaseSession) -> list[MailingGroupRead]:
    return [
        MailingGroupRead.model_validate(item)
        for item in MailingGroupService(session).list(limit=500)
    ]


@router.post("", response_model=MailingGroupRead, status_code=status.HTTP_201_CREATED)
def create_mailing_group(payload: MailingGroupCreate, session: DatabaseSession) -> MailingGroupRead:
    return MailingGroupRead.model_validate(MailingGroupService(session).create(payload))


@router.patch("/{group_id}", response_model=MailingGroupRead)
def update_mailing_group(
    group_id: uuid.UUID,
    payload: MailingGroupUpdate,
    session: DatabaseSession,
) -> MailingGroupRead:
    return MailingGroupRead.model_validate(MailingGroupService(session).update(group_id, payload))


@router.post("/merge", response_model=MailingGroupRead)
def merge_mailing_groups(
    payload: MailingGroupMergeRequest, session: DatabaseSession
) -> MailingGroupRead:
    return MailingGroupRead.model_validate(MailingGroupService(session).merge(payload))


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mailing_group(group_id: uuid.UUID, session: DatabaseSession) -> Response:
    MailingGroupService(session).delete(group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
