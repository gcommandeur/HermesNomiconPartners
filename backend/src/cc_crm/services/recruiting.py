import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.base import Base
from cc_crm.models.calendar_event import CalendarEvent
from cc_crm.models.candidate import Candidate
from cc_crm.models.candidate_pitch_log import CandidatePitchLog
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import CalendarEventType, SubmissionStatus
from cc_crm.models.recruiting import AuditLog, Fee, Interview, Offer, Placement, SubmissionFeedback
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.repositories.activities import ActivityRepository
from cc_crm.repositories.base import SQLAlchemyRepository
from cc_crm.repositories.calendar_events import CalendarEventRepository
from cc_crm.repositories.candidate_pitch_logs import CandidatePitchLogRepository
from cc_crm.repositories.clients import ClientCompanyRepository
from cc_crm.repositories.recruiting import (
    AuditLogRepository,
    FeedbackRepository,
    FeeRepository,
    InterviewRepository,
    OfferRepository,
    PlacementRepository,
)
from cc_crm.repositories.tasks import TaskRepository
from cc_crm.schemas.recruiting import (
    FeeCreate,
    FeedbackCreate,
    FeedbackRead,
    FeedbackUpdate,
    InterviewCreate,
    InterviewUpdate,
    OfferCreate,
    OfferUpdate,
    PlacementCreate,
    PlacementUpdate,
)
from cc_crm.schemas.submission import (
    CandidatePitchLogCreate,
    CandidateQuickLogCreate,
    CandidateQuickLogResult,
    CandidateStageSummary,
    CandidateSubmissionCreate,
    CandidateSubmissionRead,
    CandidateSubmissionTransition,
)
from cc_crm.services.calendar_events import apply_minimum_duration
from cc_crm.services.submissions import CandidateSubmissionService
from cc_crm.services.warranty import WarrantyService

logger = logging.getLogger(__name__)

MONEY = Decimal("0.01")
# quick_log() deckt die drei fruehen, noch nicht zwingend an eine Kanzlei
# gebundenen Stufen ab - ab Interview braucht der Prozess einen verknuepften
# Kanzlei-Kontakt (siehe services/submissions.py::STATUSES_REQUIRING_CLIENT)
# und hat eigene Panels (InterviewRoundsPanel/OfferPanel/PlacementPanel).
QUICK_LOG_STAGE_ORDER = [
    SubmissionStatus.QUALIFICATION_CALL,
    SubmissionStatus.CV_IN,
    SubmissionStatus.CV_OUT,
]
# Zielwerte, die create_feedback() per target_status selbst in einen
# Statuswechsel uebersetzen darf (siehe FeedbackCreate.target_status) - aus
# denselben Gruenden wie QUICK_LOG_STAGE_ORDER auf die kanzlei-unabhaengigen
# Fruehstufen begrenzt.
FEEDBACK_TARGET_STATUSES = frozenset(QUICK_LOG_STAGE_ORDER)
INTERVIEW_FOLLOW_UP_TITLE = "Interviewfeedback nachfassen"
# Interviews brauchen in der Regel mehr Vorlauf als ein allgemeiner Termin
# (Unterlagen/Notizen des Kandidaten nochmal durchgehen, Fragen vorbereiten)
# - deshalb 60 statt der sonst ueblichen 30 Minuten Standard-Erinnerung
# (siehe models/calendar_event.py::reminder_minutes_before).
INTERVIEW_CALENDAR_REMINDER_MINUTES = 60
ChildT = TypeVar("ChildT", bound=Base)


def stage_reached_counts(
    session: Session,
    submission_ids: "Sequence[uuid.UUID] | Select[Any]",
    *,
    since: datetime | None = None,
) -> dict[SubmissionStatus, set[uuid.UUID]]:
    """Fuer jede SubmissionStatus-Stufe: die Menge der `submission_ids`, die
    laut Audit-Log (action='status_changed', siehe services/submissions.py::
    transition()) MINDESTENS EINMAL dorthin gewechselt sind - die reale
    Statuswechsel-Historie statt SubmissionFeedback-Eintraegen oder
    Interview/Offer/Placement-Kindobjekten (siehe stage_summary() unten fuer
    die ausfuehrliche Begruendung). `since` optional: nur Transitionen AB
    diesem Zeitpunkt zaehlen (fuer period-gescopte Cockpit-Kennzahlen, siehe
    services/operational.py::CockpitService).

    `submission_ids` darf eine Liste von IDs ODER eine SELECT-Abfrage sein, die
    IDs liefert (das Cockpit uebergibt eine Unterabfrage, damit nicht tausende IDs
    als Parameter durch die Leitung gehen).

    Oeffentliche Modulfunktion statt Methode, damit CockpitService dieselbe
    Logik fuer die Pipeline-Kennzahlen wiederverwenden kann, ohne sie zu
    duplizieren."""
    reached: dict[SubmissionStatus, set[uuid.UUID]] = {
        status: set() for status in SubmissionStatus
    }
    if not isinstance(submission_ids, Select) and not submission_ids:
        return reached
    filters = [
        AuditLog.entity_type == "candidate_submission",
        AuditLog.entity_id.in_(submission_ids),
        AuditLog.action == "status_changed",
    ]
    if since is not None:
        filters.append(AuditLog.changed_at >= since)
    for row in session.scalars(select(AuditLog).where(*filters)).all():
        raw_status = (row.new_values or {}).get("status")
        if not isinstance(raw_status, str):
            continue
        try:
            target_status = SubmissionStatus(raw_status)
        except ValueError:
            continue
        reached[target_status].add(row.entity_id)
    return reached


class RecruitingProcessService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.submissions = CandidateSubmissionService(session)
        self.feedback = FeedbackRepository(session)
        self.pitch_logs = CandidatePitchLogRepository(session)
        self.interviews = InterviewRepository(session)
        self.offers = OfferRepository(session)
        self.placements = PlacementRepository(session)
        self.fees = FeeRepository(session)
        self.activities = ActivityRepository(session)
        self.audit = AuditLogRepository(session)
        self.tasks = TaskRepository(session)
        self.clients = ClientCompanyRepository(session)
        self.warranty = WarrantyService(session)
        self.calendar_events = CalendarEventRepository(session)

    def list_scoped[M: (SubmissionFeedback, Interview, Offer, Placement)](
        self,
        model: type[M],
        owner_user_ids: Sequence[uuid.UUID] | None,
        shared_submission_ids: Sequence[uuid.UUID] = (),
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[M]:
        """Alle Eintraege; mit owner_user_ids (Nicht-Admin) nur die zu
        Prozessen dieser Eigentuemer (Sichtbarkeitsgrenze, siehe api/
        dependencies.py::process_owner_scope) PLUS die Prozesse in
        shared_submission_ids (Freigaben, additiv). Ohne Limit: die "Alle"-Listen
        hingen vorher am Standardlimit 100 von repository.list() und schnitten
        still ab."""
        statement = select(model)
        if owner_user_ids is not None:
            statement = statement.join(
                CandidateSubmission, model.submission_id == CandidateSubmission.id
            ).where(
                or_(
                    CandidateSubmission.owner_user_id.in_(owner_user_ids),
                    CandidateSubmission.id.in_(shared_submission_ids),
                )
            )
        statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement).all())

    def list_fees_scoped(
        self,
        owner_user_ids: Sequence[uuid.UUID] | None,
        shared_submission_ids: Sequence[uuid.UUID] = (),
    ) -> list[Fee]:
        statement = select(Fee)
        if owner_user_ids is not None:
            statement = (
                statement.join(Placement, Fee.placement_id == Placement.id)
                .join(CandidateSubmission, Placement.submission_id == CandidateSubmission.id)
                .where(
                    or_(
                        CandidateSubmission.owner_user_id.in_(owner_user_ids),
                        CandidateSubmission.id.in_(shared_submission_ids),
                    )
                )
            )
        return list(self.session.scalars(statement).all())

    def submission_ids_for_owners(
        self,
        owner_user_ids: Sequence[uuid.UUID],
        shared_submission_ids: Sequence[uuid.UUID] = (),
    ) -> set[uuid.UUID]:
        return set(
            self.session.scalars(
                select(CandidateSubmission.id).where(
                    or_(
                        CandidateSubmission.owner_user_id.in_(owner_user_ids),
                        CandidateSubmission.id.in_(shared_submission_ids),
                    )
                )
            ).all()
        )

    def list_feedback(self, submission_id: uuid.UUID) -> list[SubmissionFeedback]:
        self.submissions.get(submission_id)
        return list(self.feedback.list_for_submission(submission_id))

    def create_feedback(
        self,
        submission_id: uuid.UUID,
        payload: FeedbackCreate,
        *,
        changed_by: str | None = None,
    ) -> SubmissionFeedback:
        """Legt eine Notiz an - bringt optional per `target_status` (Bullhorn-
        artiges "Action"-Feld, siehe Frontend feedback-panel.tsx) einen
        Statuswechsel gleich mit: weicht der Zielstatus vom aktuellen
        Submission-Status ab, wird in derselben Transaktion die bestehende,
        validierte Transition-Logik (services/submissions.py::
        ALLOWED_TRANSITIONS, inkl. BusinessRuleError bei ungueltigem
        Uebergang) angewendet. `stage` auf der Notiz selbst wird dabei immer
        auf den gewaehlten Zielstatus gesetzt, nicht auf den alten Status."""
        submission = self.submissions.get(submission_id)
        target_status = payload.target_status
        stage = payload.stage
        try:
            if target_status is not None:
                if target_status not in FEEDBACK_TARGET_STATUSES:
                    raise BusinessRuleError(
                        "target_status muss qualification_call, cv_in oder cv_out sein"
                    )
                stage = target_status
                if target_status != submission.status:
                    submission = self.submissions.transition(
                        submission_id,
                        CandidateSubmissionTransition(
                            status=target_status, changed_by=changed_by
                        ),
                        commit=False,
                    )
            values = payload.model_dump(exclude={"target_status"})
            values["submission_id"] = submission.id
            values["stage"] = stage
            # Urheber kommt vom angemeldeten Nutzer, nicht aus dem Payload -
            # sonst liesse sich ein Kommentar unter fremdem Namen anlegen. Ohne
            # Nutzer (interne Aufrufe) bleibt ein evtl. mitgegebener Wert.
            if changed_by is not None:
                values["created_by"] = changed_by
            feedback = self.feedback.create(values)
            self._event(submission, "feedback_received", "Feedback received", {}, changed_by)
            self.session.commit()
            return feedback
        except Exception:
            self.session.rollback()
            raise

    def _get_feedback(
        self, submission_id: uuid.UUID, feedback_id: uuid.UUID
    ) -> SubmissionFeedback:
        self.submissions.get(submission_id)
        feedback = self.feedback.get(feedback_id)
        if feedback is None or feedback.submission_id != submission_id:
            raise EntityNotFoundError("Feedback not found")
        return feedback

    def update_feedback(
        self,
        submission_id: uuid.UUID,
        feedback_id: uuid.UUID,
        payload: FeedbackUpdate,
    ) -> SubmissionFeedback:
        feedback = self._get_feedback(submission_id, feedback_id)
        values = payload.model_dump(exclude_unset=True)
        updated = self.feedback.update(feedback, values)
        self.session.commit()
        return updated

    def delete_feedback(self, submission_id: uuid.UUID, feedback_id: uuid.UUID) -> None:
        # Kein Kalender-Sync noetig - Feedback (anders als Interview) hat
        # keinen verknuepften CalendarEvent.
        feedback = self._get_feedback(submission_id, feedback_id)
        self.feedback.delete(feedback)
        self.session.commit()

    def quick_log(
        self,
        candidate_id: uuid.UUID,
        payload: CandidateQuickLogCreate,
        *,
        changed_by: str | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> CandidateQuickLogResult:
        """Legt eine Notiz zu einer der drei fruehen Stufen an und startet
        dabei bei Bedarf automatisch einen Prozess - keine separate "Prozess
        erstellen"-Aktion noetig (Nutzer-Feedback: eine Notiz soll automatisch
        einen Prozess starten). Sucht zuerst einen bereits offenen, noch nicht
        mit einer Kanzlei verknuepften Prozess in einer der drei Stufen und
        fuehrt diesen weiter, statt blind einen neuen anzulegen. Liegt die
        Zielstufe hinter dem aktuellen Status, wird jeder Zwischenschritt
        einzeln durchlaufen (gleiches Prinzip wie services/matching.py::
        CandidateMatchingService._transition_path fuer den Bulk-Submit-Flow)."""
        if payload.stage not in QUICK_LOG_STAGE_ORDER:
            raise BusinessRuleError(
                "quick-log unterstuetzt nur die Stufen qualification_call, "
                "cv_in und cv_out"
            )
        self.submissions.candidates.get(candidate_id)

        # owner_user_id: Owner eines neu gestarteten Prozesses (der anlegende
        # Nutzer). Ein offener Prozess eines Kollegen wird bewusst trotzdem
        # weitergefuehrt: pro Kandidat ist nur EIN offener Prozess ohne
        # Kanzlei erlaubt, ein zweiter scheitert mit 409.
        submission = self.submissions.submissions.find_open_unassigned(candidate_id)
        if submission is None:
            submission = self.submissions.create(
                CandidateSubmissionCreate(candidate_id=candidate_id, owner_user_id=owner_user_id)
            )
        current_index = QUICK_LOG_STAGE_ORDER.index(submission.status)
        target_index = QUICK_LOG_STAGE_ORDER.index(payload.stage)
        for status in QUICK_LOG_STAGE_ORDER[current_index + 1 : target_index + 1]:
            submission = self.submissions.transition(
                submission.id,
                CandidateSubmissionTransition(status=status, changed_by=changed_by),
            )

        feedback = self.create_feedback(
            submission.id,
            FeedbackCreate(
                feedback_type=payload.feedback_type,
                feedback_text=payload.feedback_text,
                received_at=payload.received_at,
                next_step=payload.next_step,
                stage=payload.stage,
            ),
            changed_by=changed_by,
        )
        return CandidateQuickLogResult(
            submission=CandidateSubmissionRead.model_validate(submission),
            feedback=FeedbackRead.model_validate(feedback),
        )

    def log_pitch(
        self, candidate_id: uuid.UUID, payload: CandidatePitchLogCreate
    ) -> CandidatePitchLog:
        """Loggt ein Pitch/InMail-Ereignis direkt am Kandidaten - bewusst OHNE
        Prozess-Bezug/Statuswechsel (anders als quick_log() oben), siehe
        CandidatePitchLog-Docstring fuer die Begruendung. Kann beliebig oft
        pro Kandidat aufgerufen werden (Nutzer-Vorgabe: "es kann auch
        mehrmals da sein")."""
        self.submissions.candidates.get(candidate_id)
        pitch_log = self.pitch_logs.create_for_candidate(
            candidate_id,
            occurred_at=payload.occurred_at,
            notes_text=payload.notes_text,
            next_step=payload.next_step,
        )
        self.session.commit()
        return pitch_log

    def stage_summary(self, candidate_id: uuid.UUID) -> CandidateStageSummary:
        """Anzahl Submissions eines Kandidaten (auch ueber mehrere Kanzleien
        hinweg), die eine Stufe TATSAECHLICH ERREICHT haben - Basis der
        Prozess-Timeline auf der Kandidat-Detailseite. Das ist eine reine
        Pipeline-Frage ("wurde dieser Schritt im Kanban je gemacht") und wird
        deshalb durchgehend aus der echten Statuswechsel-Historie (AuditLog,
        siehe services/submissions.py::transition()) abgeleitet - NICHT mehr
        aus SubmissionFeedback (manuelle Notizen mit optionalem, oft nie
        gesetztem stage-Tag; ein reiner Kanban-Drag erzeugt nie einen
        Feedback-Eintrag, der Zaehler blieb dadurch faelschlich bei 0 stehen
        - Nutzer-Feedback "KPIs stimmen nicht", Punkt 3a) und NICHT mehr aus
        den Interview/Offer/Placement-Kindobjekten (die haengen an einer
        SEPARATEN, oft nachtraeglich erst ausgefuellten Formular-Aktion, nicht
        am Statuswechsel selbst - fuer die KAUFMAENNISCHE Sicht bleiben diese
        Objekte weiterhin die massgebliche Quelle, siehe CockpitService,
        NICHT hier).

        qualification_call zaehlt EINFACH ALLE Submissions des Kandidaten:
        das ist die Startstufe, es gibt nie eine eingehende Transition
        dorthin (siehe ALLOWED_TRANSITIONS), jede Submission durchlaeuft sie
        also per Definition genau einmal."""
        self.submissions.candidates.get(candidate_id)
        submission_ids = list(
            self.session.scalars(
                select(CandidateSubmission.id).where(
                    CandidateSubmission.candidate_id == candidate_id
                )
            ).all()
        )
        reached = stage_reached_counts(self.session, submission_ids)
        pitch_count = self.pitch_logs.count_for_candidate(candidate_id)

        return CandidateStageSummary(
            pitch=pitch_count,
            qualification_call=len(submission_ids),
            cv_in=len(reached[SubmissionStatus.CV_IN]),
            cv_out=len(reached[SubmissionStatus.CV_OUT]),
            interview=len(reached[SubmissionStatus.INTERVIEW]),
            offer=len(reached[SubmissionStatus.OFFER]),
            placement=len(reached[SubmissionStatus.PLACEMENT]),
        )

    def list_interviews(self, submission_id: uuid.UUID) -> list[Interview]:
        self.submissions.get(submission_id)
        return list(self.interviews.list_for_submission(submission_id))

    def create_interview(
        self, submission_id: uuid.UUID, payload: InterviewCreate, current_user: User
    ) -> Interview:
        submission = self.submissions.get(submission_id)
        if submission.status != SubmissionStatus.INTERVIEW:
            raise BusinessRuleError("Interview requires the process to be in interview status")
        interview = self._create_child(
            self.interviews,
            submission,
            payload,
            "interview_scheduled",
            "Interview scheduled",
            changed_by=current_user.email,
        )
        self._align_interview_follow_up(submission, payload.scheduled_at)
        # Das Interview ist die primaere, wichtige Aktion und ist an dieser
        # Stelle bereits committet - ein Fehler beim (rein begleitenden)
        # Kalendereintrag darf die Interview-Erstellung nicht nachtraeglich
        # scheitern lassen (Nutzer-Vorgabe), deshalb bewusst breit gefangen
        # und nur geloggt statt weitergereicht.
        try:
            self._create_calendar_event_for_interview(interview, submission, current_user)
        except Exception:
            logger.exception(
                "Automatische Kalender-Erstellung fuer Interview %s fehlgeschlagen", interview.id
            )
            self.session.rollback()
        return interview

    def _get_interview(self, submission_id: uuid.UUID, interview_id: uuid.UUID) -> Interview:
        self.submissions.get(submission_id)
        interview = self.interviews.get(interview_id)
        if interview is None or interview.submission_id != submission_id:
            raise EntityNotFoundError("Interview not found")
        return interview

    def update_interview(
        self,
        submission_id: uuid.UUID,
        interview_id: uuid.UUID,
        payload: InterviewUpdate,
    ) -> Interview:
        interview = self._get_interview(submission_id, interview_id)
        values = payload.model_dump(exclude_unset=True)
        updated = self.interviews.update(interview, values)
        self.session.commit()
        # Kalender-Sync-Fehler duerfen die eigentliche Interview-Aktion nicht
        # verhindern (Nutzer-Vorgabe, gleiches Prinzip wie bei create_interview
        # oben) - das Interview-Update selbst ist an dieser Stelle bereits
        # committet.
        if {"scheduled_at", "location_or_link", "notes"} & values.keys():
            try:
                self._sync_calendar_event_for_interview(updated)
            except Exception:
                logger.exception(
                    "Kalender-Sync fuer Interview %s (Update) fehlgeschlagen", updated.id
                )
                self.session.rollback()
        return updated

    def _sync_calendar_event_for_interview(self, interview: Interview) -> None:
        event = self.calendar_events.for_source_interview(interview.id)
        if event is None:
            return
        self.calendar_events.update(
            event,
            {
                "start_at": interview.scheduled_at,
                "location": interview.location_or_link,
                "notes": interview.notes,
            },
        )
        self.session.commit()

    def delete_interview(self, submission_id: uuid.UUID, interview_id: uuid.UUID) -> None:
        interview = self._get_interview(submission_id, interview_id)
        # Verknuepften Kalendereintrag explizit mitloeschen, statt mich allein
        # auf die DB-seitige ON DELETE CASCADE-FK zu verlassen: SQLite (lokale
        # Entwicklung) erzwingt Foreign-Key-Constraints nur bei aktivierter
        # PRAGMA foreign_keys, die hier nicht gesetzt ist (siehe
        # infrastructure/database/session.py) - auf Postgres (Produktion)
        # greift zusaetzlich die FK-Cascade als zweite Absicherung. Gleicher
        # Fehler-Isolations-Grundsatz wie beim Erstellen/Aktualisieren.
        try:
            linked_event = self.calendar_events.for_source_interview(interview.id)
            if linked_event is not None:
                self.calendar_events.delete(linked_event)
                self.session.commit()
        except Exception:
            logger.exception(
                "Loeschen des verknuepften Kalendereintrags fuer Interview %s fehlgeschlagen",
                interview.id,
            )
            self.session.rollback()
        self.interviews.delete(interview)
        self.session.commit()

    def _create_calendar_event_for_interview(
        self, interview: Interview, submission: CandidateSubmission, current_user: User
    ) -> None:
        candidate = self.session.get(Candidate, submission.candidate_id)
        candidate_name = (
            f"{candidate.first_name} {candidate.last_name}" if candidate else "Unbekannt"
        )
        client_name = None
        if submission.client_company_id is not None:
            client = self.session.get(ClientCompany, submission.client_company_id)
            client_name = client.name if client else None
        title = f"Interview: {candidate_name}" + (f" – {client_name}" if client_name else "")

        calendar_event = CalendarEvent(
            title=title,
            event_type=CalendarEventType.INTERVIEW,
            start_at=interview.scheduled_at,
            end_at=apply_minimum_duration(interview.scheduled_at, None),
            location=interview.location_or_link,
            notes=interview.notes,
            owner_user_id=current_user.id,
            created_by_user_id=current_user.id,
            candidate_id=submission.candidate_id,
            client_company_id=submission.client_company_id,
            candidate_submission_id=submission.id,
            source_interview_id=interview.id,
            reminder_minutes_before=INTERVIEW_CALENDAR_REMINDER_MINUTES,
        )
        self.session.add(calendar_event)
        self.session.commit()

    def _align_interview_follow_up(
        self, submission: CandidateSubmission, scheduled_at: datetime
    ) -> None:
        """Move the interview follow-up to one day after the actual interview.

        The transition to 'interview' status creates a provisional follow-up
        task dated from the status change, but the interview itself is often
        scheduled days later. Once we know the real scheduled_at, the
        follow-up must move to scheduled_at + 1 day instead.
        """
        due_at = scheduled_at + timedelta(days=1)
        self.submissions.submissions.update(submission, {"follow_up_at": due_at})
        open_task = self.tasks.find_open_by_submission_and_title(
            submission.id, INTERVIEW_FOLLOW_UP_TITLE
        )
        if open_task is not None:
            self.tasks.update(open_task, {"due_at": due_at})
        self.session.commit()

    def list_offers(self, submission_id: uuid.UUID) -> list[Offer]:
        self.submissions.get(submission_id)
        return list(self.offers.list_for_submission(submission_id))

    def create_offer(
        self, submission_id: uuid.UUID, payload: OfferCreate, current_user: User | None = None
    ) -> Offer:
        submission = self.submissions.get(submission_id)
        if submission.status != SubmissionStatus.OFFER:
            raise BusinessRuleError("Offer requires the process to be in offer status")
        return self._create_child(
            self.offers,
            submission,
            payload,
            "offer_received",
            "Offer received",
            changed_by=current_user.email if current_user else None,
        )

    def _get_offer(self, submission_id: uuid.UUID, offer_id: uuid.UUID) -> Offer:
        self.submissions.get(submission_id)
        offer = self.offers.get(offer_id)
        if offer is None or offer.submission_id != submission_id:
            raise EntityNotFoundError("Offer not found")
        return offer

    def update_offer(
        self,
        submission_id: uuid.UUID,
        offer_id: uuid.UUID,
        payload: OfferUpdate,
    ) -> Offer:
        offer = self._get_offer(submission_id, offer_id)
        values = payload.model_dump(exclude_unset=True)
        updated = self.offers.update(offer, values)
        self.session.commit()
        return updated

    def delete_offer(self, submission_id: uuid.UUID, offer_id: uuid.UUID) -> None:
        offer = self._get_offer(submission_id, offer_id)
        self.offers.delete(offer)
        self.session.commit()

    def get_placement(self, submission_id: uuid.UUID) -> Placement:
        self.submissions.get(submission_id)
        placement = self.placements.for_submission(submission_id)
        if placement is None:
            raise EntityNotFoundError("Placement not found")
        return placement

    def create_placement(
        self,
        submission_id: uuid.UUID,
        payload: PlacementCreate,
        current_user: User | None = None,
    ) -> Placement:
        submission = self.submissions.get(submission_id)
        if submission.status != SubmissionStatus.PLACEMENT:
            raise BusinessRuleError("Placement requires the process to be in placement status")
        if self.placements.for_submission(submission_id) is not None:
            raise ConflictError("Placement already exists")
        fee_percentage = self._resolve_fee_percentage(submission, payload.fee_percentage)
        calculated_fee = self._calculate_fee(
            final_salary=payload.final_salary,
            fee_percentage=fee_percentage,
            rabatt_percentage=payload.rabatt_percentage,
            fee_fix=payload.fee_fix,
        )
        values = payload.model_dump()
        values.update(
            submission_id=submission_id,
            fee_percentage=fee_percentage,
            calculated_fee=calculated_fee,
        )
        placement = self.placements.create(values)
        self.warranty.schedule_follow_up(placement, submission)
        self._event(
            submission,
            "placement_created",
            "Placement created",
            {"fee_percentage": str(fee_percentage), "calculated_fee": str(calculated_fee)},
            current_user.email if current_user else None,
        )
        self.session.commit()
        return placement

    def update_placement(
        self, submission_id: uuid.UUID, payload: PlacementUpdate
    ) -> Placement:
        # Placement ist singulaer (ein Objekt pro Submission, kein :id im
        # Pfad) - Zugehoerigkeits-Check entfaellt daher, die Submission-ID
        # allein identifiziert es bereits eindeutig.
        placement = self.placements.for_submission(submission_id)
        if placement is None:
            raise EntityNotFoundError("Placement not found")
        values = payload.model_dump(exclude_unset=True)
        # `clear_fee_fix` ist nur ein Steuerflag (siehe PlacementUpdate) und
        # kein Modell-Feld - separat behandeln statt an placements.update()
        # durchzureichen.
        clear_fee_fix = values.pop("clear_fee_fix", False)
        if clear_fee_fix:
            values["fee_fix"] = None
        # calculated_fee neu berechnen, wenn final_salary, fee_percentage,
        # rabatt_percentage oder fee_fix sich aendern - gleiche Formel wie
        # beim Anlegen (create_placement).
        recalc_fields = {"final_salary", "fee_percentage", "rabatt_percentage", "fee_fix"}
        if recalc_fields & values.keys():
            values["calculated_fee"] = self._calculate_fee(
                final_salary=values.get("final_salary", placement.final_salary),
                fee_percentage=values.get("fee_percentage", placement.fee_percentage),
                rabatt_percentage=values.get("rabatt_percentage", placement.rabatt_percentage),
                fee_fix=values.get("fee_fix", placement.fee_fix),
            )
        updated = self.placements.update(placement, values)
        self.session.commit()
        return updated

    def delete_placement(self, submission_id: uuid.UUID) -> None:
        placement = self.placements.for_submission(submission_id)
        if placement is None:
            raise EntityNotFoundError("Placement not found")
        self.placements.delete(placement)
        self.session.commit()

    @staticmethod
    def _calculate_fee(
        *,
        final_salary: Decimal,
        fee_percentage: Decimal,
        rabatt_percentage: Decimal,
        fee_fix: Decimal | None,
    ) -> Decimal:
        """Server-seitige Source of Truth fuer calculated_fee - das Frontend
        zeigt waehrend der Eingabe dieselbe Formel bereits live an, muss
        dieser Berechnung hier aber nicht vertrauen (siehe placement-panel.tsx).

        Ist `fee_fix` gesetzt, wird er unveraendert als Fee uebernommen und
        fee_percentage/rabatt_percentage ignoriert (bleiben aber gespeichert,
        falls spaeter zurueck auf "Berechnet" gewechselt wird). Sonst:
        final_salary * fee_percentage/100 * (1 - rabatt_percentage/100).
        """
        if fee_fix is not None:
            return fee_fix.quantize(MONEY, rounding=ROUND_HALF_UP)
        gross = final_salary * fee_percentage / Decimal("100")
        discounted = gross * (Decimal("1") - rabatt_percentage / Decimal("100"))
        return discounted.quantize(MONEY, rounding=ROUND_HALF_UP)

    def _resolve_fee_percentage(
        self, submission: CandidateSubmission, requested: Decimal | None
    ) -> Decimal:
        """Fee percentage precedence: explicit request > submission-level
        override (e.g. individually negotiated) > the Kanzlei's own default
        (ClientCompany.fee_percentage, 27% unless overridden). This is what
        keeps the 27%-Kanzleihonorar flowing through to Placement without
        every caller having to know and repeat it.
        """
        if requested is not None:
            return requested
        if submission.fee_percentage is not None:
            return submission.fee_percentage
        if submission.client_company_id is not None:
            client = self.clients.get(submission.client_company_id)
            if client is not None:
                return client.fee_percentage
        raise BusinessRuleError(
            "fee_percentage was not provided and no Kanzlei default is available"
        )

    def create_fee(
        self, placement_id: uuid.UUID, payload: FeeCreate, current_user: User | None = None
    ) -> Fee:
        placement = self.placements.get(placement_id)
        if placement is None:
            raise EntityNotFoundError("Placement not found")
        vat_rate = payload.vat_rate
        if vat_rate is None:
            vat_rate = get_settings().default_vat_rate
        amount_gross = (payload.amount_net * (Decimal("1") + vat_rate / Decimal("100"))).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )
        values = payload.model_dump(exclude={"vat_rate"})
        values.update(
            placement_id=placement_id,
            vat_rate=vat_rate,
            amount_gross=amount_gross,
        )
        fee = self.fees.create(values)
        submission = self.submissions.get(placement.submission_id)
        self._event(
            submission,
            "fee_calculated",
            "Fee calculated",
            {"amount_net": str(fee.amount_net), "amount_gross": str(amount_gross)},
            current_user.email if current_user else None,
        )
        self.session.commit()
        return fee

    def _create_child(
        self,
        repository: SQLAlchemyRepository[ChildT],
        submission: CandidateSubmission,
        payload: BaseModel,
        activity_type: str,
        subject: str,
        *,
        commit: bool = True,
        changed_by: str | None = None,
    ) -> ChildT:
        values = payload.model_dump()
        values["submission_id"] = submission.id
        entity = repository.create(values)
        self._event(submission, activity_type, subject, {}, changed_by)
        if commit:
            self.session.commit()
        return entity

    def _event(
        self,
        submission: CandidateSubmission,
        activity_type: str,
        subject: str,
        new_values: dict[str, object],
        changed_by: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        self.activities.create(
            {
                "candidate_id": submission.candidate_id,
                "client_company_id": submission.client_company_id,
                "candidate_submission_id": submission.id,
                "activity_type": activity_type,
                "subject": subject,
                "occurred_at": now,
            }
        )
        self.audit.create(
            {
                "entity_type": "candidate_submission",
                "entity_id": submission.id,
                "action": activity_type,
                "changed_at": now,
                "changed_by": changed_by,
                "new_values": new_values,
            }
        )
