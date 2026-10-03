import uuid

from fastapi import APIRouter, status

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.custom_field import (
    CustomFieldCreate,
    CustomFieldRead,
    CustomFieldUpdate,
    EntityType,
)
from cc_crm.services.custom_fields import CustomFieldService

router = APIRouter(prefix="/custom-fields")


@router.get("", response_model=list[CustomFieldRead])
def list_custom_fields(
    session: DatabaseSession,
    current_user: CurrentUser,
    entity_type: EntityType | None = None,
    include_inactive: bool = False,
) -> list[CustomFieldRead]:
    """Fuer jeden Nutzer (die Felder erscheinen in den Masken); deaktivierte nur fuer Admins."""
    only_active = not (include_inactive and current_user.is_admin)
    items = CustomFieldService(session).list_all(entity_type, include_inactive=not only_active)
    return [CustomFieldRead.model_validate(item) for item in items]


@router.post("", response_model=CustomFieldRead, status_code=status.HTTP_201_CREATED)
def create_custom_field(
    payload: CustomFieldCreate, session: DatabaseSession, admin: AdminUser
) -> CustomFieldRead:
    item = CustomFieldService(session).create(
        entity_type=payload.entity_type,
        label=payload.label,
        field_type=payload.field_type,
        options=payload.options,
        key=payload.key,
    )
    AuditLogRepository(session).create(
        {
            "entity_type": "custom_field",
            "entity_id": item.id,
            "action": "created",
            "changed_by": admin.email,
        }
    )
    session.commit()
    return CustomFieldRead.model_validate(item)


@router.patch("/{definition_id}", response_model=CustomFieldRead)
def update_custom_field(
    definition_id: uuid.UUID,
    payload: CustomFieldUpdate,
    session: DatabaseSession,
    admin: AdminUser,
) -> CustomFieldRead:
    item = CustomFieldService(session).update(
        definition_id,
        label=payload.label,
        options=payload.options,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    AuditLogRepository(session).create(
        {
            "entity_type": "custom_field",
            "entity_id": item.id,
            "action": "updated",
            "changed_by": admin.email,
        }
    )
    session.commit()
    return CustomFieldRead.model_validate(item)
