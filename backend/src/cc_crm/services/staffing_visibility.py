# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Lohn- und Margendaten sehen und setzen nur Admins (Nutzervorgabe).

Lesen: die Read-Schemas behalten die Felder, der Wert wird fuer Nicht-Admins auf `None` gesetzt.
Schreiben: ein Nicht-Admin, der Lohn oder Verrechnungssatz mitschickt, bekommt 403 - auch bei
`null` (das waere ein Loeschen)."""

from typing import cast

from pydantic import BaseModel

from cc_crm.core.errors import PermissionDeniedError
from cc_crm.models.user import User
from cc_crm.schemas.staffing import StaffingAssignmentRead, StaffingWorkerRead

MONEY_FIELDS = ("hourly_wage", "billing_rate")


def redact[ReadT: StaffingWorkerRead | StaffingAssignmentRead](model: ReadT, user: User) -> ReadT:
    if user.is_admin:
        return model
    update = {field: None for field in MONEY_FIELDS if hasattr(model, field)}
    return cast("ReadT", model.model_copy(update=update))


def forbid_money_for_non_admin(payload: BaseModel, user: User) -> None:
    if user.is_admin:
        return
    if any(field in payload.model_fields_set for field in MONEY_FIELDS):
        raise PermissionDeniedError("Lohn und Verrechnungssatz duerfen nur Admins setzen.")
