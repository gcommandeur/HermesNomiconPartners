import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, ConflictError
from cc_crm.models.enums import SubmissionStatus, TaskPriority, TaskStatus
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.repositories.activities import ActivityRepository
from cc_crm.repositories.contacts import ContactPersonRepository
from cc_crm.repositories.jobs import JobMandateRepository
from cc_crm.repositories.recruiting import AuditLogRepository
from cc_crm.repositories.submissions import CandidateSubmissionRepository
from cc_crm.repositories.tasks import TaskRepository
from cc_crm.schemas.submission import (
    CandidateSubmissionCreate,
    CandidateSubmissionTransition,
    CandidateSubmissionUpdate,
    ClosingScoreInput,
)
from cc_crm.services.base import CrudService
from cc_crm.services.candidates import CandidateService
from cc_crm.services.clients import ClientCompanyService
from cc_crm.services.closing_score import ClosingScoreService

CLOSED_STATUSES = {
    SubmissionStatus.PLACEMENT,
    SubmissionStatus.CANCELLED,
}

# Every non-terminal status may additionally transition to CANCELLED (with a
# mandatory cancellation_reason, enforced in transition()).
ALLOWED_TRANSITIONS = {
    SubmissionStatus.PITCH: {
        SubmissionStatus.QUALIFICATION_CALL,
        SubmissionStatus.CANCELLED,
    },
    SubmissionStatus.QUALIFICATION_CALL: {
        SubmissionStatus.CV_IN,
        SubmissionStatus.CANCELLED,
    },
    SubmissionStatus.CV_IN: {
        SubmissionStatus.CV_OUT,
        SubmissionStatus.CANCELLED,
    },
    SubmissionStatus.CV_OUT: {
        SubmissionStatus.INTERVIEW,
        SubmissionStatus.CANCELLED,
    },
    SubmissionStatus.INTERVIEW: {
        SubmissionStatus.OFFER,
        SubmissionStatus.CANCELLED,
    },
    SubmissionStatus.OFFER: {
        SubmissionStatus.PLACEMENT,
        SubmissionStatus.CANCELLED,
    },
}

# From INTERVIEW onward, the process must be linked to a Kanzlei.
STATUSES_REQUIRING_CLIENT = {
    SubmissionStatus.INTERVIEW,
    SubmissionStatus.OFFER,
    SubmissionStatus.PLACEMENT,
}

FOLLOW_UP_RULES = {
    SubmissionStatus.CV_OUT: (timedelta(days=3), "CV-Out nachfassen"),
    SubmissionStatus.INTERVIEW: (timedelta(days=1), "Interviewfeedback nachfassen"),
    SubmissionStatus.OFFER: (timedelta(days=1), "Offer nachfassen"),
    SubmissionStatus.PLACEMENT: (timedelta(days=1), "Placement und Rechnung nachverfolgen"),
}

# Zusaetzliches, von FOLLOW_UP_RULES unabhaengiges Referral-Follow-up: bei
# jedem Placement soll der Recruiter aktiv nach einer Empfehlung fragen.
REFERRAL_FOLLOW_UP = (timedelta(days=7), "Nach Empfehlung fragen")


class CandidateSubmissionService(
    CrudService[
        CandidateSubmission,
        CandidateSubmissionCreate,
        CandidateSubmissionUpdate,
    ]
):
    def __init__(self, session: Session) -> None:
        repository = CandidateSubmissionRepository(session)
        super().__init__(session, repository, "CandidateSubmission")
        self.submissions = repository
        self.activities = ActivityRepository(session)
        self.audit_logs = AuditLogRepository(session)
        self.candidates = CandidateService(session)
        self.clients = ClientCompanyService(session)
        self.jobs = JobMandateRepository(session)
        self.contacts = ContactPersonRepository(session)
        self.tasks = TaskRepository(session)

    def delete(self, entity_id: uuid.UUID, current_user: User | None = None) -> None:
        # Loeschung ist sicherheits-/nachvollziehbarkeitsrelevant (Punkt 2 des
        # Auftrags) - siehe services/candidates.py::delete fuer dasselbe Muster.
        # Getrennt vom bereits bestehenden "status_changed"-Audit-Log in
        # transition() oben, das eine andere Aktion protokolliert.
        submission = self.get(entity_id)
        self.audit_logs.create(
            {
                "entity_type": "candidate_submission",
                "entity_id": submission.id,
                "action": "deleted",
                "changed_by": current_user.email if current_user else None,
                "old_values": {
                    "candidate_id": str(submission.candidate_id),
                    "status": submission.status.value,
                },
            }
        )
        self.session.commit()
        super().delete(entity_id)

    def list_for_candidate(
        self,
        candidate_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[CandidateSubmission]:
        self.candidates.get(candidate_id)
        return self.submissions.list_for_candidate(
            candidate_id,
            offset=offset,
            limit=limit,
        )

    def create(self, payload: CandidateSubmissionCreate) -> CandidateSubmission:
        if payload.status != SubmissionStatus.PITCH:
            raise BusinessRuleError("New submissions must start in pitch status")
        self.candidates.get(payload.candidate_id)
        if payload.client_company_id is not None:
            self.clients.get(payload.client_company_id)
        self._validate_related_entities(
            client_company_id=payload.client_company_id,
            job_mandate_id=payload.job_mandate_id,
            contact_person_id=payload.contact_person_id,
        )
        duplicate = self.submissions.find_active_duplicate(
            candidate_id=payload.candidate_id,
            client_company_id=payload.client_company_id,
            job_mandate_id=payload.job_mandate_id,
        )
        if duplicate is not None:
            raise ConflictError("An active submission already exists for this target")

        values = payload.model_dump(exclude_none=True)
        now = datetime.now(UTC)
        values["last_activity_at"] = now

        try:
            submission = self.submissions.create(values)
            self.activities.create(
                {
                    "candidate_id": submission.candidate_id,
                    "client_company_id": submission.client_company_id,
                    "candidate_submission_id": submission.id,
                    "activity_type": "submission_created",
                    "subject": "Candidate submission created",
                    "details": f"Initial status: {submission.status.value}",
                    "occurred_at": now,
                }
            )
            self.session.commit()
            return submission
        except Exception:
            self.session.rollback()
            raise

    def update(
        self,
        entity_id: uuid.UUID,
        payload: CandidateSubmissionUpdate,
    ) -> CandidateSubmission:
        submission = self.get(entity_id)
        values = payload.model_dump(exclude_unset=True)
        client_company_id = values.get("client_company_id", submission.client_company_id)
        if "client_company_id" in values and client_company_id is not None:
            self.clients.get(client_company_id)
        self._validate_related_entities(
            client_company_id=client_company_id,
            job_mandate_id=values.get("job_mandate_id", submission.job_mandate_id),
            contact_person_id=values.get("contact_person_id", submission.contact_person_id),
        )
        now = datetime.now(UTC)
        values["last_activity_at"] = now
        try:
            updated = self.submissions.update(submission, values)
            self.session.commit()
            return updated
        except Exception:
            self.session.rollback()
            raise

    def transition(
        self,
        entity_id: uuid.UUID,
        payload: CandidateSubmissionTransition,
        *,
        commit: bool = True,
    ) -> CandidateSubmission:
        submission = self.get(entity_id)
        old_status = submission.status
        if payload.status not in ALLOWED_TRANSITIONS.get(old_status, set()):
            raise BusinessRuleError(
                f"Transition {old_status.value} -> {payload.status.value} is not allowed"
            )

        if payload.status == SubmissionStatus.CANCELLED and payload.cancellation_reason is None:
            raise BusinessRuleError(
                "Cancelling a process requires cancellation_reason "
                "(candidate_rejected, client_rejected or candidate_ghosting)"
            )

        client_company_id = submission.client_company_id
        if payload.client_company_id is not None:
            self.clients.get(payload.client_company_id)
            client_company_id = payload.client_company_id
        if payload.status in STATUSES_REQUIRING_CLIENT and client_company_id is None:
            raise BusinessRuleError(
                "Ab Interview muss der Prozess mit einer Kanzlei verknuepft sein"
            )

        now = datetime.now(UTC)
        values: dict[str, object] = {
            "status": payload.status,
            "client_company_id": client_company_id,
            "last_activity_at": now,
            "closed_at": now if payload.status in CLOSED_STATUSES else None,
            "cancellation_reason": (
                payload.cancellation_reason
                if payload.status == SubmissionStatus.CANCELLED
                else None
            ),
        }
        follow_up = FOLLOW_UP_RULES.get(payload.status)
        if follow_up is not None:
            delay, title = follow_up
            due_at = now + delay
            values["follow_up_at"] = due_at
            values["next_step"] = title
        if payload.status == SubmissionStatus.CV_OUT and submission.submitted_at is None:
            # CV_OUT is only ever reached via CV_IN (see ALLOWED_TRANSITIONS), so
            # gating this on old_status == QUALIFICATION_CALL never fired and
            # submitted_at was never recorded. Set it the first (and only)
            # time a submission reaches CV_OUT instead.
            values["submitted_at"] = now
        try:
            updated = self.submissions.update(submission, values)
            details = f"{old_status.value} -> {payload.status.value}"
            if payload.cancellation_reason:
                details = f"{details}: {payload.cancellation_reason.value}"
            if payload.reason:
                details = f"{details}: {payload.reason}"
            self.activities.create(
                {
                    "candidate_id": updated.candidate_id,
                    "client_company_id": updated.client_company_id,
                    "candidate_submission_id": updated.id,
                    "activity_type": "submission_status_changed",
                    "subject": "Candidate submission status changed",
                    "details": details,
                    "occurred_at": now,
                }
            )
            self.audit_logs.create(
                {
                    "entity_type": "candidate_submission",
                    "entity_id": updated.id,
                    "action": "status_changed",
                    "changed_at": now,
                    "changed_by": payload.changed_by,
                    "old_values": {"status": old_status.value},
                    "new_values": {"status": payload.status.value},
                }
            )
            if follow_up is not None:
                self.tasks.create(
                    {
                        "candidate_id": updated.candidate_id,
                        "client_company_id": updated.client_company_id,
                        "candidate_submission_id": updated.id,
                        "title": follow_up[1],
                        "description": "Automatisch aus dem Prozessstatus erzeugtes Follow-up",
                        "due_at": values["follow_up_at"],
                        "status": TaskStatus.OPEN,
                        "priority": TaskPriority.HIGH,
                    }
                )
            if payload.status == SubmissionStatus.PLACEMENT:
                referral_delay, referral_title = REFERRAL_FOLLOW_UP
                self.tasks.create(
                    {
                        "candidate_id": updated.candidate_id,
                        "client_company_id": updated.client_company_id,
                        "candidate_submission_id": updated.id,
                        "title": referral_title,
                        "description": (
                            "Automatisch bei Placement erzeugtes Follow-up: nach einer "
                            "Empfehlung (referred_by) fragen"
                        ),
                        "due_at": now + referral_delay,
                        "status": TaskStatus.OPEN,
                        "priority": TaskPriority.NORMAL,
                    }
                )
            if commit:
                self.session.commit()
            return updated
        except Exception:
            self.session.rollback()
            raise

    def update_closing_score(
        self,
        entity_id: uuid.UUID,
        payload: ClosingScoreInput,
    ) -> CandidateSubmission:
        submission = self.get(entity_id)
        candidate = self.candidates.get(submission.candidate_id)
        probability, closing_status = ClosingScoreService(self.session).calculate(
            pain_staerke=payload.pain_staerke,
            entscheidungsklarheit=payload.entscheidungsklarheit,
            markt_fit=payload.markt_fit,
            momentum=payload.momentum,
            postal_code=candidate.postal_code,
        )
        values = {
            "pain_staerke": payload.pain_staerke,
            "entscheidungsklarheit": payload.entscheidungsklarheit,
            "markt_fit": payload.markt_fit,
            "momentum": payload.momentum,
            "closing_probability": probability,
            "closing_status": closing_status,
        }
        try:
            updated = self.submissions.update(submission, values)
            self.session.commit()
            return updated
        except Exception:
            self.session.rollback()
            raise

    def _validate_related_entities(
        self,
        *,
        client_company_id: uuid.UUID | None,
        job_mandate_id: uuid.UUID | None,
        contact_person_id: uuid.UUID | None,
    ) -> None:
        if job_mandate_id is not None:
            job = self.jobs.get(job_mandate_id)
            if job is None:
                raise BusinessRuleError("JobMandate not found")
            if client_company_id is not None and job.client_company_id != client_company_id:
                raise BusinessRuleError("JobMandate belongs to another client")
        if contact_person_id is not None:
            contact = self.contacts.get(contact_person_id)
            if contact is None:
                raise BusinessRuleError("ContactPerson not found")
            if client_company_id is not None and contact.client_company_id != client_company_id:
                raise BusinessRuleError("ContactPerson belongs to another client")
