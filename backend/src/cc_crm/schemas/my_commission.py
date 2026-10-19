# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Antwort "Meine Provision". Enthaelt bewusst weder Marge noch Firmenkosten noch Arbeitgeberkosten
und nie Daten anderer Mitarbeiter: sie beschreibt genau EINE Person."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class MyCommissionPerson(BaseModel):
    user_id: uuid.UUID
    display_name: str
    is_self: bool


class MyCommissionBand(BaseModel):
    label: str  # "Freigrenze", "Stufe 1" ...
    revenue: Decimal  # Umsatz in diesem Bereich
    rate: Decimal | None  # Prozent, bei der Freigrenze None
    commission: Decimal


class MyCommissionAssignment(BaseModel):
    assignment_id: uuid.UUID
    worker_name: str
    paid_months: int
    revenue: Decimal


class MyCommissionTimelineMonth(BaseModel):
    """Ein Monat im Zeitstrahl. Provision = Anteil an der Quartalsprovision (Stufen laufen mit),
    die drei Monate eines Quartals summieren sich exakt zu ihr."""

    year: int
    month: int
    quarter: int
    month_in_quarter: int
    revenue: Decimal
    commission: Decimal
    fixed_pay: Decimal
    bonus: Decimal
    total: Decimal
    is_current: bool
    is_provisional: bool  # laufender Monat: bis heute, Abrechnung zum Quartalsende


class MyCommissionProgress(BaseModel):
    is_top_rank: bool
    current_rank_label: str
    next_rank_label: str | None = None
    quarter_revenue: Decimal
    hurdle: Decimal | None = None  # Quartalsumsatz fuer die Befoerderung
    remaining: Decimal | None = None
    percent: Decimal | None = None
    days_to_quarter_end: int
    next_band_remaining: Decimal | None = None  # bis zur naechsten Provisionsstufe
    next_band_rate: Decimal | None = None  # Prozent ab dieser Stufe


class MyCommissionTimeline(BaseModel):
    user_id: uuid.UUID
    display_name: str
    rank_label: str | None = None
    year: int
    quarter: int
    months: list[MyCommissionTimelineMonth]  # letzte 12 Monate, der laufende zuletzt
    current_month: MyCommissionTimelineMonth
    quarter_revenue: Decimal  # laufendes Quartal bisher
    quarter_commission: Decimal
    quarter_fixed_pay: Decimal
    quarter_bonus: Decimal
    quarter_total: Decimal
    progress: MyCommissionProgress | None = None  # None ohne Rang


class MyCommissionRead(BaseModel):
    user_id: uuid.UUID
    display_name: str
    year: int
    quarter: int
    period_start: date
    period_end: date
    rank_key: str | None = None
    rank_label: str | None = None
    next_rank_label: str | None = None  # None bei der hoechsten Stufe
    is_top_rank: bool = False
    promotion_hurdle: Decimal | None = None  # Quartalsumsatz fuer die Befoerderung
    progress_percent: Decimal | None = None  # Umsatz / Huerde in Prozent (kann ueber 100 liegen)
    promotion_label: str | None = None  # Rang, auf den der Umsatz schon reicht (Admin setzt ihn)
    revenue: Decimal
    revenue_fees: Decimal
    revenue_staffing: Decimal
    bands: list[MyCommissionBand] = []
    explanation: list[str] = []
    commission: Decimal = Decimal("0.00")
    placement_deals: int = 0
    staffing_deals: int = 0
    bonus: Decimal = Decimal("0.00")
    fixed_pay: Decimal = Decimal("0.00")
    gross: Decimal = Decimal("0.00")
    staffing_assignments: list[MyCommissionAssignment] = []
    expected_revenue: Decimal  # Hinweis "erwartet": nicht bezahlt, NICHT in der Provision
