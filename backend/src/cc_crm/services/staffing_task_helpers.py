# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Gemeinsame Hilfen für Aufgaben und Meldungen der Überlassung.

Früher in `staffing_deadline_job.py`, von dort aber auch von anderen Services importiert
(`staffing_contract_sync`). Eigenes Modul, damit Services nicht den Job importieren müssen.
Verhalten unverändert: eine Aufgabe je Kennung (`create_task_once`), aktive Admins, Namen eines
Paares. Keine Lohn- oder Margenwerte."""

import uuid
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import TaskPriority
from cc_crm.models.staffing import StaffingWorker
from cc_crm.models.task import Task
from cc_crm.models.user import User

BERLIN = ZoneInfo("Europe/Berlin")


def _due_at(today: date) -> datetime:
    return datetime.combine(today, time(7, 0), tzinfo=BERLIN).astimezone(UTC)


def create_task_once(
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


def active_admin_ids(session: Session) -> list[uuid.UUID]:
    return list(
        session.scalars(
            select(User.id).where(User.role == "admin", User.is_active.is_(True)).order_by(User.id)
        ).all()
    )


def pair_names(session: Session, worker_id: uuid.UUID, client_id: uuid.UUID) -> tuple[str, str]:
    row = session.execute(
        select(Candidate.first_name, Candidate.last_name)
        .join(StaffingWorker, StaffingWorker.candidate_id == Candidate.id)
        .where(StaffingWorker.id == worker_id)
    ).first()
    worker = f"{row[0] or ''} {row[1] or ''}".strip() if row else "Unbekannt"
    client = session.scalar(select(ClientCompany.name).where(ClientCompany.id == client_id))
    return worker, client or "Unbekannt"
