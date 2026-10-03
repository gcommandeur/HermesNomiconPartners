"""Taegliche Faelligkeits-Mail (Digest) pro Nutzer.

Zwei bewusst getrennte Teile:
1. `collect_due_items` / `build_digest`: reine Auswahl- und Textlogik, ohne
   Mailversand - ohne Mailserver testbar.
2. `send_due_reminders`: laeuft ueber alle aktiven Nutzer und versendet ueber
   `services/mail_send.py::send_mail` (injizierbar als `sender`, gleiches
   Testmuster wie `smtp_sender` dort). Ein Fehler bei EINEM Nutzer (kein
   Sendekonto, Tageslimit, Transportfehler) bricht den Lauf fuer die
   anderen NICHT ab.

Bewusst einfach: nur EIGENE Items (Owner = Nutzer, kein Team-Scope), keine
Deduplizierung ueber mehrere Tage (jeden Morgen der aktuelle Stand), keine
leere Mail. Einstiegspunkt fuer den Scheduled Job: scripts/send_due_reminders.py.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from cc_crm.core.time import naive_utc
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import TaskStatus
from cc_crm.models.mail import MailAccount, MailMessage
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from cc_crm.models.user import User
from cc_crm.services.mail_accounts import MailAccountService
from cc_crm.services.mail_send import send_mail
from cc_crm.services.submissions import CLOSED_STATUSES

logger = logging.getLogger("cc_crm.due_reminders")

# Wie im Rest des Projekts (services/ics_feed.py): Europe/Berlin-Wanduhrzeit.
_BERLIN = ZoneInfo("Europe/Berlin")
OPEN_TASK_STATUSES = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)

Sender = Callable[..., MailMessage]


@dataclass(frozen=True)
class DueTask:
    title: str
    due_at: datetime


@dataclass(frozen=True)
class DueSubmission:
    label: str  # "Anna Muster bei Kanzlei X"
    status: str
    follow_up_at: datetime


@dataclass(frozen=True)
class DueItems:
    tasks: list[DueTask] = field(default_factory=list)
    submissions: list[DueSubmission] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.tasks and not self.submissions


@dataclass(frozen=True)
class ReminderResult:
    user_id: uuid.UUID
    email: str
    outcome: str  # "sent" | "nothing_due" | "no_account" | "error"
    detail: str | None = None


def berlin_today(now: datetime) -> date:
    return now.astimezone(_BERLIN).date()


def end_of_today_utc(now: datetime) -> datetime:
    """Erster Zeitpunkt NACH dem heutigen (Berlin-)Tag, als naive UTC-Zeit
    (siehe core/time.py::naive_utc) - "heute faellig" heisst `< dieser Wert`."""
    tomorrow = berlin_today(now) + timedelta(days=1)
    start_of_tomorrow = datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=_BERLIN)
    return naive_utc(start_of_tomorrow.astimezone(UTC))


def collect_due_items(session: Session, user: User, *, now: datetime) -> DueItems:
    """Faellige/ueberfaellige EIGENE Tasks und Prozesse eines Nutzers.

    Tasks: offen (open/in_progress), `due_at` heute oder frueher, nicht
    zurueckgestellt. Prozesse: `follow_up_at` heute oder frueher, Status nicht
    abgeschlossen/storniert (CLOSED_STATUSES), nicht archiviert.

    Fuer einen spaeteren Teamleiter-Rollup waere nur `== user.id` durch
    `.in_(Liste von Nutzer-IDs)` zu ersetzen (dieselbe Liste wie
    api/dependencies.py::process_owner_scope) und das Ergebnis nach Owner zu
    gruppieren - Auswahl und Textaufbau sind bereits vom Versand getrennt."""
    cutoff = end_of_today_utc(now)
    now_naive = naive_utc(now)

    task_rows = session.scalars(
        select(Task)
        .where(
            Task.owner_user_id == user.id,
            Task.status.in_(OPEN_TASK_STATUSES),
            Task.due_at.is_not(None),
            Task.due_at < cutoff,
            or_(Task.snoozed_until.is_(None), Task.snoozed_until <= now_naive),
        )
        .order_by(Task.due_at.asc())
    ).all()
    tasks = [DueTask(title=row.title, due_at=row.due_at) for row in task_rows if row.due_at]

    submission_rows = session.execute(
        select(CandidateSubmission, Candidate, ClientCompany)
        .join(Candidate, Candidate.id == CandidateSubmission.candidate_id)
        .outerjoin(ClientCompany, ClientCompany.id == CandidateSubmission.client_company_id)
        .where(
            CandidateSubmission.owner_user_id == user.id,
            CandidateSubmission.follow_up_at.is_not(None),
            CandidateSubmission.follow_up_at < cutoff,
            CandidateSubmission.status.not_in(CLOSED_STATUSES),
            CandidateSubmission.archived_at.is_(None),
        )
        .order_by(CandidateSubmission.follow_up_at.asc())
    ).all()
    submissions = []
    for submission, candidate, company in submission_rows:
        who = f"{candidate.first_name} {candidate.last_name}"
        label = f"{who} bei {company.name}" if company is not None else who
        assert submission.follow_up_at is not None
        submissions.append(
            DueSubmission(
                label=label,
                status=str(submission.status.value),
                follow_up_at=submission.follow_up_at,
            )
        )
    return DueItems(tasks=tasks, submissions=submissions)


def _due_label(value: datetime, today: date) -> str:
    # Gespeichert wird UTC (SQLite liefert naiv zurueck) - Anzeige in Berlin.
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    local = aware.astimezone(_BERLIN).date()
    if local < today:
        return f"ueberfaellig seit {local:%d.%m.%Y}"
    return "heute"


def build_digest(user: User, items: DueItems, *, now: datetime) -> tuple[str, str]:
    """(Betreff, Text) der Sammel-Mail. Nur sinnvoll fuer nicht leere Items."""
    today = berlin_today(now)
    total = len(items.tasks) + len(items.submissions)
    subject = f"Hermes: {total} {'Punkt' if total == 1 else 'Punkte'} heute faellig"
    greeting_name = user.display_name or user.email
    lines = [
        f"Guten Morgen {greeting_name},",
        "",
        f"das steht heute ({today:%d.%m.%Y}) bei dir an:",
    ]
    if items.tasks:
        lines += ["", f"Aufgaben ({len(items.tasks)}):"]
        lines += [f"- {task.title} ({_due_label(task.due_at, today)})" for task in items.tasks]
    if items.submissions:
        lines += ["", f"Prozesse mit faelliger Wiedervorlage ({len(items.submissions)}):"]
        lines += [
            f"- {sub.label} - Stufe {sub.status} ({_due_label(sub.follow_up_at, today)})"
            for sub in items.submissions
        ]
    lines += ["", "Diese Mail wird jeden Morgen automatisch aus Hermes erzeugt."]
    return subject, "\n".join(lines)


def send_due_reminders(
    session: Session,
    *,
    now: datetime | None = None,
    sender: Sender = send_mail,
    resolve_account: Callable[[User], MailAccount | None] | None = None,
) -> list[ReminderResult]:
    """Versendet pro aktivem Nutzer mit Faelligem EINE Mail an dessen eigene
    Adresse. Sendekonto: `User.default_send_account_id`, sonst globales
    `default_for_cv_out` (MailAccountService.resolve_send_account); ohne Konto
    wird der Nutzer uebersprungen und das protokolliert."""
    current = now or datetime.now(UTC)
    resolve = resolve_account or MailAccountService(session).resolve_send_account
    results: list[ReminderResult] = []
    users = session.scalars(select(User).where(User.is_active.is_(True)).order_by(User.email)).all()
    for user in users:
        try:
            items = collect_due_items(session, user, now=current)
            if items.is_empty:
                results.append(ReminderResult(user.id, user.email, "nothing_due"))
                continue
            account = resolve(user)
            if account is None:
                logger.warning("Kein Sendekonto fuer %s - Erinnerung uebersprungen", user.email)
                results.append(
                    ReminderResult(user.id, user.email, "no_account", "kein Sendekonto verfuegbar")
                )
                continue
            subject, body = build_digest(user, items, now=current)
            sender(
                session,
                account=account,
                to_address=user.email,
                to_name=user.display_name,
                subject=subject,
                body_text=body,
            )
            results.append(ReminderResult(user.id, user.email, "sent"))
        except Exception as exc:  # noqa: BLE001 - ein Nutzer darf die anderen nicht blockieren
            session.rollback()
            logger.warning("Erinnerung fuer %s fehlgeschlagen", user.email, exc_info=True)
            results.append(ReminderResult(user.id, user.email, "error", str(exc)))
    return results
