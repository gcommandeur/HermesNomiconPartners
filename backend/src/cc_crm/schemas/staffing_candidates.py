# NOMICON: Überlassung am Kandidaten (Liste, Detail) - nur in der Nomicon-Kopie.
import uuid
from typing import Literal

from pydantic import BaseModel, Field

StaffingListFilter = Literal["workers", "bench", "critical", "applicants", "active"]
CandidateStaffingStatus = Literal["none", "applicant", "active", "dormant", "left"]
TrafficLight = Literal["green", "yellow", "red"]


class StaffingCandidateSummaryRequest(BaseModel):
    candidate_ids: list[uuid.UUID] = Field(max_length=500)


class StaffingCandidateSummaryRead(BaseModel):
    """Zeile der Spalte "Überlassung" in der Kandidatenliste. Kein Lohn, keine Marge."""

    candidate_id: uuid.UUID
    status: CandidateStaffingStatus
    worker_id: uuid.UUID | None = None
    client_name: str | None = None  # aktueller (aktiver, sonst geplanter) Kunde
    assignment_status: Literal["planned", "active"] | None = None
    traffic: TrafficLight | None = None  # dringendste Frist der Person
    days_remaining: int | None = None
    bench: bool = False


class StaffingWorkerTimesheetSummary(BaseModel):
    """Stundenzettel einer Person nach Status (nur Einsätze im Besitzbereich des Nutzers)."""

    worker_id: uuid.UUID
    open: int
    submitted: int  # beim Kunden
    approved: int
    rejected: int
    approved_unbilled: int


