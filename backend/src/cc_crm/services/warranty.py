from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.config import get_settings
from cc_crm.models.enums import TaskPriority, TaskStatus, WarrantyStatus
from cc_crm.models.recruiting import Placement
from cc_crm.models.submission import CandidateSubmission
from cc_crm.repositories.tasks import TaskRepository

WARRANTY_FOLLOW_UP_TITLE = "Gewährleistung läuft bald ab"


def add_months(start: date, months: int) -> date:
    """Kalendermonate zu einem Datum addieren, Tag ggf. auf den letzten Tag
    des Zielmonats gekappt (z.B. 31. Januar + 1 Monat -> 28./29. Februar)."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = start.day
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


def warranty_end_date(start_date: date, guarantee_period_months: int) -> date:
    return add_months(start_date, guarantee_period_months)


def warranty_status(end_date: date, *, today: date | None = None) -> WarrantyStatus:
    today = today or date.today()
    settings = get_settings()
    if today > end_date:
        return WarrantyStatus.ABGELAUFEN
    if today >= end_date - timedelta(days=settings.warranty_follow_up_days_before):
        return WarrantyStatus.BALD_ABLAUFEND
    return WarrantyStatus.LAUFEND


class WarrantyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tasks = TaskRepository(session)

    def schedule_follow_up(self, placement: Placement, submission: CandidateSubmission) -> None:
        """Legt bei Placement-Anlage automatisch einen Follow-up-Task X Tage
        (Default 14, siehe warranty_follow_up_days_before) vor Ablauf der
        Gewährleistung an."""
        end_date = warranty_end_date(placement.start_date, placement.guarantee_period_months)
        due_date = end_date - timedelta(days=get_settings().warranty_follow_up_days_before)
        due_at = datetime.combine(due_date, datetime.min.time(), tzinfo=UTC)
        self.tasks.create(
            {
                "candidate_id": submission.candidate_id,
                "client_company_id": submission.client_company_id,
                "candidate_submission_id": submission.id,
                "title": WARRANTY_FOLLOW_UP_TITLE,
                "description": (
                    f"Automatisch erzeugt: Gewährleistung endet am {end_date.isoformat()}"
                ),
                "due_at": due_at,
                "status": TaskStatus.OPEN,
                "priority": TaskPriority.NORMAL,
            }
        )

    def active_warranties(self) -> list[tuple[Placement, date, WarrantyStatus]]:
        """Alle Placements mit LAUFEND oder BALD_ABLAUFEND Status (die
        Uebersicht "Laufende Gewaehrleistungen"), sortiert nach dem
        naechstliegenden Ablaufdatum zuerst."""
        placements = self.session.scalars(select(Placement)).all()
        results: list[tuple[Placement, date, WarrantyStatus]] = []
        for placement in placements:
            end_date = warranty_end_date(placement.start_date, placement.guarantee_period_months)
            status = warranty_status(end_date)
            if status != WarrantyStatus.ABGELAUFEN:
                results.append((placement, end_date, status))
        results.sort(key=lambda item: item[1])
        return results
