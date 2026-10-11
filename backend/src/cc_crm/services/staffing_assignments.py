# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Ueberlassungsvertraege, Einsaetze und Pflicht-Checkliste.

Statuswechsel (Aktivierung mit Erlaubnis- und Checklistenpruefung) siehe
services/staffing_activation.py."""

import uuid
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import (
    CHECKLIST_KEYS,
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingChecklistItem,
    StaffingContract,
    StaffingWorkerStatus,
)
from cc_crm.models.user import User
from cc_crm.repositories.staffing import (
    AssignmentRow,
    ContractRow,
    StaffingAssignmentRepository,
    StaffingContractRepository,
    StaffingWorkerRepository,
)
from cc_crm.schemas.staffing import (
    StaffingAssignmentCreate,
    StaffingAssignmentDetail,
    StaffingAssignmentRead,
    StaffingAssignmentUpdate,
    StaffingChecklistItemRead,
    StaffingChecklistItemUpdate,
    StaffingContractCreate,
    StaffingContractRead,
    StaffingContractUpdate,
)
from cc_crm.services import staffing_audit as audit

# Status, in denen ein Einsatz noch aenderbar ist (beendet/abgebrochen = Nachweis, eingefroren).
_EDITABLE = (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)


def contract_read(row: ContractRow) -> StaffingContractRead:
    c = row.contract
    return StaffingContractRead(
        id=c.id,
        created_at=c.created_at,
        updated_at=c.updated_at,
        client_company_id=c.client_company_id,
        client_name=row.client_name,
        contract_number=c.contract_number,
        valid_from=c.valid_from,
        valid_to=c.valid_to,
        industry_sector=c.industry_sector,
        document_id=c.document_id,
        status=c.status,
        notes=c.notes,
    )


def assignment_read(row: AssignmentRow) -> StaffingAssignmentRead:
    a = row.assignment
    return StaffingAssignmentRead(
        id=a.id,
        created_at=a.created_at,
        updated_at=a.updated_at,
        worker_id=a.worker_id,
        worker_name=row.worker_name,
        client_company_id=a.client_company_id,
        client_name=row.client_name,
        contract_id=a.contract_id,
        owner_user_id=a.owner_user_id,
        start_date=a.start_date,
        planned_end_date=a.planned_end_date,
        actual_end_date=a.actual_end_date,
        location=a.location,
        activity=a.activity,
        billing_rate=a.billing_rate,
        hourly_wage=a.hourly_wage,
        status=a.status,
        notes=a.notes,
        checklist_done=row.checklist_done,
        checklist_total=row.checklist_total,
    )


class StaffingContractService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.contracts = StaffingContractRepository(session)

    def get_row(self, contract_id: uuid.UUID) -> ContractRow:
        row = self.contracts.row(contract_id)
        if row is None:
            raise EntityNotFoundError("Vertrag nicht gefunden")
        return row

    def create(self, payload: StaffingContractCreate, actor: User) -> ContractRow:
        if self.session.get(ClientCompany, payload.client_company_id) is None:
            raise EntityNotFoundError("Kunde nicht gefunden")
        values = payload.model_dump()
        contract = self.contracts.create(values)
        audit.log_created(self.session, audit.ENTITY_CONTRACT, contract.id, values, actor.email)
        self.session.commit()
        return self.get_row(contract.id)

    def update(
        self, contract_id: uuid.UUID, payload: StaffingContractUpdate, actor: User
    ) -> ContractRow:
        contract: StaffingContract = self.get_row(contract_id).contract
        values = payload.model_dump(exclude_unset=True)
        if values.get("status") is None:
            values.pop("status", None)
        start = values.get("valid_from", contract.valid_from)
        end = values.get("valid_to", contract.valid_to)
        if start and end and end < start:
            raise BusinessRuleError("Vertragsende liegt vor dem Beginn.")
        audit.log_updated(
            self.session, audit.ENTITY_CONTRACT, contract, contract.id, values, actor.email
        )
        self.contracts.update(contract, values)
        self.session.commit()
        return self.get_row(contract.id)


class StaffingAssignmentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.assignments = StaffingAssignmentRepository(session)
        self.workers = StaffingWorkerRepository(session)
        self.contracts = StaffingContractRepository(session)

    def get_row(self, assignment_id: uuid.UUID) -> AssignmentRow:
        row = self.assignments.row(assignment_id)
        if row is None:
            raise EntityNotFoundError("Einsatz nicht gefunden")
        return row

    def detail(self, assignment_id: uuid.UUID) -> StaffingAssignmentDetail:
        row = self.get_row(assignment_id)
        order = {key: index for index, key in enumerate(CHECKLIST_KEYS)}
        items = sorted(
            self.assignments.checklist(assignment_id), key=lambda item: order[item.item_key]
        )
        return StaffingAssignmentDetail(
            **assignment_read(row).model_dump(),
            checklist=[StaffingChecklistItemRead.model_validate(item) for item in items],
        )

    def _check_contract(self, contract_id: uuid.UUID, client_company_id: uuid.UUID) -> None:
        contract = self.contracts.get(contract_id)
        if contract is None:
            raise EntityNotFoundError("Vertrag nicht gefunden")
        if contract.client_company_id != client_company_id:
            raise BusinessRuleError("Der Vertrag gehoert zu einem anderen Kunden.")

    def create(self, payload: StaffingAssignmentCreate, actor: User) -> AssignmentRow:
        worker = self.workers.get(payload.worker_id)
        if worker is None:
            raise EntityNotFoundError("Leiharbeitnehmer nicht gefunden")
        if worker.status in (StaffingWorkerStatus.LEFT, StaffingWorkerStatus.DORMANT):
            raise BusinessRuleError(
                "Fuer ausgeschiedene oder ruhende Leiharbeitnehmer kann kein Einsatz "
                "angelegt werden."
            )
        if self.session.get(ClientCompany, payload.client_company_id) is None:
            raise EntityNotFoundError("Kunde nicht gefunden")
        if payload.contract_id is not None:
            self._check_contract(payload.contract_id, payload.client_company_id)
        owner_id = payload.owner_user_id or actor.id
        if self.session.get(User, owner_id) is None:
            raise EntityNotFoundError("Disponent nicht gefunden")
        values = payload.model_dump()
        values["owner_user_id"] = owner_id
        # Lohn: ohne Angabe der Stammwert des Leiharbeitnehmers (Momentaufnahme zum Einsatzbeginn).
        if values.get("hourly_wage") is None:
            values["hourly_wage"] = worker.hourly_wage
        try:
            assignment = self.assignments.create(values)
            for key in CHECKLIST_KEYS:
                self.session.add(StaffingChecklistItem(assignment_id=assignment.id, item_key=key))
            audit.log_created(
                self.session, audit.ENTITY_ASSIGNMENT, assignment.id, values, actor.email
            )
            self.session.commit()
        except IntegrityError as exception:
            self.session.rollback()
            raise ConflictError("Einsatz konnte nicht angelegt werden.") from exception
        return self.get_row(assignment.id)

    def update(
        self, assignment_id: uuid.UUID, payload: StaffingAssignmentUpdate, actor: User
    ) -> AssignmentRow:
        assignment: StaffingAssignment = self.get_row(assignment_id).assignment
        if assignment.status not in _EDITABLE:
            raise BusinessRuleError(
                "Beendete oder abgebrochene Einsaetze sind nicht mehr aenderbar."
            )
        values = payload.model_dump(exclude_unset=True)
        if values.get("start_date") is None:
            values.pop("start_date", None)
        if values.get("owner_user_id") is None:
            values.pop("owner_user_id", None)
        elif self.session.get(User, values["owner_user_id"]) is None:
            raise EntityNotFoundError("Disponent nicht gefunden")
        if values.get("contract_id") is not None:
            self._check_contract(values["contract_id"], assignment.client_company_id)
        start: date = values.get("start_date", assignment.start_date)
        end = values.get("planned_end_date", assignment.planned_end_date)
        if end is not None and end < start:
            raise BusinessRuleError("Geplantes Ende liegt vor dem Start.")
        audit.log_updated(
            self.session, audit.ENTITY_ASSIGNMENT, assignment, assignment.id, values, actor.email
        )
        self.assignments.update(assignment, values)
        self.session.commit()
        return self.get_row(assignment.id)

    def update_checklist_item(
        self,
        assignment_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: StaffingChecklistItemUpdate,
        actor: User,
    ) -> StaffingAssignmentDetail:
        assignment = self.get_row(assignment_id).assignment
        if assignment.status not in _EDITABLE:
            raise BusinessRuleError(
                "Beendete oder abgebrochene Einsaetze sind nicht mehr aenderbar."
            )
        item = self.session.get(StaffingChecklistItem, item_id)
        if item is None or item.assignment_id != assignment_id:
            raise EntityNotFoundError("Checklistenpunkt nicht gefunden")
        old_done = item.done
        item.done = payload.done
        item.done_on = (payload.done_on or date.today()) if payload.done else None
        item.document_id = payload.document_id
        if old_done != payload.done:
            audit.log_event(
                self.session,
                audit.ENTITY_ASSIGNMENT,
                assignment_id,
                "checklist_done" if payload.done else "checklist_undone",
                actor.email,
                {"item": item.item_key.value},
            )
        self.session.commit()
        return self.detail(assignment_id)

    def checklist_complete(self, assignment_id: uuid.UUID) -> bool:
        items = self.assignments.checklist(assignment_id)
        return len(items) == len(CHECKLIST_KEYS) and all(item.done for item in items)
