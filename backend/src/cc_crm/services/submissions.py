import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
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
    UnownedSubmissionList,
    UnownedSubmissionRead,
)
from cc_crm.services.audit_diff import changed_values
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

# Exakte description, mit der jeder automatisch erzeugte Follow-up-Task
# unten angelegt wird - dient als eindeutiges Erkennungsmerkmal, um bei
# einem weiteren Statuswechsel NUR diese automatischen Tasks zu schliessen,
# nicht manuell vom Nutzer angelegte Aufgaben mit zufaellig demselben Titel
# (z.B. "CV-Out nachfassen" von Hand nochmal angelegt).
AUTO_FOLLOW_UP_DESCRIPTION = "Automatisch aus dem Prozessstatus erzeugtes Follow-up"

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

    def archive(
        self, entity_id: uuid.UUID, current_user: User | None = None
    ) -> CandidateSubmission:
        """Expliziter Abschluss NACH einem Placement (Nutzer-Vorgabe "Prozesse
        abschliessen") - blendet den Prozess aus dem Kanban aus, OHNE Status
        oder Historie anzufassen (siehe models/submission.py::archived_at).
        Bewusst NUR ab status==PLACEMENT erlaubt: das ist ein Erfolgs-
        Abschluss, kein allgemeiner "aus dem Kanban werfen"-Mechanismus -
        fuer andere Ausgaenge existiert bereits CANCELLED."""
        submission = self.get(entity_id)
        if submission.status != SubmissionStatus.PLACEMENT:
            raise BusinessRuleError(
                "Nur Prozesse im Status 'placement' koennen abgeschlossen werden."
            )
        if submission.archived_at is not None:
            return submission
        now = datetime.now(UTC)
        submission.archived_at = now
        self.audit_logs.create(
            {
                "entity_type": "candidate_submission",
                "entity_id": submission.id,
                "action": "archived",
                "changed_by": current_user.email if current_user else None,
                "old_values": {"archived_at": None},
                "new_values": {"archived_at": now.isoformat()},
            }
        )
        self.session.commit()
        self.session.refresh(submission)
        return submission

    def unarchive(
        self, entity_id: uuid.UUID, current_user: User | None = None
    ) -> CandidateSubmission:
        """Macht archive() rueckgaengig - fuer den Fall, dass ein Prozess
        versehentlich abgeschlossen wurde oder doch noch im Blick bleiben
        soll (z.B. Rechnungsklaerung)."""
        submission = self.get(entity_id)
        if submission.archived_at is None:
            return submission
        self.audit_logs.create(
            {
                "entity_type": "candidate_submission",
                "entity_id": submission.id,
                "action": "unarchived",
                "changed_by": current_user.email if current_user else None,
                "old_values": {"archived_at": submission.archived_at.isoformat()},
                "new_values": {"archived_at": None},
            }
        )
        submission.archived_at = None
        self.session.commit()
        self.session.refresh(submission)
        return submission

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
        # Ein Prozess ohne Verantwortlichen ist fuer Nicht-Admins unsichtbar und verschwindet
        # aus Listen, Kennzahlen und Abrechnung - deshalb keine Neuanlage ohne Owner (nur
        # anwendungsseitig, kein DB-NOT-NULL, weil Altdaten ohne Owner existieren). Die
        # API-Routen setzen den anlegenden Nutzer, wenn nichts angegeben ist.
        if payload.owner_user_id is None:
            raise BusinessRuleError("Ein Prozess braucht einen Verantwortlichen (owner_user_id).")
        if payload.status != SubmissionStatus.QUALIFICATION_CALL:
            raise BusinessRuleError("New submissions must start in qualification_call status")
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

    def list_without_owner(self, limit: int = 200) -> UnownedSubmissionList:
        """Alle Prozesse ohne `owner_user_id` (Admin-Sicht), neueste zuerst, mit Namen."""
        base = select(CandidateSubmission).where(CandidateSubmission.owner_user_id.is_(None))
        total = int(
            self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        )
        rows = self.session.execute(
            select(CandidateSubmission, Candidate, ClientCompany)
            .join(Candidate, Candidate.id == CandidateSubmission.candidate_id)
            .outerjoin(ClientCompany, ClientCompany.id == CandidateSubmission.client_company_id)
            .where(CandidateSubmission.owner_user_id.is_(None))
            .order_by(CandidateSubmission.created_at.desc())
            .limit(limit)
        ).all()
        return UnownedSubmissionList(
            total=total,
            items=[
                UnownedSubmissionRead(
                    id=submission.id,
                    candidate_id=submission.candidate_id,
                    candidate_name=f"{candidate.first_name} {candidate.last_name}".strip(),
                    client_company_id=submission.client_company_id,
                    client_name=company.name if company is not None else None,
                    status=submission.status,
                    created_at=submission.created_at,
                )
                for submission, candidate, company in rows
            ],
        )

    def assign_owner(
        self, entity_id: uuid.UUID, owner_user_id: uuid.UUID, admin: User
    ) -> CandidateSubmission:
        """Admin weist einen aktiven Nutzer als Verantwortlichen zu (Audit `updated`, alt/neu)."""
        submission = self.get(entity_id)
        owner = self.session.get(User, owner_user_id)
        if owner is None or not owner.is_active:
            raise EntityNotFoundError("Nutzer nicht gefunden oder deaktiviert")
        values = {"owner_user_id": owner_user_id}
        old_values, new_values = changed_values(submission, values)
        updated = self.submissions.update(submission, values)
        if new_values:
            self.audit_logs.create(
                {
                    "entity_type": "candidate_submission",
                    "entity_id": updated.id,
                    "action": "updated",
                    "changed_by": admin.email,
                    "old_values": old_values,
                    "new_values": new_values,
                }
            )
        self.session.commit()
        return updated

    def update(
        self,
        entity_id: uuid.UUID,
        payload: CandidateSubmissionUpdate,
        current_user: User | None = None,
    ) -> CandidateSubmission:
        submission = self.get(entity_id)
        values = payload.model_dump(exclude_unset=True)
        old_values, new_values = changed_values(submission, values)
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
            if new_values:
                self.audit_logs.create(
                    {
                        "entity_type": "candidate_submission",
                        "entity_id": updated.id,
                        "action": "updated",
                        "changed_by": current_user.email if current_user else None,
                        "old_values": old_values,
                        "new_values": new_values,
                    }
                )
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
        # SELECT ... FOR UPDATE (Punkt 1 des Auftrags "3 Mittel-Punkte
        # umsetzen"): ohne Row-Lock konnten zwei gleichzeitige Requests auf
        # denselben Prozess beide gegen denselben (veralteten) Status
        # pruefen und beide durchschreiben (z.B. doppelte Placement/Fee-
        # Eintraege). Eine zweite, gleichzeitige transition() wartet jetzt
        # hier, bis die erste committet hat, und sieht dann den bereits
        # aktualisierten Status. Auf Postgres (Produktion) sperrt das den
        # Datensatz echt; auf SQLite (lokale Tests) ist die Klausel
        # wirkungslos - deshalb zusaetzlich die bedingte UPDATE-Klausel
        # unten (WHERE status = old_status), die auch ohne echten Row-Lock
        # zuverlaessig einen sauberen ConflictError statt eines stillen
        # doppelten Schreibens liefert.
        submission = self.submissions.get_for_update(entity_id)
        if submission is None:
            raise EntityNotFoundError(f"{self.entity_name} not found")
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
            # Bedingtes UPDATE (WHERE status = old_status) statt eines
            # blinden setattr()+flush() - schuetzt zusaetzlich zu SELECT
            # ... FOR UPDATE oben davor, dass eine zweite, gleichzeitige
            # transition() (auf einer DB ohne wirksames Row-Lock, siehe
            # get_for_update()) den Status stillschweigend ueberschreibt:
            # rowcount == 0 bedeutet, jemand anderes hat den Status bereits
            # veraendert, seit wir ihn gelesen haben - dann klarer
            # Konflikt-Fehler statt eines doppelten Schreibens.
            result = cast(
                "CursorResult[Any]",
                self.session.execute(
                    update(CandidateSubmission)
                    .where(
                        CandidateSubmission.id == submission.id,
                        CandidateSubmission.status == old_status,
                    )
                    .values(**values)
                ),
            )
            if result.rowcount == 0:
                raise ConflictError(
                    "Der Prozess wurde inzwischen von einer anderen Anfrage aktualisiert - "
                    "bitte neu laden und erneut versuchen."
                )
            self.session.flush()
            self.session.refresh(submission)
            updated = submission
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
            # Vorherige automatische Follow-ups fuer denselben Prozess schliessen,
            # bevor ein neuer angelegt wird - sonst blieb z.B. "CV-Out
            # nachfassen" sichtbar offen, obwohl der Prozess laengst bei
            # "Interview" war (kein Task wurde je geschlossen, siehe
            # Nutzer-Feedback). Nur Tasks mit der exakten automatischen
            # description werden geschlossen, keine manuell angelegten.
            stale_auto_follow_ups = self.tasks.find_open_auto_follow_ups(
                updated.id, AUTO_FOLLOW_UP_DESCRIPTION
            )
            for stale_task in stale_auto_follow_ups:
                self.tasks.update(stale_task, {"status": TaskStatus.DONE})
            if follow_up is not None:
                self.tasks.create(
                    {
                        "candidate_id": updated.candidate_id,
                        "client_company_id": updated.client_company_id,
                        "candidate_submission_id": updated.id,
                        "title": follow_up[1],
                        "description": AUTO_FOLLOW_UP_DESCRIPTION,
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
