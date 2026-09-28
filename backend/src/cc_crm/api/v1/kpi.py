from typing import Annotated, Literal

from fastapi import APIRouter, Query

from cc_crm.api.dependencies import AdminUser, CurrentUser, DatabaseSession
from cc_crm.schemas.kpi import (
    AppSettingsRead,
    AppSettingsUpdate,
    KpiPointRuleRead,
    KpiPointRulesUpdate,
    KpiRankingEntry,
    KpiRankingResult,
    TeamKpiOverview,
    TeamMemberKpis,
)
from cc_crm.services.kpi_scoring import (
    STAGE_KEYS,
    get_app_settings,
    get_point_rules,
    kpi_ranking,
    set_app_settings,
    set_point_rules,
    team_kpi_overview,
)

router = APIRouter()


@router.get("/admin/kpi-point-rules", response_model=list[KpiPointRuleRead])
def get_kpi_point_rules(session: DatabaseSession, _admin: AdminUser) -> list[KpiPointRuleRead]:
    rules = get_point_rules(session)
    return [KpiPointRuleRead(stage=stage, points=rules[stage]) for stage in STAGE_KEYS]


@router.put("/admin/kpi-point-rules", response_model=list[KpiPointRuleRead])
def update_kpi_point_rules(
    payload: KpiPointRulesUpdate, session: DatabaseSession, _admin: AdminUser
) -> list[KpiPointRuleRead]:
    set_point_rules(session, payload.rules)
    rules = get_point_rules(session)
    return [KpiPointRuleRead(stage=stage, points=rules[stage]) for stage in STAGE_KEYS]


@router.get("/admin/app-settings", response_model=AppSettingsRead)
def get_admin_app_settings(session: DatabaseSession, _admin: AdminUser) -> AppSettingsRead:
    return AppSettingsRead.model_validate(get_app_settings(session))


@router.put("/admin/app-settings", response_model=AppSettingsRead)
def update_admin_app_settings(
    payload: AppSettingsUpdate, session: DatabaseSession, _admin: AdminUser
) -> AppSettingsRead:
    values = payload.model_dump(exclude_none=True)
    return AppSettingsRead.model_validate(set_app_settings(session, values))


@router.get("/team-kpis", response_model=TeamKpiOverview)
def get_team_kpis(
    session: DatabaseSession,
    _admin: AdminUser,
    period: Annotated[Literal["week", "month", "quarter"], Query()] = "week",
) -> TeamKpiOverview:
    """Geschaeftsfuehrer-Ansicht: eine Zeile pro Mitarbeiter mit den 6
    KPI-Stufen-Ist-Werten (gleiche Zahlen wie im eigenen Cockpit der
    jeweiligen Person) und der Gesamt-Punktzahl - admin-only
    (Rollenmodell-Entscheidung: keine neue Rolle, User.is_admin schaltet
    frei)."""
    members = team_kpi_overview(session, period)
    return TeamKpiOverview(
        period=period,
        members=[
            TeamMemberKpis(
                user_id=str(item["user_id"]),
                display_name=item["display_name"],
                stages=item["stages"],
                points=item["points"],
            )
            for item in members
        ],
    )


@router.get("/kpi-ranking", response_model=KpiRankingResult)
def get_kpi_ranking(
    session: DatabaseSession,
    _current_user: CurrentUser,
    period: Annotated[Literal["day", "week"] | None, Query()] = None,
    metric: str | None = None,
) -> KpiRankingResult:
    """Live-Ranking-Widget - sichtbar fuer ALLE Nutzer (Nutzer-Vorgabe:
    "Recruiter sollen sich untereinander sehen koennen"). period/metric
    optional: fehlt einer, greift die admin-konfigurierte Voreinstellung
    (app_settings), Tag/Woche bleibt im Widget selbst umschaltbar."""
    settings = get_app_settings(session)
    effective_period = period or settings["kpi_ranking_period"]
    effective_metric = metric or settings["kpi_ranking_metric"]
    entries = kpi_ranking(session, period=effective_period, metric=effective_metric)
    return KpiRankingResult(
        period=effective_period,
        metric=effective_metric,
        entries=[
            KpiRankingEntry(
                user_id=str(item["user_id"]),
                display_name=item["display_name"],
                value=item["value"],
            )
            for item in entries
        ],
    )
