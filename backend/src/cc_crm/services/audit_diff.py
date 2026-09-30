"""Ermittelt fuer einen AuditLog-Eintrag "updated" nur die Felder, die sich
durch ein Update tatsaechlich aendern - ein Speichern ohne echte Aenderung
erzeugt so keinen Eintrag."""

import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def _comparable(value: Any) -> Any:
    # SQLite liefert Zeitstempel ohne Zeitzone, Payloads kommen mit - ohne
    # Normalisierung waere jedes unveraenderte Datumsfeld eine "Aenderung".
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value


def changed_values(
    entity: object, values: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(alte, neue) Werte nur der Felder aus `values`, die sich vom aktuellen
    Stand von `entity` unterscheiden - JSON-tauglich fuer AuditLog."""
    old: dict[str, Any] = {}
    new: dict[str, Any] = {}
    for key, new_value in values.items():
        if not hasattr(entity, key):
            continue
        old_value = getattr(entity, key)
        if _comparable(old_value) == _comparable(new_value):
            continue
        old[key] = json_safe(old_value)
        new[key] = json_safe(new_value)
    return old, new
