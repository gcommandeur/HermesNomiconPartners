# NOMICON: Aufgaben der Ansicht Überlassung - nur in der Nomicon-Kopie.
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel

TaskKind = Literal[
    "deadline_max",
    "equal_pay",
    "timesheet_missing",
    "timesheet_overdue",
    "timesheet_rejected",
    "checklist_open",
    "assignment_overdue",
    "bench",
    "license",
]
Severity = Literal["red", "yellow", "info"]


class StaffingTaskRead(BaseModel):
    kind: TaskKind
    severity: Severity
    title: str
    detail: str
    due_at: date | None = None
    # Ziel der Aufgabe in der Oberfläche (Einsatz, Leiharbeitnehmer oder Compliance)
    assignment_id: uuid.UUID | None = None
    worker_id: uuid.UUID | None = None


class StaffingTasksRead(BaseModel):
    """To-dos und Hinweise der Ansicht Überlassung. Keine Lohn- oder Margenangaben."""

    tasks: list[StaffingTaskRead]
    alerts: list[str]  # kurze Hinweiszeile (rote Fristen, Erlaubnis, Rückstand)
    bench_after_days: int
    equal_pay_warn_days: int
