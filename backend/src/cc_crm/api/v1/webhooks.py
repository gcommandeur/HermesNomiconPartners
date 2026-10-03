import uuid

from fastapi import APIRouter, status

from cc_crm.api.dependencies import AdminUser, DatabaseSession
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.schemas.webhook import (
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
    WebhookEndpointWithSecret,
)
from cc_crm.services.webhooks import WebhookService

router = APIRouter(prefix="/webhooks")

# Alles hier ist Admin-Sache: Webhooks verlassen das System Richtung Dritter.


def _with_secret(endpoint: object, secret: str) -> WebhookEndpointWithSecret:
    base = WebhookEndpointRead.model_validate(endpoint)
    return WebhookEndpointWithSecret(**base.model_dump(), secret=secret)


@router.get("", response_model=list[WebhookEndpointRead])
def list_webhooks(session: DatabaseSession, _admin: AdminUser) -> list[WebhookEndpointRead]:
    return [WebhookEndpointRead.model_validate(item) for item in WebhookService(session).list_all()]


@router.post("", response_model=WebhookEndpointWithSecret, status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookEndpointCreate, session: DatabaseSession, admin: AdminUser
) -> WebhookEndpointWithSecret:
    endpoint, secret = WebhookService(session).create(
        payload.name, payload.url, payload.event_types, admin.id
    )
    AuditLogRepository(session).create(
        {
            "entity_type": "webhook_endpoint",
            "entity_id": endpoint.id,
            "action": "created",
            "changed_by": admin.email,
        }
    )
    session.commit()
    return _with_secret(endpoint, secret)


@router.patch("/{endpoint_id}", response_model=WebhookEndpointRead)
def update_webhook(
    endpoint_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    session: DatabaseSession,
    admin: AdminUser,
) -> WebhookEndpointRead:
    endpoint = WebhookService(session).update(
        endpoint_id,
        name=payload.name,
        url=payload.url,
        event_types=payload.event_types,
        is_active=payload.is_active,
    )
    AuditLogRepository(session).create(
        {
            "entity_type": "webhook_endpoint",
            "entity_id": endpoint.id,
            "action": "updated",
            "changed_by": admin.email,
        }
    )
    session.commit()
    return WebhookEndpointRead.model_validate(endpoint)


@router.post("/{endpoint_id}/rotate-secret", response_model=WebhookEndpointWithSecret)
def rotate_webhook_secret(
    endpoint_id: uuid.UUID, session: DatabaseSession, admin: AdminUser
) -> WebhookEndpointWithSecret:
    endpoint, secret = WebhookService(session).rotate_secret(endpoint_id)
    AuditLogRepository(session).create(
        {
            "entity_type": "webhook_endpoint",
            "entity_id": endpoint.id,
            "action": "secret_rotated",
            "changed_by": admin.email,
        }
    )
    session.commit()
    return _with_secret(endpoint, secret)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(endpoint_id: uuid.UUID, session: DatabaseSession, admin: AdminUser) -> None:
    WebhookService(session).delete(endpoint_id)
    AuditLogRepository(session).create(
        {
            "entity_type": "webhook_endpoint",
            "entity_id": endpoint_id,
            "action": "deleted",
            "changed_by": admin.email,
        }
    )
    session.commit()


@router.get("/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryRead])
def list_deliveries(
    endpoint_id: uuid.UUID, session: DatabaseSession, _admin: AdminUser, limit: int = 50
) -> list[WebhookDeliveryRead]:
    items = WebhookService(session).deliveries(endpoint_id, min(max(limit, 1), 200))
    return [WebhookDeliveryRead.model_validate(item) for item in items]


@router.post("/{endpoint_id}/test", response_model=WebhookDeliveryRead)
def send_test_event(
    endpoint_id: uuid.UUID, session: DatabaseSession, _admin: AdminUser
) -> WebhookDeliveryRead:
    return WebhookDeliveryRead.model_validate(WebhookService(session).send_test(endpoint_id))


@router.post("/deliveries/{delivery_id}/retry", response_model=WebhookDeliveryRead)
def retry_delivery(
    delivery_id: uuid.UUID, session: DatabaseSession, _admin: AdminUser
) -> WebhookDeliveryRead:
    return WebhookDeliveryRead.model_validate(WebhookService(session).retry_delivery(delivery_id))
