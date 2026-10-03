"""Mehrkanal-Outreach-Sequenzen: Verwaltung, Einschreibung und Tageslauf.

Drei Teile: `SequenceService` (Sequenzen anlegen/aendern), `EnrollmentService`
(einschreiben/stoppen/anzeigen) und `run_due_steps` (der Tageslauf fuer
scripts/run_outreach_sequences.py). Der Mailversand ist wie bei
services/due_reminders.py injizierbar (`sender`), damit der Lauf ohne Mailserver
testbar ist.

Regeln des Tageslaufs, pro Einschreibung:
1. Antwort-Stopp VOR jedem Schritt: gibt es seit `started_at` eine eingehende
   Aktivitaet des Kandidaten (E-Mail/LinkedIn, siehe services/mail_sync.py), wird
   die Einschreibung auf `paused_reply` gesetzt und nichts ausgefuehrt.
2. Faellig ist der naechste Schritt, wenn heute (Europe/Berlin) mindestens
   `Starttag + day_offset` erreicht ist UND heute noch kein Schritt dieser
   Einschreibung lief (`last_step_at`) - hoechstens ein Schritt pro Tag, damit
   ein zweiter Lauf am selben Tag nichts doppelt ausfuehrt.
3. Kanal `email`: Versand ueber send_mail (Absender wie beim manuellen Versand:
   persoenliches Postfach des Owners, sonst globales Standardpostfach). Alle
   anderen Kanaele legen einen Task fuer den Owner an - keine Automatisierung.
4. Nicht ausfuehrbare Schritte (Kandidat ohne E-Mail-Adresse oder ohne erfasste
   Einwilligung): Einschreibung wird `stopped` und der Owner bekommt einen Task.
   Voruebergehende Probleme (kein Sendekonto, Tageslimit, Transportfehler)
   lassen sie `active`; der naechste Lauf versucht es erneut.
Ein Fehler bei EINER Einschreibung stoppt die anderen nicht.

Bekannte Grenze: Versand und Fortschritt (`current_step_index`) lassen sich nicht
atomar speichern - bricht der Prozess genau zwischen erfolgreichem Versand und
Commit ab, wuerde der Schritt beim naechsten Lauf noch einmal versendet.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cc_crm.core.errors import (
    BusinessRuleError,
    ConflictError,
    ConsentNotGrantedError,
    EntityNotFoundError,
    PermissionDeniedError,
)
from cc_crm.core.time import naive_utc
from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import TaskPriority, TaskStatus
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.outreach import OutreachSequence, OutreachSequenceStep, SequenceEnrollment
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.schemas.outreach import (
    EnrollmentRead,
    SequenceCreate,
    SequenceRead,
    SequenceStepInput,
    SequenceStepRead,
    SequenceUpdate,
)
from cc_crm.services.mail_accounts import MailAccountService
from cc_crm.services.mail_send import DailyLimitReachedError, send_mail
from cc_crm.services.mail_sync import ACTIVITY_TYPE_EMAIL, ACTIVITY_TYPE_LINKEDIN

logger = logging.getLogger("cc_crm.outreach_sequences")

_BERLIN = ZoneInfo("Europe/Berlin")
# Eingehende Aktivitaeten, die als Antwort gelten. Ausgehende Mails legen keine
# Kandidaten-Aktivitaet an (der Mail-Sync ordnet nach Absenderadresse = Kandidat zu).
REPLY_ACTIVITY_TYPES = (ACTIVITY_TYPE_EMAIL, ACTIVITY_TYPE_LINKEDIN)
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

Sender = Callable[..., MailMessage]


def _berlin_day(value: datetime) -> date:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(_BERLIN).date()


def render_template(text: str, candidate: Candidate, owner: User | None) -> str:
    values = {
        "first_name": candidate.first_name,
        "last_name": candidate.last_name,
        "full_name": f"{candidate.first_name} {candidate.last_name}",
        "sender_name": (owner.display_name or owner.email) if owner is not None else "",
    }
    return _PLACEHOLDER_RE.sub(lambda match: values.get(match.group(1), match.group(0)), text)


class SequenceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _steps(self, sequence_id: uuid.UUID) -> list[OutreachSequenceStep]:
        return list(
            self.session.scalars(
                select(OutreachSequenceStep)
                .where(OutreachSequenceStep.sequence_id == sequence_id)
                .order_by(OutreachSequenceStep.step_index)
            ).all()
        )

    def to_read(self, sequence: OutreachSequence) -> SequenceRead:
        return SequenceRead(
            id=sequence.id,
            name=sequence.name,
            is_active=sequence.is_active,
            created_at=sequence.created_at,
            steps=[
                SequenceStepRead(
                    step_index=step.step_index,
                    day_offset=step.day_offset,
                    channel=step.channel,
                    subject=step.subject,
                    body_template=step.body_template,
                )
                for step in self._steps(sequence.id)
            ],
        )

    def get(self, sequence_id: uuid.UUID) -> OutreachSequence:
        sequence = self.session.get(OutreachSequence, sequence_id)
        if sequence is None:
            raise EntityNotFoundError("Sequenz nicht gefunden")
        return sequence

    def list(self, *, only_active: bool) -> list[OutreachSequence]:
        statement = select(OutreachSequence).order_by(OutreachSequence.name)
        if only_active:
            statement = statement.where(OutreachSequence.is_active.is_(True))
        return list(self.session.scalars(statement).all())

    def _replace_steps(self, sequence_id: uuid.UUID, steps: Sequence[SequenceStepInput]) -> None:
        for existing in self._steps(sequence_id):
            self.session.delete(existing)
        self.session.flush()
        for index, step in enumerate(steps):
            self.session.add(
                OutreachSequenceStep(
                    sequence_id=sequence_id,
                    step_index=index,
                    day_offset=step.day_offset,
                    channel=step.channel,
                    subject=step.subject,
                    body_template=step.body_template,
                )
            )

    def create(self, payload: SequenceCreate) -> OutreachSequence:
        sequence = OutreachSequence(name=payload.name, is_active=payload.is_active)
        self.session.add(sequence)
        self.session.flush()
        self._replace_steps(sequence.id, payload.steps)
        self.session.commit()
        return sequence

    def update(self, sequence_id: uuid.UUID, payload: SequenceUpdate) -> OutreachSequence:
        sequence = self.get(sequence_id)
        if payload.name is not None:
            sequence.name = payload.name
        if payload.is_active is not None:
            sequence.is_active = payload.is_active
        if payload.steps is not None:
            self._replace_steps(sequence.id, payload.steps)
        self.session.commit()
        return sequence


class EnrollmentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sequences = SequenceService(session)

    def enroll(
        self, sequence_id: uuid.UUID, candidate_id: uuid.UUID, current_user: User
    ) -> SequenceEnrollment:
        sequence = self.sequences.get(sequence_id)
        if not sequence.is_active:
            raise BusinessRuleError("Diese Sequenz ist deaktiviert.")
        candidate = self.session.get(Candidate, candidate_id)
        if candidate is None:
            raise EntityNotFoundError("Kandidat nicht gefunden")
        if any(step.channel == "email" for step in self.sequences._steps(sequence.id)):
            if not (candidate.email or "").strip():
                raise BusinessRuleError(
                    "Der Kandidat hat keine E-Mail-Adresse - die Sequenz hat E-Mail-Schritte."
                )
            if not candidate.consent_received:
                raise BusinessRuleError(
                    "Fuer den Kandidaten ist keine Einwilligung erfasst - "
                    "E-Mail-Schritte wuerden abgelehnt."
                )
        running = self.session.scalar(
            select(SequenceEnrollment.id).where(
                SequenceEnrollment.sequence_id == sequence_id,
                SequenceEnrollment.candidate_id == candidate_id,
                SequenceEnrollment.status == "active",
            )
        )
        if running is not None:
            raise ConflictError("Der Kandidat ist in dieser Sequenz bereits eingeschrieben.")
        enrollment = SequenceEnrollment(
            sequence_id=sequence_id,
            candidate_id=candidate_id,
            owner_user_id=current_user.id,
            started_at=datetime.now(UTC),
            status="active",
        )
        self.session.add(enrollment)
        try:
            self.session.commit()
        except IntegrityError as exc:  # paralleler Doppelklick: partieller Unique-Index greift
            self.session.rollback()
            raise ConflictError(
                "Der Kandidat ist in dieser Sequenz bereits eingeschrieben."
            ) from exc
        return enrollment

    def get(self, enrollment_id: uuid.UUID) -> SequenceEnrollment:
        enrollment = self.session.get(SequenceEnrollment, enrollment_id)
        if enrollment is None:
            raise EntityNotFoundError("Einschreibung nicht gefunden")
        return enrollment

    def stop(
        self, enrollment_id: uuid.UUID, current_user: User, reason: str | None = None
    ) -> SequenceEnrollment:
        enrollment = self.get(enrollment_id)
        if not current_user.is_admin and enrollment.owner_user_id != current_user.id:
            raise PermissionDeniedError(
                "Nur der zustaendige Nutzer oder ein Admin kann die Einschreibung stoppen."
            )
        if enrollment.status in ("completed", "stopped"):
            raise BusinessRuleError("Die Einschreibung ist bereits beendet.")
        enrollment.status = "stopped"
        enrollment.stopped_reason = reason or "manuell gestoppt"
        self.session.commit()
        return enrollment

    def for_candidate(self, candidate_id: uuid.UUID) -> list[SequenceEnrollment]:
        return list(
            self.session.scalars(
                select(SequenceEnrollment)
                .where(SequenceEnrollment.candidate_id == candidate_id)
                .order_by(SequenceEnrollment.started_at.desc())
            ).all()
        )

    def to_read(self, enrollment: SequenceEnrollment) -> EnrollmentRead:
        sequence = self.sequences.get(enrollment.sequence_id)
        steps = self.sequences._steps(sequence.id)
        upcoming = (
            steps[enrollment.current_step_index]
            if enrollment.status in ("active", "paused_reply")
            and enrollment.current_step_index < len(steps)
            else None
        )
        due_on = (
            _berlin_day(enrollment.started_at) + timedelta(days=upcoming.day_offset)
            if upcoming is not None
            else None
        )
        return EnrollmentRead(
            id=enrollment.id,
            sequence_id=sequence.id,
            sequence_name=sequence.name,
            candidate_id=enrollment.candidate_id,
            owner_user_id=enrollment.owner_user_id,
            status=enrollment.status,
            stopped_reason=enrollment.stopped_reason,
            started_at=enrollment.started_at,
            current_step_index=enrollment.current_step_index,
            total_steps=len(steps),
            next_step_channel=upcoming.channel if upcoming else None,
            next_step_subject=upcoming.subject if upcoming else None,
            next_step_due_on=due_on,
        )


@dataclass(frozen=True)
class StepResult:
    enrollment_id: uuid.UUID
    outcome: str  # executed_email | executed_task | completed | paused_reply | not_due |
    # stopped | skipped | error
    detail: str | None = None


def _has_reply(session: Session, enrollment: SequenceEnrollment) -> bool:
    return (
        session.scalar(
            select(Activity.id)
            .where(
                Activity.candidate_id == enrollment.candidate_id,
                Activity.activity_type.in_(REPLY_ACTIVITY_TYPES),
                Activity.occurred_at > naive_utc(enrollment.started_at),
            )
            .limit(1)
        )
        is not None
    )


def _block_step(
    session: Session,
    enrollment: SequenceEnrollment,
    sequence: OutreachSequence,
    candidate: Candidate,
    reason: str,
    now: datetime,
) -> StepResult:
    """Dauerhaft nicht ausfuehrbarer Schritt: Einschreibung beenden, Owner informieren."""
    enrollment.status = "stopped"
    enrollment.stopped_reason = reason
    session.add(
        Task(
            candidate_id=candidate.id,
            owner_user_id=enrollment.owner_user_id,
            title=(
                f"Sequenz '{sequence.name}' gestoppt: "
                f"{candidate.first_name} {candidate.last_name}"
            )[:240],
            description=f"{reason}. Bitte manuell weiterverfolgen.",
            due_at=now,
            status=TaskStatus.OPEN,
            priority=TaskPriority.NORMAL,
        )
    )
    session.commit()
    return StepResult(enrollment.id, "stopped", reason)


def _advance(
    session: Session, enrollment: SequenceEnrollment, total_steps: int, now: datetime
) -> str:
    enrollment.current_step_index += 1
    enrollment.last_step_at = now
    done = enrollment.current_step_index >= total_steps
    if done:
        enrollment.status = "completed"
    session.commit()
    return "completed" if done else "next"


def _process(
    session: Session,
    enrollment: SequenceEnrollment,
    now: datetime,
    sender: Sender,
    resolve_account: Callable[[User], MailAccount | None],
) -> StepResult:
    sequence = session.get(OutreachSequence, enrollment.sequence_id)
    if sequence is None or not sequence.is_active:
        return StepResult(enrollment.id, "skipped", "Sequenz deaktiviert")
    steps = list(
        session.scalars(
            select(OutreachSequenceStep)
            .where(OutreachSequenceStep.sequence_id == sequence.id)
            .order_by(OutreachSequenceStep.step_index)
        ).all()
    )
    if enrollment.current_step_index >= len(steps):
        enrollment.status = "completed"
        session.commit()
        return StepResult(enrollment.id, "completed")
    candidate = session.get(Candidate, enrollment.candidate_id)
    if candidate is None:
        return StepResult(enrollment.id, "skipped", "Kandidat nicht gefunden")

    if _has_reply(session, enrollment):
        enrollment.status = "paused_reply"
        session.commit()
        return StepResult(enrollment.id, "paused_reply")

    step = steps[enrollment.current_step_index]
    today = _berlin_day(now)
    due_day = _berlin_day(enrollment.started_at) + timedelta(days=step.day_offset)
    ran_today = (
        enrollment.last_step_at is not None and _berlin_day(enrollment.last_step_at) >= today
    )
    if today < due_day or ran_today:
        return StepResult(enrollment.id, "not_due")

    owner = session.get(User, enrollment.owner_user_id) if enrollment.owner_user_id else None
    subject = render_template(step.subject, candidate, owner)
    body = render_template(step.body_template or "", candidate, owner)

    if step.channel != "email":
        session.add(
            Task(
                candidate_id=candidate.id,
                owner_user_id=enrollment.owner_user_id,
                title=subject[:240],
                description=body or None,
                due_at=now,
                status=TaskStatus.OPEN,
                priority=TaskPriority.NORMAL,
            )
        )
        result = _advance(session, enrollment, len(steps), now)
        return StepResult(enrollment.id, "completed" if result == "completed" else "executed_task")

    if not (candidate.email or "").strip():
        return _block_step(session, enrollment, sequence, candidate, "Keine E-Mail-Adresse", now)
    if not candidate.consent_received:
        return _block_step(
            session, enrollment, sequence, candidate, "Keine Einwilligung erfasst", now
        )
    if owner is None:
        return StepResult(enrollment.id, "skipped", "Kein zustaendiger Nutzer")
    account = resolve_account(owner)
    if account is None:
        return StepResult(enrollment.id, "skipped", "Kein Sendekonto verfuegbar")
    try:
        sender(
            session,
            account=account,
            to_address=candidate.email,
            to_name=f"{candidate.first_name} {candidate.last_name}",
            subject=subject,
            body_text=body,
            candidate_id=candidate.id,
            current_user=owner,
        )
    except DailyLimitReachedError as exc:
        session.rollback()
        return StepResult(enrollment.id, "skipped", str(exc))
    except ConsentNotGrantedError as exc:
        session.rollback()
        return _block_step(session, enrollment, sequence, candidate, str(exc), now)
    result = _advance(session, enrollment, len(steps), now)
    return StepResult(enrollment.id, "completed" if result == "completed" else "executed_email")


def run_due_steps(
    session: Session,
    *,
    now: datetime | None = None,
    sender: Sender = send_mail,
    resolve_account: Callable[[User], MailAccount | None] | None = None,
) -> list[StepResult]:
    """Tageslauf ueber alle laufenden Einschreibungen (siehe Modul-Docstring)."""
    current = now or datetime.now(UTC)
    resolve = resolve_account or MailAccountService(session).resolve_send_account
    ids = list(
        session.scalars(
            select(SequenceEnrollment.id)
            .where(SequenceEnrollment.status == "active")
            .order_by(SequenceEnrollment.started_at)
        ).all()
    )
    results: list[StepResult] = []
    for enrollment_id in ids:
        try:
            enrollment = session.get(SequenceEnrollment, enrollment_id)
            if enrollment is None or enrollment.status != "active":
                continue
            results.append(_process(session, enrollment, current, sender, resolve))
        except Exception as exc:  # noqa: BLE001 - eine Einschreibung darf die anderen nicht blockieren
            session.rollback()
            logger.warning("Sequenz-Schritt fuer %s fehlgeschlagen", enrollment_id, exc_info=True)
            results.append(StepResult(enrollment_id, "error", str(exc)))
    return results
