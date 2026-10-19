# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Ansicht "Meine Provision": Rang, Fortschritt zur Befoerderung und nachvollziehbare Rechnung fuer
EINE Person. Rechte: jeder sieht sich selbst, Teamleiter zusaetzlich ihr Team (`manager_id`), Admins
alle. Fremde und nicht vorhandene Personen liefern dasselbe 404. Die Antwort enthaelt weder Marge
noch Firmenkosten (das bleibt im Admin-Bericht)."""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import EntityNotFoundError
from cc_crm.models.commission import CommissionUserRank
from cc_crm.models.user import User
from cc_crm.schemas.my_commission import (
    MyCommissionAssignment,
    MyCommissionBand,
    MyCommissionPerson,
    MyCommissionRead,
)
from cc_crm.services.commission_deals import expected_revenue, staffing_breakdown
from cc_crm.services.commission_model import CommissionConfig, evaluate_quarter, money
from cc_crm.services.commission_revenue import quarter_bounds, quarter_revenue
from cc_crm.services.commission_settings import load_config

NOT_FOUND = "Mitarbeiter nicht gefunden"


def _name(user: User) -> str:
    return user.display_name or user.email


def euro(value: Decimal) -> str:
    """12345.5 -> "12.345,50 €" (deutsche Schreibweise, ohne Nachkommastellen bei ganzen Zahlen)."""
    whole = value == value.to_integral_value()
    text = f"{value:,.0f}" if whole else f"{value:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def percent(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.replace(".", ",") + " %"


def visible_people(session: Session, viewer: User) -> list[User]:
    """Personen, deren Provision `viewer` ansehen darf (er selbst zuerst)."""
    if viewer.is_admin:
        others = session.scalars(
            select(User).where(User.is_active.is_(True), User.id != viewer.id)
        ).all()
    elif viewer.is_team_lead:
        others = session.scalars(
            select(User).where(User.manager_id == viewer.id, User.is_active.is_(True))
        ).all()
    else:
        others = []
    return [viewer, *sorted(others, key=lambda user: _name(user).lower())]


def people(session: Session, viewer: User) -> list[MyCommissionPerson]:
    return [
        MyCommissionPerson(user_id=u.id, display_name=_name(u), is_self=u.id == viewer.id)
        for u in visible_people(session, viewer)
    ]


def resolve_target(session: Session, viewer: User, user_id: uuid.UUID | None) -> User:
    if user_id is None or user_id == viewer.id:
        return viewer
    for person in visible_people(session, viewer):
        if person.id == user_id:
            return person
    raise EntityNotFoundError(NOT_FOUND)  # fremd UND nicht vorhanden: dasselbe 404


def _explain(
    config: CommissionConfig, rank_key: str, revenue: Decimal
) -> tuple[list[MyCommissionBand], list[str]]:
    rank = config.rank(rank_key)
    free = config.general.commission_free_base
    result = evaluate_quarter(revenue, rank_key, config).breakdown
    bands = [
        MyCommissionBand(
            label="Freigrenze",
            revenue=money(min(revenue, free)),
            rate=None,
            commission=Decimal("0.00"),
        ),
        MyCommissionBand(
            label="Stufe 1",
            revenue=money(result.band1_revenue),
            rate=rank.rate1,
            commission=result.band1_commission,
        ),
        MyCommissionBand(
            label="Stufe 2",
            revenue=money(result.band2_revenue),
            rate=rank.rate2,
            commission=result.band2_commission,
        ),
        MyCommissionBand(
            label="Stufe 3",
            revenue=money(result.band3_revenue),
            rate=rank.rate3,
            commission=result.band3_commission,
        ),
    ]
    lines = [
        f"{euro(band.revenue)} frei (Freigrenze {euro(free)})"
        if band.rate is None
        else f"{euro(band.revenue)} zu {percent(band.rate)} = {euro(band.commission)}"
        for band in bands
        if band.revenue > 0
    ]
    return bands, lines or ["Noch kein Umsatz in diesem Quartal."]


def build(
    session: Session, viewer: User, user_id: uuid.UUID | None, year: int, quarter: int
) -> MyCommissionRead:
    target = resolve_target(session, viewer, user_id)
    config = load_config(session)
    start, end = quarter_bounds(year, quarter)
    revenue = quarter_revenue(session, year, quarter, config.revenue_basis)
    data = revenue.by_user.get(target.id)
    fees = data.fees if data else Decimal("0")
    staffing = data.staffing if data else Decimal("0")
    total = fees + staffing
    assignments = [
        MyCommissionAssignment(
            assignment_id=item.assignment_id,
            worker_name=item.worker_name,
            paid_months=item.paid_months,
            revenue=item.revenue,
        )
        for item in staffing_breakdown(session, target.id, start, end)
    ]
    rank_key = session.scalar(
        select(CommissionUserRank.rank_key).where(CommissionUserRank.user_id == target.id)
    )
    keys = {r.key for r in config.ranks}
    placement_deals = data.placement_deals if data else 0
    staffing_deals = data.staffing_deals if data else 0
    base = MyCommissionRead(
        user_id=target.id,
        display_name=_name(target),
        year=year,
        quarter=quarter,
        period_start=start,
        period_end=end,
        revenue=money(total),
        revenue_fees=money(fees),
        revenue_staffing=money(staffing),
        placement_deals=placement_deals,
        staffing_deals=staffing_deals,
        staffing_assignments=assignments,
        expected_revenue=expected_revenue(session, target.id, end),
    )
    if rank_key not in keys:  # noch kein (oder ein entfernter) Rang: nur der Umsatz
        base.explanation = [
            "Dir ist noch kein Rang zugewiesen – die Provision wird nach der Zuweisung berechnet."
        ]
        return base
    result = evaluate_quarter(total, rank_key, config, placement_deals, staffing_deals)
    rank = config.rank(rank_key)
    position = config.index(rank_key)
    is_top = position == len(config.ranks) - 1
    hurdle = None if is_top else rank.threshold2
    bands, explanation = _explain(config, rank_key, total)
    progress = None
    if hurdle:
        progress = (total / hurdle * 100).quantize(Decimal("0.1"))
    return base.model_copy(
        update={
            "rank_key": rank.key,
            "rank_label": rank.label,
            "next_rank_label": None if is_top else config.ranks[position + 1].label,
            "is_top_rank": is_top,
            "promotion_hurdle": hurdle,
            "progress_percent": progress,
            "promotion_label": (
                config.rank(result.promotion_to).label if result.promotion_to else None
            ),
            "bands": bands,
            "explanation": explanation,
            "commission": result.breakdown.commission,
            "bonus": result.bonus,
            "fixed_pay": result.fixed_pay,
            "gross": result.gross,
        }
    )
