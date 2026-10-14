# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Uebernahme durch den Kunden: der Leiharbeitnehmer wird beim Kunden fest angestellt.

Der Einsatz wird beendet, und es entsteht ein Vermittlungsprozess (`CandidateSubmission`) fuer
Kandidat und Kunde mit dem Honorar (Prozentsatz, erwartetes Honorar aus Jahresgehalt). Der Prozess
beginnt bewusst im ersten Status (Quali-Call): die Stufen bis zur Vermittlung durchlaeuft die
Disponentin wie sonst auch - es werden keine Stufen vorgetaeuscht (sie zaehlen in KPIs und
Auswertungen)."""

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import StaffingAssignmentStatus, StaffingWorker
from cc_crm.models.user import User
from cc_crm.schemas.staffing import (
    StaffingAssignmentStatusChange,
    StaffingTakeoverInput,
    StaffingTakeoverResult,
)
from cc_crm.schemas.submission import CandidateSubmissionCreate
from cc_crm.services import staffing_audit as audit
from cc_crm.services.staffing_activation import StaffingActivationService
from cc_crm.services.staffing_assignments import StaffingAssignmentService
from cc_crm.services.staffing_takeover_fee import load_tiers, months_between, tier_percent
from cc_crm.services.submissions import CandidateSubmissionService


class StaffingTakeoverService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def take_over(
        self,
        assignment_id: uuid.UUID,
        payload: StaffingTakeoverInput,
        actor: User,
        today: date | None = None,
    ) -> StaffingTakeoverResult:
        day = payload.takeover_date or today or date.today()
        assignments = StaffingAssignmentService(self.session)
        assignment = assignments.get_row(assignment_id).assignment
        if assignment.status != StaffingAssignmentStatus.ACTIVE:
            raise BusinessRuleError("Nur ein aktiver Einsatz kann vom Kunden uebernommen werden.")
        if day < assignment.start_date:
            raise BusinessRuleError("Das Uebernahmedatum liegt vor dem Einsatzbeginn.")
        worker = self.session.get(StaffingWorker, assignment.worker_id)
        client = self.session.get(ClientCompany, assignment.client_company_id)
        if worker is None or client is None:
            raise EntityNotFoundError("Leiharbeitnehmer oder Kunde nicht gefunden")

        # NOMICON: ohne eigenen Prozentsatz = Honorarsatz des Kunden x Staffel nach Einsatzdauer
        months = months_between(assignment.start_date, day)
        tier = None
        if payload.fee_percentage is not None:
            percentage = payload.fee_percentage
        elif client.fee_percentage is not None:
            tier = tier_percent(months, load_tiers(self.session))
            percentage = (client.fee_percentage * tier / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            percentage = None
        expected_fee = None
        if payload.annual_salary is not None and percentage is not None:
            expected_fee = (payload.annual_salary * percentage / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        # Zuerst den Prozess anlegen (kann an einem doppelten aktiven Prozess scheitern), dann
        # beenden - so bleibt bei einem Fehler der Einsatz unveraendert.
        submission = CandidateSubmissionService(self.session).create(
            CandidateSubmissionCreate(
                candidate_id=worker.candidate_id,
                client_company_id=client.id,
                owner_user_id=assignment.owner_user_id or actor.id,
                summary=(
                    f"Uebernahme durch den Kunden aus der Arbeitnehmerueberlassung "
                    f"(Einsatz seit {assignment.start_date:%d.%m.%Y}, Uebernahme {day:%d.%m.%Y})."
                ),
                salary_at_submission=(
                    None
                    if payload.annual_salary is None
                    else f"{payload.annual_salary:.2f} EUR/Jahr"
                ),
                fee_percentage=percentage,
                expected_fee=expected_fee,
                next_step="Vermittlungshonorar klaeren und Vermittlung abschliessen",
            ),
            created_by_user_id=actor.id,
        )
        StaffingActivationService(self.session).change_status(
            assignment_id,
            StaffingAssignmentStatusChange(
                status=StaffingAssignmentStatus.ENDED, actual_end_date=day
            ),
            actor,
            today=day,
        )
        audit.log_event(
            self.session,
            audit.ENTITY_ASSIGNMENT,
            assignment_id,
            "taken_over",
            actor.email,
            {"submission_id": submission.id, "takeover_date": day},
        )
        self.session.commit()
        return StaffingTakeoverResult(
            assignment=assignments.detail(assignment_id, day),
            submission_id=submission.id,
            months_worked=months,
            tier_percent=tier,
            applied_fee_percentage=percentage,
        )
