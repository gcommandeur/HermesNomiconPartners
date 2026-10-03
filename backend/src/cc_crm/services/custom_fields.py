"""Eigene Felder (Zusatzfelder): Definitionen verwalten und Werte pruefen.

Werte werden als JSON-Dict `{schluessel: wert}` am Objekt gespeichert
(`custom_fields`). Beim Speichern gilt "Ersetzen": der Client schickt das
komplette Dict, Schluessel mit `None`/leerem Wert werden entfernt. Unbekannte
oder deaktivierte Schluessel sind ein Fehler, ausser sie stehen schon im
gespeicherten Stand (ein deaktiviertes Feld darf seinen alten Wert behalten).
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.custom_field import (
    CUSTOM_FIELD_ENTITIES,
    CUSTOM_FIELD_TYPES,
    CustomFieldDefinition,
)

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,59}$")
MAX_TEXT_LENGTH = 1000


def slugify_key(label: str) -> str:
    table = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower().translate(table)).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"feld_{slug}" if slug else "feld"
    return slug[:60]


class CustomFieldService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(
        self, entity_type: str | None = None, *, include_inactive: bool = False
    ) -> list[CustomFieldDefinition]:
        statement = select(CustomFieldDefinition).order_by(
            CustomFieldDefinition.entity_type,
            CustomFieldDefinition.sort_order,
            CustomFieldDefinition.label,
        )
        if entity_type:
            statement = statement.where(CustomFieldDefinition.entity_type == entity_type)
        if not include_inactive:
            statement = statement.where(CustomFieldDefinition.is_active.is_(True))
        return list(self.session.scalars(statement))

    def get(self, definition_id: uuid.UUID) -> CustomFieldDefinition:
        definition = self.session.get(CustomFieldDefinition, definition_id)
        if definition is None:
            raise EntityNotFoundError("Eigenes Feld nicht gefunden")
        return definition

    def create(
        self,
        *,
        entity_type: str,
        label: str,
        field_type: str,
        options: list[str],
        key: str | None = None,
    ) -> CustomFieldDefinition:
        if entity_type not in CUSTOM_FIELD_ENTITIES:
            raise BusinessRuleError("Unbekannter Objekttyp.")
        if field_type not in CUSTOM_FIELD_TYPES:
            raise BusinessRuleError("Unbekannter Feldtyp.")
        key = (key or slugify_key(label)).strip()
        if not _KEY_RE.match(key):
            raise BusinessRuleError(
                "Der Schluessel darf nur Kleinbuchstaben, Ziffern und _ enthalten "
                "und muss mit einem Buchstaben beginnen."
            )
        cleaned = _clean_options(field_type, options)
        existing = self.session.scalar(
            select(CustomFieldDefinition).where(
                CustomFieldDefinition.entity_type == entity_type, CustomFieldDefinition.key == key
            )
        )
        if existing is not None:
            raise BusinessRuleError(f"Ein Feld mit dem Schluessel '{key}' gibt es bereits.")
        next_order = len(self.list_all(entity_type, include_inactive=True))
        definition = CustomFieldDefinition(
            entity_type=entity_type,
            key=key,
            label=label.strip(),
            field_type=field_type,
            options=cleaned,
            sort_order=next_order,
        )
        self.session.add(definition)
        self.session.commit()
        return definition

    def update(
        self,
        definition_id: uuid.UUID,
        *,
        label: str | None,
        options: list[str] | None,
        sort_order: int | None,
        is_active: bool | None,
    ) -> CustomFieldDefinition:
        """Typ und Schluessel bleiben unveraenderlich (gespeicherte Werte
        wuerden sonst ihre Bedeutung verlieren)."""
        definition = self.get(definition_id)
        if label is not None:
            definition.label = label.strip()
        if options is not None:
            definition.options = _clean_options(definition.field_type, options)
        if sort_order is not None:
            definition.sort_order = sort_order
        if is_active is not None:
            definition.is_active = is_active
        self.session.commit()
        return definition

    def validate_values(
        self,
        entity_type: str,
        values: dict[str, Any],
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        definitions = {
            item.key: item for item in self.list_all(entity_type, include_inactive=True)
        }
        existing = existing or {}
        cleaned: dict[str, Any] = {}
        for key, raw in values.items():
            definition = definitions.get(key)
            if definition is None:
                raise BusinessRuleError(f"Unbekanntes eigenes Feld: {key}")
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                continue
            if not definition.is_active and existing.get(key) != raw:
                raise BusinessRuleError(f"Das Feld '{definition.label}' ist deaktiviert.")
            cleaned[key] = _coerce(definition, raw)
        return cleaned

    def filter_kind(self, entity_type: str, key: str) -> str:
        definition = next(
            (item for item in self.list_all(entity_type, include_inactive=True) if item.key == key),
            None,
        )
        if definition is None:
            raise BusinessRuleError(f"Unbekanntes eigenes Feld: {key}")
        return definition.field_type


def _clean_options(field_type: str, options: list[str]) -> list[str]:
    if field_type != "select":
        return []
    cleaned = list(dict.fromkeys(option.strip() for option in options if option.strip()))
    if not cleaned:
        raise BusinessRuleError("Ein Auswahlfeld braucht mindestens eine Option.")
    return cleaned


def _coerce(definition: CustomFieldDefinition, raw: Any) -> Any:
    label = definition.label
    kind = definition.field_type
    if kind == "text":
        if not isinstance(raw, str):
            raise BusinessRuleError(f"'{label}' erwartet Text.")
        if len(raw) > MAX_TEXT_LENGTH:
            raise BusinessRuleError(f"'{label}' ist zu lang (max. {MAX_TEXT_LENGTH} Zeichen).")
        return raw.strip()
    if kind == "number":
        if isinstance(raw, bool) or not isinstance(raw, int | float):
            raise BusinessRuleError(f"'{label}' erwartet eine Zahl.")
        return raw
    if kind == "boolean":
        if not isinstance(raw, bool):
            raise BusinessRuleError(f"'{label}' erwartet Ja/Nein.")
        return raw
    if kind == "date":
        try:
            return date.fromisoformat(str(raw)).isoformat()
        except ValueError as exc:
            raise BusinessRuleError(f"'{label}' erwartet ein Datum (JJJJ-MM-TT).") from exc
    if kind == "select":
        if raw not in definition.options:
            raise BusinessRuleError(f"'{raw}' ist keine Option von '{label}'.")
        return raw
    raise BusinessRuleError("Unbekannter Feldtyp.")
