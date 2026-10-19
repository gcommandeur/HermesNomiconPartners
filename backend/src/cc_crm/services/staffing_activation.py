# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Statuswechsel eines Einsatzes. Aktivierung nur mit gültiger Erlaubnis, gültigem
Überlassungsvertrag UND vollständiger Pflicht-Checkliste (klare deutsche Fehlermeldung, alle
Probleme gemeinsam)."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.staffing import (
    CHECKLIST_KEYS,
    StaffingAssignmentStatus,
    StaffingChecklistKey,
    StaffingWorker,
    StaffingWorkerStatus,
)
from cc_crm.models.user import User
from cc_crm.repositories.staffing import AssignmentRow, StaffingLicenseRepository
from cc_crm.schemas.staffing import StaffingAssignmentStatusChange
from cc_crm.services import staffing_audit as audit
from cc_crm.services.staffing_assignments import StaffingAssignmentService
from cc_crm.services.staffing_contract_sync import contract_problem_for, sync_supply_contract_item
from cc_crm.services.staffing_overlap import find_overlaps, overlap_text

CHECKLIST_LABELS: dict[StaffingChecklistKey, str] = {
    StaffingChecklistKey.EMPLOYMENT_CONTRACT: "Arbeitsvertrag / Nachweis (§ 11 AÜG)",
    StaffingChecklistKey.INFO_LEAFLET: "Merkblatt für Leiharbeitnehmer",
    StaffingChecklistKey.SUPPLY_CONTRACT: "Überlassungsvertrag (§ 12 AÜG)",
    StaffingChecklistKey.SPECIFICATION: "Konkretisierung der Person",
    StaffingChecklistKey.SAFETY_BRIEFING: "Sicherheitsunterweisung",
    StaffingChecklistKey.PPE_PROTOCOL: "PSA-Übergabeprotokoll",
}

_ALLOWED: dict[StaffingAssignmentStatus, set[StaffingAssignmentStatus]] = {
    StaffingAssignmentStatus.PLANNED: {
        StaffingAssignmentStatus.ACTIVE,
        StaffingAssignmentStatus.ABORTED,
    },
    StaffingAssignmentStatus.ACTIVE: {
        StaffingAssignmentStatus.ENDED,
        StaffingAssignmentStatus.ABORTED,
    },
    StaffingAssignmentStatus.ENDED: set(),
    StaffingAssignmentStatus.ABORTED: set(),
}

_STATUS_LABELS = {
    StaffingAssignmentStatus.PLANNED: "geplant",
    StaffingAssignmentStatus.ACTIVE: "aktiv",
    StaffingAssignmentStatus.ENDED: "beendet",
    StaffingAssignmentStatus.ABORTED: "abgebrochen",
}


def _fmt(value: date) -> str:
    return value.strftime("%d.%m.%Y")


class StaffingActivationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.assignments = StaffingAssignmentService(session)
        self.licenses = StaffingLicenseRepository(session)

    def activation_problems(self, assignment_id: uuid.UUID, today: date) -> list[str]:
        assignment = self.assignments.get_row(assignment_id).assignment
        problems: list[str] = []
        if assignment.start_date > today:  # Aktiv erst ab Einsatzbeginn, nie in der Zukunft
            problems.append(
                f"Der Einsatz beginnt erst am {_fmt(assignment.start_date)} und kann vorher "
                "nicht aktiviert werden."
            )
        # Zeitraum der Pruefung: Start bis geplantes Ende; ohne Plan bis heute (die tägliche
        # Fristenpruefung meldet eine später ablaufende Erlaubnis).
        period_end = assignment.planned_end_date or max(assignment.start_date, today)
        if self.licenses.covering(assignment.start_date, period_end) is None:
            problems.append(
                "Keine gültige AÜG-Erlaubnis für den Zeitraum "
                f"{_fmt(assignment.start_date)} bis {_fmt(period_end)} hinterlegt."
            )
        # Überlassungsvertrag: Pflicht VOR der Aktivierung und nicht von Hand abhakbar; der
        # Checklistenpunkt ergibt sich aus dieser Prüfung (live, nicht aus dem gespeicherten Haken).
        contract_problem = contract_problem_for(self.session, assignment, today)
        if contract_problem is not None:
            problems.append(contract_problem)
        done = {
            item.item_key
            for item in self.assignments.assignments.checklist(assignment_id)
            if item.done
        }
        missing = [
            CHECKLIST_LABELS[key]
            for key in CHECKLIST_KEYS
            if key not in done and key != StaffingChecklistKey.SUPPLY_CONTRACT
        ]
        if missing:
            problems.append("Pflicht-Checkliste unvollständig (offen: " + ", ".join(missing) + ").")
        return problems

    def activation_warnings(self, assignment_id: uuid.UUID) -> list[str]:
        """Hinweise ohne Sperre: Überschneidung mit einem anderen Einsatz derselben Person."""
        assignment = self.assignments.get_row(assignment_id).assignment
        overlaps = find_overlaps(
            self.session,
            assignment.worker_id,
            assignment.start_date,
            assignment.planned_end_date,
            exclude_id=assignment.id,
        )
        if not overlaps:
            return []
        return [f"{overlap_text(overlaps)} Die Aktivierung ist dadurch nicht gesperrt."]

    def change_status(
        self,
        assignment_id: uuid.UUID,
        payload: StaffingAssignmentStatusChange,
        actor: User,
        today: date | None = None,
    ) -> AssignmentRow:
        day = today or date.today()
        assignment = self.assignments.get_row(assignment_id).assignment
        target = payload.status
        if target not in _ALLOWED[assignment.status]:
            raise BusinessRuleError(
                f"Ein Einsatz mit Status '{_STATUS_LABELS[assignment.status]}' kann nicht auf "
                f"'{_STATUS_LABELS[target]}' gesetzt werden."
            )
        old_status = assignment.status
        if target == StaffingAssignmentStatus.ACTIVE:
            problems = self.activation_problems(assignment_id, day)
            if problems:
                raise BusinessRuleError(
                    "Der Einsatz kann nicht aktiviert werden. " + " ".join(problems)
                )
            # gespeicherten Haken des Checklistenpunkts angleichen
            sync_supply_contract_item(self.session, assignment, day)
            worker = self.session.get(StaffingWorker, assignment.worker_id)
            if worker is not None and worker.status == StaffingWorkerStatus.APPLICANT:
                audit.log_updated(
                    self.session,
                    audit.ENTITY_WORKER,
                    worker,
                    worker.id,
                    {"status": StaffingWorkerStatus.ACTIVE},
                    actor.email,
                )
                worker.status = StaffingWorkerStatus.ACTIVE
        elif old_status == StaffingAssignmentStatus.ACTIVE:
            end = payload.actual_end_date or day
            if end < assignment.start_date:
                raise BusinessRuleError("Das tatsächliche Ende liegt vor dem Start.")
            assignment.actual_end_date = end
        audit.log_event(
            self.session,
            audit.ENTITY_ASSIGNMENT,
            assignment.id,
            "status_changed",
            actor.email,
            {
                "from": old_status.value,
                "to": target.value,
                "actual_end_date": assignment.actual_end_date,
            },
        )
        assignment.status = target
        self.session.commit()
        return self.assignments.get_row(assignment_id)
