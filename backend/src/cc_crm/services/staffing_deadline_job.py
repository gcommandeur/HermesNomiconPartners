# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Fristen je Paar (Leiharbeitnehmer, Kunde) aus der Datenbank und der tägliche Job.

Der Job legt Aufgaben (`tasks`) für Disponenten an - sie erscheinen in der Aufgabenliste und
in der taeglichen Faelligkeits-Mail (services/due_reminders.py). Gegen Dubletten traegt jede
Aufgabe eine Kennung in der Beschreibung; es gibt je Paar und Schwelle genau EINE Aufgabe,
auch wenn sie inzwischen erledigt ist (sie kommt erst wieder, wenn sich die Kette ändert)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import TaskPriority
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingLicense,
    StaffingPriorPeriod,
    StaffingWorker,
)
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.services.staffing_deadlines import (
    DeadlineConfig,
    DeadlineResult,
    Span,
    Traffic,
    compute_deadline,
)
from cc_crm.services.staffing_settings import load_config

_BERLIN = ZoneInfo("Europe/Berlin")
_COUNTED = (
    StaffingAssignmentStatus.PLANNED,
    StaffingAssignmentStatus.ACTIVE,
    StaffingAssignmentStatus.ENDED,
)


def assignment_span(assignment: StaffingAssignment) -> Span:
    """Beendete Einsätze zählen bis zum tatsächlichen Ende, laufende bis zum geplanten Ende
    (ohne Plan: offen)."""
    if assignment.status == StaffingAssignmentStatus.ENDED:
        return Span(
            assignment.start_date, assignment.actual_end_date or assignment.planned_end_date
        )
    return Span(assignment.start_date, assignment.planned_end_date)


def pair_deadline(
    session: Session,
    worker_id: uuid.UUID,
    client_company_id: uuid.UUID,
    today: date,
    config: DeadlineConfig | None = None,
) -> DeadlineResult:
    assignments = session.scalars(
        select(StaffingAssignment).where(
            StaffingAssignment.worker_id == worker_id,
            StaffingAssignment.client_company_id == client_company_id,
            StaffingAssignment.status.in_(_COUNTED),
        )
    ).all()
    # Vorzeiten beim selben Kunden (früher geleistet) zählen wie Einsätze mit, sind aber immer
    # abgeschlossen.
    prior = session.scalars(
        select(StaffingPriorPeriod).where(
            StaffingPriorPeriod.worker_id == worker_id,
            StaffingPriorPeriod.client_company_id == client_company_id,
        )
    ).all()
    return compute_deadline(
        [assignment_span(a) for a in assignments],
        today,
        config or load_config(session),
        prior_spans=[Span(p.start_date, p.end_date) for p in prior],
    )


@dataclass
class DeadlineJobResult:
    pairs_checked: int = 0
    tasks_created: int = 0


def _due_at(today: date) -> datetime:
    return datetime.combine(today, time(7, 0), tzinfo=_BERLIN).astimezone(UTC)


def _create_task_once(
    session: Session,
    *,
    marker: str,
    title: str,
    body: str,
    owner_user_id: uuid.UUID,
    priority: TaskPriority,
    today: date,
) -> bool:
    exists = session.scalar(select(Task.id).where(Task.description.contains(marker)).limit(1))
    if exists is not None:
        return False
    session.add(
        Task(
            title=title,
            description=f"{body}\n\n{marker}",
            due_at=_due_at(today),
            owner_user_id=owner_user_id,
            priority=priority,
        )
    )
    return True


def _active_admin_ids(session: Session) -> list[uuid.UUID]:
    return list(
        session.scalars(
            select(User.id).where(User.role == "admin", User.is_active.is_(True)).order_by(User.id)
        ).all()
    )


def run_deadline_job(session: Session, today: date | None = None) -> DeadlineJobResult:
    """Täglich ausführen (scripts/run_staffing_deadlines.py). Idempotent."""
    day = today or datetime.now(_BERLIN).date()
    config = load_config(session)
    result = DeadlineJobResult()
    admins = _active_admin_ids(session)

    pairs = session.execute(
        select(StaffingAssignment.worker_id, StaffingAssignment.client_company_id)
        .where(
            StaffingAssignment.status.in_(
                (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)
            )
        )
        .distinct()
    ).all()
    for worker_id, client_id in pairs:
        result.pairs_checked += 1
        deadline = pair_deadline(session, worker_id, client_id, day, config)
        if not deadline.has_chain or deadline.chain_start is None or deadline.max_end_date is None:
            continue
        worker_name, client_name = _names(session, worker_id, client_id)
        owner = session.scalar(
            select(StaffingAssignment.owner_user_id)
            .where(
                StaffingAssignment.worker_id == worker_id,
                StaffingAssignment.client_company_id == client_id,
                StaffingAssignment.status.in_(
                    (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)
                ),
                StaffingAssignment.owner_user_id.is_not(None),
            )
            .order_by(StaffingAssignment.start_date.desc())
            .limit(1)
        )
        recipients = [owner] if owner is not None else admins
        levels: list[tuple[str, str, str, TaskPriority]] = []
        if deadline.traffic in (Traffic.YELLOW, Traffic.RED):
            level = "exceeded" if deadline.exceeded else deadline.traffic.value
            levels.append(
                (
                    level,
                    f"Überlassungsfrist: {worker_name} bei {client_name}",
                    "Höchstüberlassungsdauer "
                    + (
                        f"seit {-(deadline.days_remaining or 0)} Tag(en) überschritten"
                        if deadline.exceeded
                        else f"endet am {deadline.max_end_date:%d.%m.%Y} "
                        f"(noch {deadline.days_remaining} Tage)"
                    )
                    + ". Einsatz beenden oder Übernahme/Neubesetzung planen. "
                    "Hinweis: kein Rechtsrat.",
                    TaskPriority.URGENT if deadline.traffic == Traffic.RED else TaskPriority.HIGH,
                )
            )
        if deadline.equal_pay_reached:
            levels.append(
                (
                    "equal_pay",
                    f"Equal Pay ab jetzt: {worker_name} bei {client_name}",
                    f"Seit {deadline.equal_pay_from:%d.%m.%Y} gilt Equal Pay (gleiches Entgelt wie "
                    "die Stammbelegschaft). Lohn und Verrechnungssatz prüfen. Hinweis: kein "
                    "Rechtsrat, Tarifverträge können abweichen.",
                    TaskPriority.HIGH,
                )
            )
        for level, title, body, priority in levels:
            for user_id in recipients:
                marker = (
                    f"[staffing-deadline:{worker_id}:{client_id}:{level}:"
                    f"{deadline.chain_start.isoformat()}:{user_id}]"
                )
                if _create_task_once(
                    session,
                    marker=marker,
                    title=title,
                    body=body,
                    owner_user_id=user_id,
                    priority=priority,
                    today=day,
                ):
                    result.tasks_created += 1

    for lic in session.scalars(
        select(StaffingLicense).where(StaffingLicense.valid_to.is_not(None))
    ):
        if lic.valid_to is None or (lic.valid_to - day).days > lic.reminder_days:
            continue
        remaining = (lic.valid_to - day).days
        for user_id in admins:
            if _create_task_once(
                session,
                marker=(
                    f"[staffing-license:{lic.id}:{lic.valid_to.isoformat()}:"
                    f"{'expired' if remaining < 0 else 'expiring'}:{user_id}]"
                ),
                title=f"AÜG-Erlaubnis {'abgelaufen' if remaining < 0 else 'läuft ab'}: "
                f"{lic.authority}",
                body=(
                    f"Die Erlaubnis zur Arbeitnehmerüberlassung ({lic.authority}"
                    f"{', Az. ' + lic.file_number if lic.file_number else ''}) "
                    + (
                        f"ist seit {-remaining} Tag(en) abgelaufen."
                        if remaining < 0
                        else f"läuft am {lic.valid_to:%d.%m.%Y} ab (noch {remaining} Tage)."
                    )
                    + " Verlängerung rechtzeitig beantragen; ohne gültige Erlaubnis dürfen "
                    "keine Einsätze aktiv sein."
                ),
                owner_user_id=user_id,
                priority=TaskPriority.URGENT if remaining < 30 else TaskPriority.HIGH,
                today=day,
            ):
                result.tasks_created += 1
    session.commit()
    return result


def _names(session: Session, worker_id: uuid.UUID, client_id: uuid.UUID) -> tuple[str, str]:
    row = session.execute(
        select(Candidate.first_name, Candidate.last_name)
        .join(StaffingWorker, StaffingWorker.candidate_id == Candidate.id)
        .where(StaffingWorker.id == worker_id)
    ).first()
    worker = f"{row[0] or ''} {row[1] or ''}".strip() if row else "Unbekannt"
    client = session.scalar(select(ClientCompany.name).where(ClientCompany.id == client_id))
    return worker, client or "Unbekannt"
