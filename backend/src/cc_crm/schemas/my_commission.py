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
