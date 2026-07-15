import uuid

from fastapi import APIRouter, Response, status

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.schemas.region_modifier import (
    RegionModifierCreate,
    RegionModifierRead,
    RegionModifierUpdate,
)
from cc_crm.services.region_modifier import RegionModifierService

router = APIRouter(prefix="/region-modifiers")


@router.get("", response_model=list[RegionModifierRead])
def list_region_modifiers(session: DatabaseSession) -> list[RegionModifierRead]:
    return [
        RegionModifierRead.model_validate(item)
        for item in RegionModifierService(session).list(limit=500)
    ]


@router.post("", response_model=RegionModifierRead, status_code=status.HTTP_201_CREATED)
def create_region_modifier(
    payload: RegionModifierCreate, session: DatabaseSession
) -> RegionModifierRead:
    return RegionModifierRead.model_validate(RegionModifierService(session).create(payload))


@router.patch("/{region_modifier_id}", response_model=RegionModifierRead)
def update_region_modifier(
    region_modifier_id: uuid.UUID,
    payload: RegionModifierUpdate,
    session: DatabaseSession,
) -> RegionModifierRead:
    return RegionModifierRead.model_validate(
        RegionModifierService(session).update(region_modifier_id, payload)
    )


@router.delete("/{region_modifier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_region_modifier(region_modifier_id: uuid.UUID, session: DatabaseSession) -> Response:
    RegionModifierService(session).delete(region_modifier_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
