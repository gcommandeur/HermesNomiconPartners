# NOMICON: Disposition der Ueberlassung - nur in der Nomicon-Kopie.
import uuid
from datetime import date

from pydantic import BaseModel

from cc_crm.schemas.staffing import StaffingLicenseStatus


class StaffingBenchWorkerRead(BaseModel):
    """Leiharbeitnehmer ohne aktiven oder geplanten Einsatz ("Bench")."""

    worker_id: uuid.UUID
    worker_name: str
    free_since: date | None  # Ende des letzten Einsatzes, ersatzweise Eintrittsdatum
    days_free: int | None
    pay_grade: str | None
    work_permit_valid_until: date | None


class StaffingTimesheetInboxRead(BaseModel):
    """Stundenzettel nach Stand (nur Einsaetze im Sichtbereich des Nutzers)."""

    open: int  # offen, noch nicht zur Freigabe beim Kunden
    open_overdue: int  # offen, Zeitraum schon vorbei = Rueckstand
    submitted: int  # beim Kunden zur Freigabe
    approved_unbilled: int  # freigegeben, noch auf keiner Rechnung
    rejected: int


class StaffingDispositionRead(BaseModel):
    active_assignments: int
    planned_assignments: int
    open_checklist_assignments: int
    bench_count: int
    timesheet_backlog: int  # open_overdue + approved_unbilled
    license: StaffingLicenseStatus
    inbox: StaffingTimesheetInboxRead
    bench: list[StaffingBenchWorkerRead]
