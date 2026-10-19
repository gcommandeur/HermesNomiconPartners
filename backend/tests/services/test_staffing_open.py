# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Eine gemeinsame Antwort auf "offen": Ueberschneidung, Fristen-Job und "ueberfaellig"."""

from datetime import date

from cc_crm.models.staffing import StaffingAssignment, StaffingAssignmentStatus
from cc_crm.services.staffing_deadline_job import assignment_span
from cc_crm.services.staffing_open import assignment_is_open, effective_end_date, is_overdue

TODAY = date(2026, 10, 19)


def _a(status: StaffingAssignmentStatus, end: date | None) -> StaffingAssignment:
    return StaffingAssignment(start_date=date(2026, 1, 1), planned_end_date=end, status=status)


def test_overdue_active_assignment_is_open_with_open_end() -> None:
    a = _a(StaffingAssignmentStatus.ACTIVE, date(2026, 9, 1))
    assert is_overdue(a, TODAY)
    assert effective_end_date(a, TODAY) is None
    assert assignment_is_open(a, TODAY)
    assert assignment_span(a, TODAY).end is None  # Fristen-Job meint dasselbe


def test_ended_aborted_and_past_planned_are_not_open() -> None:
    assert not assignment_is_open(_a(StaffingAssignmentStatus.ENDED, date(2026, 9, 1)), TODAY)
    assert not assignment_is_open(_a(StaffingAssignmentStatus.ABORTED, None), TODAY)
    planned_past = _a(StaffingAssignmentStatus.PLANNED, date(2026, 9, 1))
    assert not is_overdue(planned_past, TODAY)
    assert not assignment_is_open(planned_past, TODAY)


def test_running_assignments_are_open() -> None:
    assert assignment_is_open(_a(StaffingAssignmentStatus.ACTIVE, date(2026, 12, 1)), TODAY)
    assert assignment_is_open(_a(StaffingAssignmentStatus.ACTIVE, None), TODAY)
    assert assignment_is_open(_a(StaffingAssignmentStatus.PLANNED, date(2026, 10, 19)), TODAY)
