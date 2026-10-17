# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Überschneidung desselben Leiharbeitnehmers: nur warnen, nie hart sperren.

Ein Leiharbeitnehmer kann nicht an zwei Orten gleichzeitig arbeiten - kommt es trotzdem vor
(Teilzeit, Übergabe), entscheidet der Disponent. Beim Anlegen und beim Ändern der Daten eines
Einsatzes prüft der Service, ob ein anderer geplanter oder aktiver Einsatz DESSELBEN
Leiharbeitnehmers (gleicher oder anderer Kunde) im selben Zeitraum liegt. Treffer: die API
antwortet 409 mit der Liste der überschneidenden Einsätze; mit `confirm_overlap=true` wird
trotzdem gespeichert und ein Audit-Eintrag `overlap_acknowledged` geschrieben. Die Liste enthält
weder Lohn noch Verrechnungssatz.

Zeiträume sind inklusive; angrenzende Tage (Ende 10., Beginn 11.) überschneiden sich nicht. Ein
Einsatz ohne geplantes Ende läuft offen weiter."""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from cc_crm.core.errors import OverlapConflictError
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.staffing import StaffingAssignment, StaffingAssignmentStatus

_OPEN = (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)
_STATUS_TEXT = {
    StaffingAssignmentStatus.PLANNED: "geplant",
    StaffingAssignmentStatus.ACTIVE: "aktiv",
}


@dataclass(frozen=True)
class OverlapItem:
    assignment_id: uuid.UUID
    client_name: str
    start_date: date
    planned_end_date: date | None
    status: StaffingAssignmentStatus

    def describe(self) -> str:
        end = f"{self.planned_end_date:%d.%m.%Y}" if self.planned_end_date else "offen"
        return (
            f"{self.client_name} ({self.start_date:%d.%m.%Y} bis {end}, "
            f"{_STATUS_TEXT.get(self.status, self.status.value)})"
        )

    def as_json(self) -> dict[str, object]:
        return {
            "assignment_id": str(self.assignment_id),
            "client_name": self.client_name,
            "start_date": self.start_date.isoformat(),
            "planned_end_date": (
                self.planned_end_date.isoformat() if self.planned_end_date else None
            ),
            "status": self.status.value,
        }


def find_overlaps(
    session: Session,
    worker_id: uuid.UUID,
    start: date,
    end: date | None,
    exclude_id: uuid.UUID | None = None,
) -> list[OverlapItem]:
    """Andere geplante/aktive Einsätze des Leiharbeitnehmers im Zeitraum [start, end]."""
    statement = (
        select(StaffingAssignment, ClientCompany.name)
        .join(ClientCompany, ClientCompany.id == StaffingAssignment.client_company_id)
        .where(
            StaffingAssignment.worker_id == worker_id,
            StaffingAssignment.status.in_(_OPEN),
            or_(
                StaffingAssignment.planned_end_date.is_(None),
                StaffingAssignment.planned_end_date >= start,
            ),
            *([StaffingAssignment.start_date <= end] if end is not None else []),
            *([StaffingAssignment.id != exclude_id] if exclude_id is not None else []),
        )
        .order_by(StaffingAssignment.start_date, StaffingAssignment.id)
    )
    return [
        OverlapItem(a.id, name, a.start_date, a.planned_end_date, a.status)
        for a, name in session.execute(statement).all()
    ]


def overlap_text(items: list[OverlapItem]) -> str:
    noun = "einen anderen Einsatz" if len(items) == 1 else f"{len(items)} andere Einsätze"
    return (
        f"Überschneidung: Dieser Leiharbeitnehmer hat im selben Zeitraum bereits {noun}: "
        + "; ".join(item.describe() for item in items)
        + "."
    )


def raise_if_unconfirmed(items: list[OverlapItem], confirmed: bool, action: str) -> None:
    """409 mit der Liste, solange der Disponent die Überschneidung nicht bestätigt hat."""
    if items and not confirmed:
        raise OverlapConflictError(
            f"{overlap_text(items)} Trotzdem {action}?", [item.as_json() for item in items]
        )
