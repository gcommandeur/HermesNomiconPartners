# NOMICON: gemeinsamer Kandidatenstatus - nur in der Nomicon-Kopie.
"""Wo ist ein Kandidat bereits im Austausch? Abgeleitet aus Prozessen (Direct) und Einsätzen
(Überlassung), nichts doppelt gespeichert.

Sichtbarkeit (Standardentscheidung, siehe docs/ANSICHTEN.md): Kanal, Stufe, zustaendiger Mitarbeiter
und Datum sieht jeder Angemeldete; Kanzleiname und IDs nur, wer Zugriff auf den Prozess bzw. Einsatz
hat (Owner-Scope, Freigabe, Admin). Lohn und Marge kommen hier nie vor."""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date

from sqlalchemy import and_, exists, not_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from cc_crm.api.dependencies import process_owner_scope, shared_submission_ids
from cc_crm.core.errors import BusinessRuleError, ConflictError, EntityNotFoundError
from cc_crm.models.app_setting import AppSetting
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.engagement import CandidateEngagementPrefs
from cc_crm.models.enums import SubmissionStatus
from cc_crm.models.recruiting import AuditLog, Placement
from cc_crm.models.staffing import StaffingAssignment, StaffingAssignmentStatus, StaffingWorker
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.schemas.engagement import (
    CandidateEngagementRead,
    EngagementItemRead,
)

ACTIVE_PROCESS_STATUSES = (
    SubmissionStatus.QUALIFICATION_CALL,
    SubmissionStatus.CV_IN,
    SubmissionStatus.CV_OUT,
    SubmissionStatus.INTERVIEW,
    SubmissionStatus.OFFER,
)
ACTIVE_ASSIGNMENT_STATUSES = (StaffingAssignmentStatus.PLANNED, StaffingAssignmentStatus.ACTIVE)
OPENNESS = ("yes", "no", "unknown")
CONFLICT_MODE_KEY = "engagement_conflict_mode"
STAGE_LABELS = {
    "qualification_call": "Quali Call",
    "cv_in": "CV in",
    "cv_out": "CV out",
    "interview": "Interview",
    "offer": "Offer",
    "placement": "vermittelt",
    "planned": "geplant",
    "active": "aktiv",
}


def _active_process_condition() -> ColumnElement[bool]:
    """Aktiver Prozess ODER vermittelt (ein Placement bleibt auch nach dem Archivieren bestehen)."""
    return or_(
        and_(
            CandidateSubmission.status.in_(ACTIVE_PROCESS_STATUSES),
            CandidateSubmission.archived_at.is_(None),
            CandidateSubmission.closed_at.is_(None),
        ),
        CandidateSubmission.status == SubmissionStatus.PLACEMENT,
    )


def derive_status(items: Sequence[EngagementItemRead]) -> str:
    """frei / im_direct / im_einsatz / beides / vermittelt. Eine Vermittlung geht vor."""
    if any(item.kind == "placement" for item in items):
        return "vermittelt"
    direct = any(item.channel == "direct" for item in items)
    staffing = any(item.channel == "staffing" for item in items)
    if direct and staffing:
        return "beides"
    if direct:
        return "im_direct"
    if staffing:
        return "im_einsatz"
    return "frei"


def summarize(
    session: Session, user: User, candidate_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, CandidateEngagementRead]:
    """Zusammenfassung für viele Kandidaten per Sammelabfrage (keine Abfrage je Kandidat)."""
    ids = list(dict.fromkeys(candidate_ids))
    result: dict[uuid.UUID, CandidateEngagementRead] = {}
    if not ids:
        return result

    prefs = {
        row.candidate_id: row
        for row in session.scalars(
            select(CandidateEngagementPrefs).where(CandidateEngagementPrefs.candidate_id.in_(ids))
        ).all()
    }
    process_rows = session.execute(
        select(CandidateSubmission, ClientCompany.name, Placement.start_date)
        .outerjoin(ClientCompany, ClientCompany.id == CandidateSubmission.client_company_id)
        .outerjoin(Placement, Placement.submission_id == CandidateSubmission.id)
        .where(CandidateSubmission.candidate_id.in_(ids), _active_process_condition())
    ).all()
    assignment_rows = session.execute(
        select(StaffingAssignment, StaffingWorker.candidate_id, ClientCompany.name)
        .join(StaffingWorker, StaffingWorker.id == StaffingAssignment.worker_id)
        .join(ClientCompany, ClientCompany.id == StaffingAssignment.client_company_id)
        .where(
            StaffingWorker.candidate_id.in_(ids),
            StaffingAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
    ).all()

    owner_ids = {row[0].owner_user_id for row in process_rows} | {
        row[0].owner_user_id for row in assignment_rows
    }
    owner_ids.discard(None)
    names: dict[uuid.UUID, str] = {}
    if owner_ids:
        for owner in session.scalars(select(User).where(User.id.in_(owner_ids))).all():
            names[owner.id] = owner.display_name or owner.email

    scope = process_owner_scope(user, session)  # Prozesse und Einsätze: gleiche Regel
    shared = set(shared_submission_ids(user, session))

    items: dict[uuid.UUID, list[EngagementItemRead]] = defaultdict(list)
    for submission, client_name, placement_start in process_rows:
        sees = scope is None or submission.owner_user_id in scope or submission.id in shared
        placed = submission.status == SubmissionStatus.PLACEMENT
        items[submission.candidate_id].append(
            EngagementItemRead(
                channel="direct",
                kind="placement" if placed else "process",
                stage=submission.status.value,
                owner_name=names.get(submission.owner_user_id)
                if submission.owner_user_id
                else None,
                since=placement_start
                if placed and placement_start
                else submission.last_activity_at.date(),
                until=None,
                details_visible=sees,
                client_name=client_name,
                entity_id=submission.id if sees else None,
            )
        )
    for assignment, candidate_id, client_name in assignment_rows:
        sees = scope is None or assignment.owner_user_id in scope
        items[candidate_id].append(
            EngagementItemRead(
                channel="staffing",
                kind="assignment",
                stage=assignment.status.value,
                owner_name=names.get(assignment.owner_user_id)
                if assignment.owner_user_id
                else None,
                since=assignment.start_date,
                until=assignment.actual_end_date or assignment.planned_end_date,
                details_visible=sees,
                client_name=client_name,
                entity_id=assignment.id if sees else None,
            )
        )

    for candidate_id in ids:
        row = prefs.get(candidate_id)
        own = sorted(items.get(candidate_id, []), key=lambda item: (item.channel, str(item.since)))
        result[candidate_id] = CandidateEngagementRead.model_validate(
            {
                "candidate_id": candidate_id,
                "status": derive_status(own),
                "open_for_direct": row.open_for_direct if row else "unknown",
                "open_for_staffing": row.open_for_staffing if row else "unknown",
                "items": own,
            }
        )
    return result


def describe(item: EngagementItemRead) -> str:
    """Kurztext mit den für alle sichtbaren Angaben (Kanal, Stufe, Kunde, Mitarbeiter, Datum)."""
    channel = "Direct" if item.channel == "direct" else "AÜ"
    stage = STAGE_LABELS.get(item.stage, item.stage)
    who = f" ({item.owner_name})" if item.owner_name else ""
    since = f" seit {item.since.strftime('%d.%m.%Y')}" if isinstance(item.since, date) else ""
    client = f" bei {item.client_name}" if item.client_name else ""
    return f"{channel}: {stage}{client}{who}{since}"


# --- Praeferenz ---------------------------------------------------------------------------------


def update_prefs(
    session: Session,
    user: User,
    candidate_id: uuid.UUID,
    open_for_direct: str | None,
    open_for_staffing: str | None,
) -> None:
    if session.get(Candidate, candidate_id) is None:
        raise EntityNotFoundError("Kandidat nicht gefunden")
    for value in (open_for_direct, open_for_staffing):
        if value is not None and value not in OPENNESS:
            raise BusinessRuleError("Erlaubt sind ja, nein oder nicht geklärt.")
    row = session.scalar(
        select(CandidateEngagementPrefs).where(
            CandidateEngagementPrefs.candidate_id == candidate_id
        )
    )
    old = {
        "open_for_direct": row.open_for_direct if row else "unknown",
        "open_for_staffing": row.open_for_staffing if row else "unknown",
    }
    if row is None:
        row = CandidateEngagementPrefs(candidate_id=candidate_id)
        session.add(row)
    row.open_for_direct = open_for_direct or old["open_for_direct"]
    row.open_for_staffing = open_for_staffing or old["open_for_staffing"]
    row.updated_by_user_id = user.id
    new = {"open_for_direct": row.open_for_direct, "open_for_staffing": row.open_for_staffing}
    if new != old:
        session.add(
            AuditLog(
                entity_type="candidate_engagement_prefs",
                entity_id=candidate_id,
                action="updated",
                changed_by=user.email,
                old_values=old,
                new_values=new,
            )
        )
    session.commit()


# --- Filter für die Kandidatenliste -------------------------------------------------------------


def candidate_filters(kind: str) -> list[ColumnElement[bool]]:
    """Zusatzbedingungen für die Kandidatenliste. "Frei" heisst: nicht ausdrücklich "nein" und
    aktuell nicht im Prozess/Einsatz des Kanals; "Im Austausch": irgendein aktiver Prozess,
    eine Vermittlung oder ein geplanter/aktiver Einsatz."""
    in_direct = exists().where(
        CandidateSubmission.candidate_id == Candidate.id, _active_process_condition()
    )
    in_staffing = exists().where(
        StaffingWorker.candidate_id == Candidate.id,
        StaffingAssignment.worker_id == StaffingWorker.id,
        StaffingAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
    )

    def declined(column: str) -> ColumnElement[bool]:
        return exists().where(
            CandidateEngagementPrefs.candidate_id == Candidate.id,
            getattr(CandidateEngagementPrefs, column) == "no",
        )

    if kind == "free_direct":
        return [not_(in_direct), not_(declined("open_for_direct"))]
    if kind == "free_staffing":
        return [not_(in_staffing), not_(declined("open_for_staffing"))]
    if kind == "engaged":
        return [or_(in_direct, in_staffing)]
    raise BusinessRuleError("Unbekannter Filter.")


# --- Konflikt beim Anlegen ---------------------------------------------------------------------


def get_conflict_mode(session: Session) -> str:
    row = session.scalar(select(AppSetting).where(AppSetting.key == CONFLICT_MODE_KEY))
    return row.value if row is not None and row.value in ("warn", "block") else "warn"


def save_conflict_mode(session: Session, mode: str, actor: User) -> str:
    if mode not in ("warn", "block"):
        raise BusinessRuleError("Erlaubt sind warnen oder sperren.")
    old = get_conflict_mode(session)
    row = session.scalar(select(AppSetting).where(AppSetting.key == CONFLICT_MODE_KEY))
    if row is None:
        session.add(AppSetting(key=CONFLICT_MODE_KEY, value=mode))
    else:
        row.value = mode
    if old != mode:
        session.add(
            AuditLog(
                entity_type="engagement_settings",
                entity_id=actor.id,
                action="updated",
                changed_by=actor.email,
                old_values={"conflict_mode": old},
                new_values={"conflict_mode": mode},
            )
        )
    session.commit()
    return mode


def _conflicting(
    items: Sequence[EngagementItemRead], channel: str, user: User
) -> list[EngagementItemRead]:
    """Gebunden heisst: Vermittlung, anderer Kanal oder (gleicher Kanal) von einem Kollegen
    betreut. Eigene parallele Prozesse bei anderen Kanzleien sind Alltag und lösen nichts aus."""
    own_name = user.display_name or user.email
    result = []
    for item in items:
        if item.kind == "placement" or item.channel != channel or item.owner_name != own_name:
            result.append(item)
    return result


def ensure_no_conflict(
    session: Session, user: User, candidate_id: uuid.UUID, channel: str, confirmed: bool
) -> None:
    """Vor dem Anlegen eines Prozesses (`direct`) oder Einsatzes (`staffing`). Modus "warn":
    409 mit Hinweistext, ein zweiter Aufruf mit Bestätigung geht durch. Modus "block": 422."""
    summary = summarize(session, user, [candidate_id])[candidate_id]
    items = _conflicting(summary.items, channel, user)
    if not items:
        return
    text = (
        "Dieser Kandidat ist bereits im Austausch: " + "; ".join(describe(i) for i in items) + "."
    )
    if get_conflict_mode(session) == "block":
        raise BusinessRuleError(text + " Anlegen ist gesperrt (Einstellung der Geschäftsführung).")
    if not confirmed:
        raise ConflictError(text + " Trotzdem anlegen?")


def require_channel_open(session: Session, candidate_id: uuid.UUID, channel: str) -> None:
    """Der Kandidat muss für den Kanal freigegeben sein (beim Kandidaten angekreuzt).

    Überlassung braucht ein ausdrückliches "ja" (Einwilligung); Direct ist nur bei "nein"
    gesperrt, "nicht geklärt" reicht, damit bestehende Kandidaten vermittelt werden können."""
    row = session.scalar(
        select(CandidateEngagementPrefs).where(
            CandidateEngagementPrefs.candidate_id == candidate_id
        )
    )
    if channel == "staffing":
        if row is None or row.open_for_staffing != "yes":
            raise BusinessRuleError(
                "Dieser Kandidat ist nicht für Überlassung freigegeben. "
                "Bitte beim Kandidaten „Überlassung“ ankreuzen."
            )
    elif row is not None and row.open_for_direct == "no":
        raise BusinessRuleError(
            "Dieser Kandidat ist nicht für Direct freigegeben. "
            "Bitte beim Kandidaten „Direct“ ankreuzen."
        )
