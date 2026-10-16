# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Audit-Log-Eintraege der Arbeitnehmerüberlassung (gleiche Tabelle `audit_logs` wie bei
Prozessen, `entity_type` mit Praefix `staffing_`). Diese Einträge enthalten Lohn- und
Margenwerte; sie sind nur über `/audit-logs` (Admin) lesbar und tauchen NICHT in der
Kandidaten-Historie auf (die filtert auf `candidate` und `candidate_submission`)."""

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from cc_crm.models.recruiting import AuditLog
from cc_crm.services.audit_diff import changed_values, json_safe

ENTITY_WORKER = "staffing_worker"
ENTITY_CONTRACT = "staffing_contract"
ENTITY_ASSIGNMENT = "staffing_assignment"
ENTITY_LICENSE = "staffing_license"
ENTITY_TIMESHEET = "staffing_timesheet"


def log_created(
    session: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    values: Mapping[str, Any],
    changed_by: str | None,
) -> None:
    session.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action="created",
            changed_by=changed_by,
            new_values=json_safe(dict(values)),
        )
    )


def log_updated(
    session: Session,
    entity_type: str,
    entity: object,
    entity_id: uuid.UUID,
    values: Mapping[str, Any],
    changed_by: str | None,
    *,
    action: str = "updated",
) -> bool:
    """Schreibt nur dann einen Eintrag, wenn sich wirklich ein Feld ändert; Rückgabe: ob."""
    old, new = changed_values(entity, values)
    if not new:
        return False
    session.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changed_by=changed_by,
            old_values=old,
            new_values=new,
        )
    )
    return True


def log_event(
    session: Session,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    changed_by: str | None,
    new_values: Mapping[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changed_by=changed_by,
            new_values=None if new_values is None else json_safe(dict(new_values)),
        )
    )
