import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["candidate", "client", "contact"]
FieldType = Literal["text", "number", "date", "boolean", "select"]


class CustomFieldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: EntityType
    key: str
    label: str
    field_type: FieldType
    options: list[str]
    sort_order: int
    is_active: bool


class CustomFieldCreate(BaseModel):
    entity_type: EntityType
    label: str = Field(min_length=1, max_length=120)
    field_type: FieldType
    options: list[str] = Field(default_factory=list)
    # Optional: sonst aus der Bezeichnung abgeleitet (z. B. "Führerschein" -> fuehrerschein).
    key: str | None = Field(default=None, max_length=60)


class CustomFieldUpdate(BaseModel):
    """Typ und Schluessel sind nach dem Anlegen unveraenderlich."""

    label: str | None = Field(default=None, min_length=1, max_length=120)
    options: list[str] | None = None
    sort_order: int | None = None
    is_active: bool | None = None
