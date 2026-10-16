# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Stundenzettel je Einsatz und Zeitraum, Einreichen und Freigabe durch den Kunden per Link.

Freigabe-Link: ein zufaelliges Token (`secrets.token_urlsafe(32)`, 256 Bit). In der Datenbank liegt
NUR der SHA-256-Hash (`approval_token_hash`), der Klartext steht einmalig in der Antwort von
`submit` und im Link. Das Token läuft ab (`TOKEN_VALID_DAYS`), ist nur EINMAL nutzbar (Freigabe
oder Ablehnung entwertet es) und gilt nur für genau diesen Stundenzettel. Wer den Zettel erneut
einreicht ("Link neu erzeugen"), entwertet den alten Link. Der Kunde sieht über den Link nur die
nötigen Daten (siehe schemas.staffing.PublicTimesheetRead)."""

import hashlib
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, CcCrmError, ConflictError, EntityNotFoundError
from cc_crm.models.staffing import (
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingTimesheet,
    StaffingTimesheetEntry,
    StaffingTimesheetStatus,
)
from cc_crm.models.user import User
from cc_crm.repositories.staffing import StaffingAssignmentRepository
from cc_crm.schemas.staffing import (
    PublicTimesheetRead,
    StaffingTimesheetCreate,
    StaffingTimesheetEntriesUpdate,
    StaffingTimesheetEntryRead,
    StaffingTimesheetRead,
    StaffingTimesheetSubmitResult,
)
from cc_crm.services import staffing_audit as audit

TOKEN_VALID_DAYS = 14  # Gueltigkeit des Freigabelinks
MAX_PERIOD_DAYS = 62  # laengster Zeitraum eines Stundenzettels (ein Monat plus Puffer)
APPROVAL_PATH_PREFIX = "/stundenzettel/"
_EDITABLE = (StaffingTimesheetStatus.OPEN, StaffingTimesheetStatus.REJECTED)


class TimesheetLinkNotFoundError(CcCrmError):
    """Unbekanntes Token (nie vergeben oder erfunden)."""


class TimesheetLinkExpiredError(CcCrmError):
    """Token abgelaufen, schon verwendet oder durch einen neuen Link ersetzt."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _entries_read(entries: list[StaffingTimesheetEntry]) -> list[StaffingTimesheetEntryRead]:
    ordered = sorted(entries, key=lambda e: e.work_date)
    return [StaffingTimesheetEntryRead.model_validate(e) for e in ordered]


class StaffingTimesheetService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.assignments = StaffingAssignmentRepository(session)

    # --- Lesen --------------------------------------------------------------------------------

    def _entries(self, timesheet_id: uuid.UUID) -> list[StaffingTimesheetEntry]:
        return list(
            self.session.scalars(
                select(StaffingTimesheetEntry).where(
                    StaffingTimesheetEntry.timesheet_id == timesheet_id
                )
            ).all()
        )

    def _get(self, timesheet_id: uuid.UUID) -> StaffingTimesheet:
        sheet = self.session.get(StaffingTimesheet, timesheet_id)
        if sheet is None:
            raise EntityNotFoundError("Stundenzettel nicht gefunden")
        return sheet

    def read(self, sheet: StaffingTimesheet) -> StaffingTimesheetRead:
        row = self.assignments.row(sheet.assignment_id)
        assert row is not None
        entries = self._entries(sheet.id)
        link_valid = (
            sheet.status == StaffingTimesheetStatus.SUBMITTED
            and sheet.approval_token_hash is not None
            and sheet.approval_token_used_at is None
        )
        return StaffingTimesheetRead(
            id=sheet.id,
            created_at=sheet.created_at,
            updated_at=sheet.updated_at,
            assignment_id=sheet.assignment_id,
            worker_name=row.worker_name,
            client_name=row.client_name,
            period_start=sheet.period_start,
            period_end=sheet.period_end,
            status=sheet.status,
            submitted_at=sheet.submitted_at,
            decided_at=sheet.decided_at,
            decided_by_name=sheet.decided_by_name,
            rejection_reason=sheet.rejection_reason,
            approval_link_expires_at=sheet.approval_token_expires_at if link_valid else None,
            total_hours=sum((e.hours for e in entries), Decimal("0")),
            entries=_entries_read(entries),
        )

    def get_read(self, timesheet_id: uuid.UUID) -> StaffingTimesheetRead:
        return self.read(self._get(timesheet_id))

    def list_for_assignment(self, assignment_id: uuid.UUID) -> list[StaffingTimesheetRead]:
        sheets = self.session.scalars(
            select(StaffingTimesheet)
            .where(StaffingTimesheet.assignment_id == assignment_id)
            .order_by(StaffingTimesheet.period_start.desc())
        ).all()
        return [self.read(sheet) for sheet in sheets]

    # --- Schreiben (intern) -------------------------------------------------------------------

    def _assignment(self, assignment_id: uuid.UUID) -> StaffingAssignment:
        row = self.assignments.row(assignment_id)
        if row is None:
            raise EntityNotFoundError("Einsatz nicht gefunden")
        return row.assignment

    @staticmethod
    def _span(assignment: StaffingAssignment) -> tuple[date, date | None]:
        end = assignment.actual_end_date or assignment.planned_end_date
        return assignment.start_date, end

    def create(
        self, assignment_id: uuid.UUID, payload: StaffingTimesheetCreate, actor: User
    ) -> StaffingTimesheetRead:
        assignment = self._assignment(assignment_id)
        if assignment.status not in (
            StaffingAssignmentStatus.ACTIVE,
            StaffingAssignmentStatus.ENDED,
        ):
            raise BusinessRuleError(
                "Stundenzettel gibt es nur für aktive oder beendete Einsätze."
            )
        if (payload.period_end - payload.period_start).days + 1 > MAX_PERIOD_DAYS:
            raise BusinessRuleError(f"Ein Stundenzettel umfasst höchstens {MAX_PERIOD_DAYS} Tage.")
        start, end = self._span(assignment)
        if payload.period_end < start or (end is not None and payload.period_start > end):
            raise BusinessRuleError("Der Zeitraum liegt ausserhalb des Einsatzes.")
        for other in self.session.scalars(
            select(StaffingTimesheet).where(StaffingTimesheet.assignment_id == assignment_id)
        ):
            if (
                payload.period_start <= other.period_end
                and payload.period_end >= other.period_start
            ):
                raise ConflictError(
                    "Für diesen Zeitraum gibt es schon einen Stundenzettel "
                    f"({other.period_start:%d.%m.%Y} bis {other.period_end:%d.%m.%Y})."
                )
        sheet = StaffingTimesheet(
            assignment_id=assignment_id,
            period_start=payload.period_start,
            period_end=payload.period_end,
        )
        self.session.add(sheet)
        self.session.flush()
        audit.log_created(
            self.session,
            audit.ENTITY_TIMESHEET,
            sheet.id,
            {"assignment_id": assignment_id, **payload.model_dump()},
            actor.email,
        )
        self.session.commit()
        return self.read(sheet)

    def set_entries(
        self, timesheet_id: uuid.UUID, payload: StaffingTimesheetEntriesUpdate, actor: User
    ) -> StaffingTimesheetRead:
        sheet = self._get(timesheet_id)
        if sheet.status not in _EDITABLE:
            raise BusinessRuleError(
                "Eingereichte oder freigegebene Stundenzettel sind nicht mehr änderbar."
            )
        assignment = self._assignment(sheet.assignment_id)
        span_start, span_end = self._span(assignment)
        seen: set[date] = set()
        for entry in payload.entries:
            day = entry.work_date
            if not sheet.period_start <= day <= sheet.period_end:
                raise BusinessRuleError(f"{day:%d.%m.%Y} liegt ausserhalb des Zeitraums.")
            if day < span_start or (span_end is not None and day > span_end):
                raise BusinessRuleError(f"{day:%d.%m.%Y} liegt ausserhalb des Einsatzes.")
            if day in seen:
                raise BusinessRuleError(f"{day:%d.%m.%Y} ist doppelt eingetragen.")
            seen.add(day)
        self.session.execute(
            delete(StaffingTimesheetEntry).where(StaffingTimesheetEntry.timesheet_id == sheet.id)
        )
        for entry in payload.entries:
            self.session.add(
                StaffingTimesheetEntry(
                    timesheet_id=sheet.id,
                    work_date=entry.work_date,
                    hours=entry.hours,
                    break_minutes=entry.break_minutes,
                )
            )
        reopened = sheet.status == StaffingTimesheetStatus.REJECTED
        if reopened:
            # Nach einer Ablehnung beginnt die Bearbeitung von vorn; die Begruendung bleibt im
            # Audit-Log, der Zettel ist wieder offen.
            sheet.status = StaffingTimesheetStatus.OPEN
            sheet.rejection_reason = None
            sheet.decided_at = None
            sheet.decided_by_name = None
        audit.log_event(
            self.session,
            audit.ENTITY_TIMESHEET,
            sheet.id,
            "entries_set",
            actor.email,
            {"days": len(payload.entries), "reopened": reopened},
        )
        self.session.commit()
        return self.read(sheet)

    def submit(
        self, timesheet_id: uuid.UUID, actor: User, now: datetime | None = None
    ) -> StaffingTimesheetSubmitResult:
        """Einreichen und Freigabelink erzeugen. Bei einem schon eingereichten Zettel wird der
        Link neu erzeugt (der alte wird ungültig) - für abgelaufene oder verlorene Links."""
        sheet = self._get(timesheet_id)
        if sheet.status in (StaffingTimesheetStatus.APPROVED,):
            raise BusinessRuleError("Dieser Stundenzettel ist bereits freigegeben.")
        if not self._entries(sheet.id):
            raise BusinessRuleError("Ein leerer Stundenzettel kann nicht eingereicht werden.")
        moment = now or datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        resubmitted = sheet.status == StaffingTimesheetStatus.SUBMITTED
        sheet.approval_token_hash = hash_token(token)
        sheet.approval_token_expires_at = moment + timedelta(days=TOKEN_VALID_DAYS)
        sheet.approval_token_used_at = None
        sheet.status = StaffingTimesheetStatus.SUBMITTED
        sheet.submitted_at = moment
        audit.log_event(
            self.session,
            audit.ENTITY_TIMESHEET,
            sheet.id,
            "link_renewed" if resubmitted else "submitted",
            actor.email,
        )
        self.session.commit()
        return StaffingTimesheetSubmitResult(
            timesheet=self.read(sheet),
            approval_path=f"{APPROVAL_PATH_PREFIX}{token}",
            expires_at=sheet.approval_token_expires_at,
        )

    # --- Öffentlich (Kunde, ohne Login) ------------------------------------------------------

    def _by_token(self, token: str, now: datetime) -> StaffingTimesheet:
        sheet = self.session.scalar(
            select(StaffingTimesheet).where(
                StaffingTimesheet.approval_token_hash == hash_token(token)
            )
        )
        if sheet is None:
            raise TimesheetLinkNotFoundError()
        if (
            sheet.approval_token_used_at is not None
            or sheet.status != StaffingTimesheetStatus.SUBMITTED
            or sheet.approval_token_expires_at is None
            or _aware(sheet.approval_token_expires_at) < now
        ):
            raise TimesheetLinkExpiredError()
        return sheet

    def public_view(self, token: str, now: datetime | None = None) -> PublicTimesheetRead:
        moment = now or datetime.now(UTC)
        sheet = self._by_token(token, moment)
        full = self.read(sheet)
        return PublicTimesheetRead(
            worker_name=full.worker_name,
            client_name=full.client_name,
            period_start=full.period_start,
            period_end=full.period_end,
            status=full.status,
            total_hours=full.total_hours,
            entries=full.entries,
            decided_at=None,
            decided_by_name=None,
            rejection_reason=None,
            expires_at=sheet.approval_token_expires_at,
        )

    def decide(
        self,
        token: str,
        *,
        approve: bool,
        approver_name: str,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> PublicTimesheetRead:
        moment = now or datetime.now(UTC)
        sheet = self._by_token(token, moment)
        name = approver_name.strip()
        sheet.status = (
            StaffingTimesheetStatus.APPROVED if approve else StaffingTimesheetStatus.REJECTED
        )
        sheet.decided_at = moment
        sheet.decided_by_name = name
        sheet.rejection_reason = None if approve else (reason or "").strip()
        sheet.approval_token_used_at = moment  # Link ist verbraucht
        audit.log_event(
            self.session,
            audit.ENTITY_TIMESHEET,
            sheet.id,
            "approved" if approve else "rejected",
            f"Kunde: {name}",
            None if approve else {"reason": sheet.rejection_reason},
        )
        self.session.commit()
        full = self.read(sheet)
        return PublicTimesheetRead(
            worker_name=full.worker_name,
            client_name=full.client_name,
            period_start=full.period_start,
            period_end=full.period_end,
            status=full.status,
            total_hours=full.total_hours,
            entries=full.entries,
            decided_at=full.decided_at,
            decided_by_name=full.decided_by_name,
            rejection_reason=full.rejection_reason,
            expires_at=None,
        )
