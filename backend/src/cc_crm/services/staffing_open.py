# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Eine gemeinsame Antwort auf "ist dieser Einsatz noch offen?".

Überschneidung (`staffing_overlap`), Fristen-Job (`staffing_deadline_job.assignment_span`) und
"überfällig" (`is_overdue`) müssen dasselbe meinen. Ein AKTIVER Einsatz, dessen geplantes Ende
schon vorbei ist, gilt als offen, bis er beendet oder verlängert wird: das ist die vorsichtige
Richtung, und die Kette erlischt nicht, nur weil niemand das Ende pflegt."""

from datetime import date

from cc_crm.models.staffing import StaffingAssignment, StaffingAssignmentStatus

OPEN_STATUSES = (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)


def is_overdue(assignment: StaffingAssignment, today: date) -> bool:
    """Aktiv, aber das geplante Ende liegt vor heute (beenden oder verlängern)."""
    return (
        assignment.status == StaffingAssignmentStatus.ACTIVE
        and assignment.planned_end_date is not None
        and assignment.planned_end_date < today
    )


def effective_end_date(assignment: StaffingAssignment, today: date) -> date | None:
    """Bis wann der Einsatz gilt: geplantes Ende, überfällig und aktiv: offen (`None`)."""
    if is_overdue(assignment, today):
        return None
    return assignment.planned_end_date


def assignment_is_open(assignment: StaffingAssignment, today: date) -> bool:
    """Geplant oder aktiv und nicht schon vor heute zu Ende (überfällige aktive Einsätze: offen)."""
    if assignment.status not in OPEN_STATUSES:
        return False
    end = effective_end_date(assignment, today)
    return end is None or end >= today
