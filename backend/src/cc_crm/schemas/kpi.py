from typing import Literal

from pydantic import BaseModel, Field


class KpiPointRuleRead(BaseModel):
    stage: str
    points: int


class KpiPointRulesUpdate(BaseModel):
    # dict statt Liste - ein PUT setzt beliebig viele Stufen auf einmal,
    # unbekannte/fehlende Stufen bleiben unveraendert (siehe kpi_scoring.py::
    # set_point_rules).
    rules: dict[str, int] = Field(default_factory=dict)


class TeamMemberKpis(BaseModel):
    user_id: str
    display_name: str
    stages: dict[str, int]
    points: int
    # Ziel-Spalte bewusst vorbereitet, aber leer (Nutzer-Vorgabe: Soll-Werte
    # sind noch nicht definiert, NICHT raten) - immer null, bis ein
    # Folge-Auftrag ein echtes Zielwert-Feld einfuehrt.
    target: None = None


class TeamKpiOverview(BaseModel):
    period: str
    members: list[TeamMemberKpis]


class KpiRankingEntry(BaseModel):
    user_id: str
    display_name: str
    value: int


class KpiRankingResult(BaseModel):
    period: str
    metric: str
    entries: list[KpiRankingEntry]


class AppSettingsRead(BaseModel):
    kpi_ranking_metric: str
    kpi_ranking_period: Literal["day", "week"]


class AppSettingsUpdate(BaseModel):
    kpi_ranking_metric: str | None = None
    kpi_ranking_period: Literal["day", "week"] | None = None
