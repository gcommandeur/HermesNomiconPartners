from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AppSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Kleine Key-Value-Tabelle fuer admin-konfigurierbare, globale
    Einstellungen, die zu keiner bestehenden Tabelle gehoeren - erster
    Anwendungsfall: welche Kennzahl/Zeitraum das Live-Ranking-Widget auf dem
    Cockpit fuer ALLE Nutzer standardmaessig zeigt (Auftrag "Geschaeftsfueh-
    rer-Ansicht + KPI-Punkte-System + Live-Ranking", Nutzer-Vorgabe: "im
    Admin-Bereich anwaehlbar, welcher KPI ... angezeigt wird"). Bewusst eine
    generische Key-Value-Tabelle statt zwei weiterer Spalten auf
    KpiPointRule - diese Einstellung ist global (eine Zeile fuers ganze
    System), nicht pro Pipeline-Stufe, gehoert also nicht in eine Tabelle
    mit einer Zeile pro Stufe. `value` ist JSON, damit sich hier spaeter
    auch andere Einstellungstypen (Zahl, Liste, Objekt) ablegen lassen, ohne
    weitere Spalten/Migrationen.

    Bekannte Keys (siehe services/kpi_scoring.py):
    - "kpi_ranking_metric": str, einer von "points" oder einem STAGE_KEYS-
      Wert (siehe kpi_point_rule.py) - welche Zahl das Ranking-Widget zeigt.
    - "kpi_ranking_period": str, "day" oder "week" - Standard-Zeitraum,
      clientseitig im Widget trotzdem umschaltbar (Nutzer-Vorgabe)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
