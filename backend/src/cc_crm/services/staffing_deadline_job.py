# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Fristen je Paar (Leiharbeitnehmer, Kunde) aus der Datenbank und der tägliche Job.

Der Job legt Aufgaben (`tasks`) für Disponenten an - sie erscheinen in der Aufgabenliste und
in der taeglichen Faelligkeits-Mail (services/due_reminders.py). Gegen Dubletten traegt jede
Aufgabe eine Kennung in der Beschreibung; es gibt je Paar und Schwelle genau EINE Aufgabe,
auch wenn sie inzwischen erledigt ist (sie kommt erst wieder, wenn sich die Kette ändert)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.enums import TaskPriority
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingLicense,
    StaffingPriorPeriod,
)
from cc_crm.services.staffing_deadlines import (
    DeadlineConfig,
    DeadlineResult,
    Span,
    Traffic,
    compute_deadline,
)
from cc_crm.services.staffing_equal_pay import (
    EQUAL_PAY_PREWARN_DAYS,
    close_equal_pay_tasks,
    pair_equal_pay_confirmed_on,
)
from cc_crm.services.staffing_open import is_overdue
from cc_crm.services.staffing_prior_confirmations import pair_prior_confirmed
from cc_crm.services.staffing_settings import load_config
from cc_crm.services.staffing_task_helpers import (
    BERLIN,
    active_admin_ids,
    create_task_once,
    pair_names,
)

_COUNTED = (
    StaffingAssignmentStatus.PLANNED,
    StaffingAssignmentStatus.ACTIVE,
    StaffingAssignmentStatus.ENDED,
)


def assignment_span(assignment: StaffingAssignment, today: date) -> Span:
    """Beendete Einsätze zählen bis zum tatsächlichen Ende, laufende bis zum geplanten Ende
    (ohne Plan: offen). Ein AKTIVER Einsatz, dessen geplantes Ende schon vorbei ist, gilt als
    offen, bis er beendet oder verlängert wird: das ist die vorsichtige Richtung (die Restlaufzeit
    wird kürzer, nicht länger), und die Kette erlischt nicht, nur weil niemand das Ende pflegt."""
    if assignment.status == StaffingAssignmentStatus.ENDED:
        return Span(
            assignment.start_date, assignment.actual_end_date or assignment.planned_end_date
        )
    if is_overdue(assignment, today):
        return Span(assignment.start_date, None)
    # Geplante (noch nicht aktivierte) Einsätze zählen mit, machen die Frist aber vorläufig.
    return Span(
        assignment.start_date,
        assignment.planned_end_date,
        planned=assignment.status == StaffingAssignmentStatus.PLANNED,
    )


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
        [assignment_span(a, today) for a in assignments],
        today,
        config or load_config(session),
        prior_spans=[Span(p.start_date, p.end_date) for p in prior],
        prior_confirmed=bool(prior) or pair_prior_confirmed(session, worker_id, client_company_id),
    )


@dataclass
class DeadlineJobResult:
    pairs_checked: int = 0
    tasks_created: int = 0


def run_deadline_job(session: Session, today: date | None = None) -> DeadlineJobResult:
    """Täglich ausführen (scripts/run_staffing_deadlines.py). Idempotent."""
    day = today or datetime.now(BERLIN).date()
    config = load_config(session)
    result = DeadlineJobResult()
    admins = active_admin_ids(session)

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
        worker_name, client_name = pair_names(session, worker_id, client_id)
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
        # Equal Pay mit Folge: Aufgabe "Lohn prüfen und angleichen", erledigt mit der Bestätigung
        # am Einsatz. Die Texte nennen nur Namen und Datum - nie Lohn- oder Margenwerte.
        confirmed_on = pair_equal_pay_confirmed_on(
            session, worker_id, client_id, deadline.chain_start, deadline.equal_pay_from
        )
        if confirmed_on is not None:
            close_equal_pay_tasks(session, worker_id, client_id)
        elif deadline.equal_pay_from is not None and deadline.equal_pay_reached:
            levels.append(
                (
                    "equal_pay",
                    f"Equal Pay gilt ab {deadline.equal_pay_from:%d.%m.%Y}: Lohn von "
                    f"{worker_name} bei {client_name} prüfen und angleichen",
                    f"Seit {deadline.equal_pay_from:%d.%m.%Y} gilt Equal Pay (gleiches Entgelt wie "
                    "die Stammbelegschaft). Bitte den Lohn prüfen, angleichen und danach im "
                    "Einsatz „Equal Pay bestätigen“. Hinweis: kein Rechtsrat, Tarifverträge "
                    "können abweichen.",
                    TaskPriority.HIGH,
                )
            )
        elif (
            deadline.equal_pay_from is not None
            and 0 < (deadline.equal_pay_from - day).days <= EQUAL_PAY_PREWARN_DAYS
        ):
            levels.append(
                (
                    "equal_pay_soon",
                    f"Equal Pay beginnt am {deadline.equal_pay_from:%d.%m.%Y}: "
                    f"{worker_name} bei {client_name}",
                    f"In {(deadline.equal_pay_from - day).days} Tag(en), am "
                    f"{deadline.equal_pay_from:%d.%m.%Y}, gilt Equal Pay. Den Lohn rechtzeitig "
                    "prüfen. Hinweis: kein Rechtsrat, Tarifverträge können abweichen.",
                    TaskPriority.NORMAL,
                )
            )
        for level, title, body, priority in levels:
            for user_id in recipients:
                marker = (
                    f"[staffing-deadline:{worker_id}:{client_id}:{level}:"
                    f"{deadline.chain_start.isoformat()}:{user_id}]"
                )
                if create_task_once(
                    session,
                    marker=marker,
                    title=title,
                    body=body,
                    owner_user_id=user_id,
                    priority=priority,
                    today=day,
                ):
                    result.tasks_created += 1

    _overdue_assignment_tasks(session, day, result, admins)
    _missing_contract_tasks(session, day, result)

    for lic in session.scalars(
        select(StaffingLicense).where(StaffingLicense.valid_to.is_not(None))
    ):
        if lic.valid_to is None or (lic.valid_to - day).days > lic.reminder_days:
            continue
        remaining = (lic.valid_to - day).days
        for user_id in admins:
            if create_task_once(
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


def _missing_contract_tasks(session: Session, day: date, result: DeadlineJobResult) -> None:
    """Aktive Einsätze ohne gültigen Überlassungsvertrag (kein Vertrag, abgelaufen, falscher
    Zeitraum): eine kurze Aufgabe für den Disponenten, einmalig je Zustand (Kennung). Ohne Lohn-
    oder Margenwerte. Der Einsatz wird nicht blockiert."""
    from cc_crm.services.staffing_contract_sync import notify_contract_gap  # Zyklus vermeiden

    for assignment in session.scalars(
        select(StaffingAssignment)
        .where(StaffingAssignment.status == StaffingAssignmentStatus.ACTIVE)
        .order_by(StaffingAssignment.start_date, StaffingAssignment.id)
    ).all():
        result.tasks_created += notify_contract_gap(session, assignment, None, day)


def _overdue_assignment_tasks(
    session: Session, day: date, result: DeadlineJobResult, admins: list[uuid.UUID]
) -> None:
    """Aktive Einsätze mit überschrittenem geplantem Ende: eine Aufgabe (hohe Priorität) für den
    Disponenten, einmalig je Einsatz UND geplantem Ende - wird das Ende verlängert und erneut
    überschritten, entsteht eine neue. Keine Lohn- oder Margenwerte im Text."""
    overdue = session.scalars(
        select(StaffingAssignment)
        .where(
            StaffingAssignment.status == StaffingAssignmentStatus.ACTIVE,
            StaffingAssignment.planned_end_date.is_not(None),
            StaffingAssignment.planned_end_date < day,
        )
        .order_by(StaffingAssignment.start_date, StaffingAssignment.id)
    ).all()
    for assignment in overdue:
        planned_end = assignment.planned_end_date
        if planned_end is None:
            continue
        worker_name, client_name = pair_names(
            session, assignment.worker_id, assignment.client_company_id
        )
        recipients = [assignment.owner_user_id] if assignment.owner_user_id is not None else admins
        for user_id in recipients:
            if create_task_once(
                session,
                marker=f"[staffing-overdue:{assignment.id}:{planned_end.isoformat()}:{user_id}]",
                title=f"Einsatz überfällig: {worker_name} bei {client_name}",
                body=(
                    f"Das geplante Ende {planned_end:%d.%m.%Y} ist überschritten, der Einsatz ist "
                    "noch aktiv – beenden oder verlängern. Bis dahin zählt er in der Frist als "
                    "offen."
                ),
                owner_user_id=user_id,
                priority=TaskPriority.HIGH,
                today=day,
            ):
                result.tasks_created += 1
