# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Schemas des Provisionsmodells (nur Admins, siehe api/v1/commission.py)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from cc_crm.services.commission_model import Traffic

Percent = Field(ge=0, le=100)
Money = Field(ge=0, le=Decimal("100000000"))


class CommissionRankConfig(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=80)
    fixed_monthly: Decimal = Money
    rate1: Decimal = Percent
    threshold1: Decimal = Money
    rate2: Decimal = Percent
    threshold2: Decimal = Money  # zugleich Befoerderungshuerde
    rate3: Decimal = Percent


class CommissionGeneralConfig(BaseModel):
    commission_free_base: Decimal = Money
    employer_factor: Decimal = Field(ge=1, le=3)
    extra_cost_monthly: Decimal = Money
    fee_rate_on_target_salary: Decimal = Percent
    min_fee: Decimal = Money
    target_margin: Decimal = Field(ge=0, lt=95)


class CommissionRevenueBasis(BaseModel):
    placement_fees: Literal["paid", "issued"]
    include_staffing: bool
    staffing: Literal["issued", "paid"]


class CommissionConfigUpdate(BaseModel):
    general: CommissionGeneralConfig
    ranks: list[CommissionRankConfig] = Field(min_length=1, max_length=20)
    revenue_basis: CommissionRevenueBasis


class CommissionConfigRead(CommissionConfigUpdate):
    notice: str


class CommissionRowRead(BaseModel):
    user_id: uuid.UUID
    display_name: str
    rank_key: str
    rank_label: str
    revenue_fees: Decimal
    revenue_staffing: Decimal
    revenue: Decimal
    commission: Decimal
    band1_revenue: Decimal
    band2_revenue: Decimal
    band3_revenue: Decimal
    band1_commission: Decimal
    band2_commission: Decimal
    band3_commission: Decimal
    fixed_pay: Decimal
    employer_cost: Decimal
    margin: Decimal
    margin_percent: Decimal | None
    break_even_revenue: Decimal
    target_revenue: Decimal
    traffic: Traffic
    promotion_hurdle: Decimal | None  # Quartalsumsatz fuer die Befoerderung (None: hoechster Rang)
    promotion_to_key: str | None
    promotion_to_label: str | None


class CommissionUnassignedRead(BaseModel):
    """Mitarbeiter mit Umsatz, denen noch kein Rang zugeordnet ist."""

    user_id: uuid.UUID
    display_name: str
    revenue_fees: Decimal
    revenue_staffing: Decimal
    revenue: Decimal


class CommissionTotalsRead(BaseModel):
    revenue: Decimal
    commission: Decimal
    fixed_pay: Decimal
    employer_cost: Decimal
    margin: Decimal
    margin_percent: Decimal | None
    traffic: Traffic


class CommissionReportRead(BaseModel):
    year: int
    quarter: int
    period_start: date
    period_end: date
    target_margin: Decimal
    rows: list[CommissionRowRead]
    unassigned: list[CommissionUnassignedRead]
    totals: CommissionTotalsRead
    revenue_basis: CommissionRevenueBasis
    notice: str


class CommissionUserRankRead(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str
    rank_key: str | None
    effective_from: date | None


class CommissionUserRankUpdate(BaseModel):
    rank_key: str | None = Field(default=None, max_length=40)  # None = Rang entfernen
    effective_from: date | None = None
