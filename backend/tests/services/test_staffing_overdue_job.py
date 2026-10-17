# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Ueberfaellige Einsaetze: Zaehlung in der Frist und taegliche Aufgabe fuer den Disponenten."""

from datetime import date

from sqlalchemy.orm import Session

from cc_crm.models.staffing import StaffingAssignment, StaffingAssignmentStatus
from cc_crm.services.staffing_deadline_job import (
    assignment_span,
    pair_deadline,
    run_deadline_job,
)
from cc_crm.services.staffing_deadlines import Span
from tests.services.test_staffing_deadline_job import (
    _assignment,
    _client,
    _tasks,
    _user,
    _worker,
    session,
)

D = date
_ = session  # Fixture (per Import registriert)


def _plain(
    status: StaffingAssignmentStatus, start: date, planned: date | None
) -> StaffingAssignment:
    return StaffingAssignment(
        start_date=start, planned_end_date=planned, actual_end_date=None, status=status
    )


def _overdue_tasks(session: Session):  # type: ignore[no-untyped-def]
    return [t for t in _tasks(session) if t.title.startswith("Einsatz überfällig")]


# --- Zuordnung zum Zeitraum -----------------------------------------------------------------


def test_active_assignment_past_its_planned_end_counts_as_open() -> None:
    today = D(2026, 6, 1)
    overdue = _plain(StaffingAssignmentStatus.ACTIVE, D(2026, 1, 1), D(2026, 2, 28))
    assert assignment_span(overdue, today) == Span(D(2026, 1, 1), None)
    # Noch nicht ueberschritten (auch am letzten geplanten Tag): bleibt begrenzt
    running = _plain(StaffingAssignmentStatus.ACTIVE, D(2026, 1, 1), D(2026, 6, 1))
    assert assignment_span(running, today) == Span(D(2026, 1, 1), D(2026, 6, 1))
    # Nur aktive Einsaetze: geplante und beendete behalten ihr Ende
    planned = _plain(StaffingAssignmentStatus.PLANNED, D(2026, 1, 1), D(2026, 2, 28))
    assert assignment_span(planned, today) == Span(D(2026, 1, 1), D(2026, 2, 28), planned=True)
    ended = _plain(StaffingAssignmentStatus.ENDED, D(2026, 1, 1), D(2026, 2, 28))
    ended.actual_end_date = D(2026, 2, 20)
    assert assignment_span(ended, today) == Span(D(2026, 1, 1), D(2026, 2, 20))
    # Ohne geplantes Ende war er schon vorher offen
    open_ended = _plain(StaffingAssignmentStatus.ACTIVE, D(2026, 1, 1), None)
    assert assignment_span(open_ended, today) == Span(D(2026, 1, 1), None)


def test_overdue_assignment_keeps_counting_days_until_today(session: Session) -> None:
    worker, client = _worker(session), _client(session)
    _assignment(session, worker, client, D(2026, 1, 1), end=D(2026, 2, 28))
    result = pair_deadline(session, worker.id, client.id, D(2026, 6, 1))
    # bisher (mit Ende 28.2.) waeren es nur 59 Tage und die Kette waere erloschen
    assert result.has_chain
    assert result.counted_days == 152  # 1.1. bis 1.6.


# --- Taegliche Aufgabe ----------------------------------------------------------------------


def test_job_creates_one_overdue_task_for_the_owner(session: Session) -> None:
    owner = _user(session, "dispo@x.example")
    worker, client = _worker(session), _client(session)
    assignment = _assignment(
        session, worker, client, D(2026, 1, 1), end=D(2026, 2, 28), owner=owner
    )

    assert run_deadline_job(session, D(2026, 2, 28)).tasks_created == 0  # letzter Planungstag
    first = run_deadline_job(session, D(2026, 3, 1))  # Tag nach dem geplanten Ende
    tasks = _overdue_tasks(session)
    assert len(tasks) == 1 and first.tasks_created >= 1
    task = tasks[0]
    assert task.owner_user_id == owner.id
    assert "Mira Muster bei Logistik GmbH" in task.title
    assert "28.02.2026" in (task.description or "")
    assert "beenden oder verlängern" in (task.description or "")
    assert task.priority.value == "high"
    assert "€" not in (task.description or "") and "14.50" not in (task.description or "")

    # Einmalig: weitere Laeufe erzeugen nichts Neues
    run_deadline_job(session, D(2026, 3, 2))
    run_deadline_job(session, D(2026, 4, 15))
    assert len(_overdue_tasks(session)) == 1

    # Verlaengert (neues Ende in der Zukunft): ruhig. Wird auch das ueberschritten: neue Aufgabe.
    assignment.planned_end_date = D(2026, 5, 31)
    session.commit()
    run_deadline_job(session, D(2026, 5, 31))
    assert len(_overdue_tasks(session)) == 1
    run_deadline_job(session, D(2026, 6, 1))
    assert len(_overdue_tasks(session)) == 2


def test_job_overdue_task_goes_to_admins_without_owner_and_skips_other_states(
    session: Session,
) -> None:
    admin = _user(session, "gf@x.example", "admin")
    _user(session, "member@x.example")
    worker, client = _worker(session), _client(session)
    other_worker = _worker(session, "Jonas")
    _assignment(session, worker, client, D(2026, 1, 1), end=D(2026, 2, 28), owner=None)
    # beendet und geplant mit vergangenem Ende: keine Ueberfaelligkeits-Aufgabe
    _assignment(
        session,
        other_worker,
        client,
        D(2026, 1, 1),
        end=D(2026, 2, 28),
        status=StaffingAssignmentStatus.ENDED,
    )
    _assignment(
        session,
        _worker(session, "Eva"),
        client,
        D(2026, 1, 1),
        end=D(2026, 2, 28),
        status=StaffingAssignmentStatus.PLANNED,
    )
    run_deadline_job(session, D(2026, 3, 5))
    tasks = _overdue_tasks(session)
    assert [t.owner_user_id for t in tasks] == [admin.id]
    assert "Mira" in tasks[0].title
