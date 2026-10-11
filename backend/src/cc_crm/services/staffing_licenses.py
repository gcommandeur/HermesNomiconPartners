# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Erlaubnis zur Arbeitnehmerueberlassung (Bundesagentur fuer Arbeit)."""

import uuid

from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.staffing import StaffingLicense
from cc_crm.models.user import User
from cc_crm.repositories.staffing import StaffingLicenseRepository
from cc_crm.schemas.staffing import StaffingLicenseCreate, StaffingLicenseUpdate
from cc_crm.services import staffing_audit as audit


class StaffingLicenseService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.licenses = StaffingLicenseRepository(session)

    def get(self, license_id: uuid.UUID) -> StaffingLicense:
        found = self.licenses.get(license_id)
        if found is None:
            raise EntityNotFoundError("Erlaubnis nicht gefunden")
        return found

    def list(self) -> list[StaffingLicense]:
        return list(self.licenses.ordered())

    def create(self, payload: StaffingLicenseCreate, actor: User) -> StaffingLicense:
        values = payload.model_dump()
        created = self.licenses.create(values)
        audit.log_created(self.session, audit.ENTITY_LICENSE, created.id, values, actor.email)
        self.session.commit()
        return created

    def update(
        self, license_id: uuid.UUID, payload: StaffingLicenseUpdate, actor: User
    ) -> StaffingLicense:
        found = self.get(license_id)
        values = payload.model_dump(exclude_unset=True)
        for required in ("authority", "valid_from", "reminder_days"):
            if required in values and values[required] is None:
                values.pop(required)
        start = values.get("valid_from", found.valid_from)
        end = values.get("valid_to", found.valid_to)
        if end is not None and end < start:
            raise BusinessRuleError("Gueltig-bis liegt vor Gueltig-ab.")
        audit.log_updated(self.session, audit.ENTITY_LICENSE, found, found.id, values, actor.email)
        self.licenses.update(found, values)
        self.session.commit()
        return found
