import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WebhookEndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    event_types: list[str]
    is_active: bool
    created_at: datetime


class WebhookEndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=500)
    event_types: list[str] = Field(default_factory=lambda: ["*"], min_length=1)


class WebhookEndpointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=1, max_length=500)
    event_types: list[str] | None = Field(default=None, min_length=1)
    is_active: bool | None = None


class WebhookEndpointWithSecret(WebhookEndpointRead):
    """Nur bei Anlage/Erneuerung: das Geheimnis wird NUR EINMAL angezeigt."""

    secret: str


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint_id: uuid.UUID
    event_type: str
    status: str
    attempts: int
    response_status: int | None
    last_error: str | None
    delivered_at: datetime | None
    created_at: datetime
