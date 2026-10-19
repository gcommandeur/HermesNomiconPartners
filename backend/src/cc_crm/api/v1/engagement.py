# NOMICON: gemeinsamer Kandidatenstatus - nur in der Nomicon-Kopie.
"""Status "wo ist der Kandidat bereits im Austausch", Präferenzen und Konflikt-Einstellung."""

import uuid

from fastapi import APIRouter

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.core.errors import EntityNotFoundError
from cc_crm.models.candidate import Candidate
from cc_crm.schemas.engagement import (
    CandidateEngagementRead,
    EngagementPrefsUpdate,
    EngagementSettingsRead,
    EngagementSettingsUpdate,
    EngagementSummaryRequest,
)
from cc_crm.services import engagement_status as service

router = APIRouter()


@router.get("/candidates/{candidate_id}/engagement", response_model=CandidateEngagementRead)
def get_candidate_engagement(
    candidate_id: uuid.UUID, session: DatabaseSession, current_user: CurrentUser
) -> CandidateEngagementRead:
    if session.get(Candidate, candidate_id) is None:
        raise EntityNotFoundError("Kandidat nicht gefunden")
    return service.summarize(session, current_user, [candidate_id])[candidate_id]


@router.patch("/candidates/{candidate_id}/engagement-prefs", response_model=CandidateEngagementRead)
def update_engagement_prefs(
    candidate_id: uuid.UUID,
    payload: EngagementPrefsUpdate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> CandidateEngagementRead:
    service.update_prefs(
        session, current_user, candidate_id, payload.open_for_direct, payload.open_for_staffing
    )
    return service.summarize(session, current_user, [candidate_id])[candidate_id]


@router.post("/engagement/summary", response_model=list[CandidateEngagementRead])
def engagement_summary(
    payload: EngagementSummaryRequest, session: DatabaseSession, current_user: CurrentUser
) -> list[CandidateEngagementRead]:
    """Sammelabfrage für ganze Listenseiten (eine Abfrage statt einer je Kandidat)."""
    summaries = service.summarize(session, current_user, payload.candidate_ids)
    return list(summaries.values())


@router.get("/admin/engagement-settings", response_model=EngagementSettingsRead)
def get_engagement_settings(session: DatabaseSession, _admin: AdminUser) -> EngagementSettingsRead:
    return EngagementSettingsRead.model_validate(
        {"conflict_mode": service.get_conflict_mode(session)}
    )


@router.put("/admin/engagement-settings", response_model=EngagementSettingsRead)
def put_engagement_settings(
    payload: EngagementSettingsUpdate, session: DatabaseSession, admin: AdminUser
) -> EngagementSettingsRead:
    mode = service.save_conflict_mode(session, payload.conflict_mode, admin)
    return EngagementSettingsRead.model_validate({"conflict_mode": mode})
