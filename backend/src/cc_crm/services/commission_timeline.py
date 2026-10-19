# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Zeitstrahl "Meine Provision": Monatswerte, laufendes Quartal und Fortschritt zur nächsten Rolle.

Abgerechnet wird weiter JE QUARTAL (Rechenkern und Beförderungsregel unverändert). Damit man sieht,
was im Monat verdient wurde, wird der Quartalswert auf die Monate verteilt:

* Provision bis Monatsende = Provision aus dem KUMULIERTEN Quartalsumsatz bis zu diesem Monat.
* Monatswert = Wert bis Monatsende minus Wert bis Vormonatsende im selben Quartal. So wandern die
  Stufen (Freigrenze, Satz 1 bis 3) korrekt mit, und die drei Monatswerte summieren sich EXAKT zur
  Quartalsprovision (Teleskopsumme).
* Fixgehalt: je Monat ein Drittel des Quartalsfixums (der dritte Monat nimmt den Cent-Rest, damit
  die Summe exakt stimmt). Bonus: im Monat des Zahldatums des Deals, wie im bestehenden Modell
  ("erst, wenn er im Quartal erreicht ist"). Umsatz nach Zahldatum.
* Der laufende Monat rechnet bis heute und ist vorläufig; die Abrechnung erfolgt zum Quartalsende.

Annahme: Für alle Monate gilt der AKTUELLE Rang (der Rang-Verlauf wird nicht gespeichert).
Die Antwort beschreibt genau eine Person und enthält weder Marge noch Firmenkosten."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.commission import CommissionUserRank
from cc_crm.models.user import User
from cc_crm.schemas.my_commission import (
    MyCommissionProgress,
    MyCommissionTimeline,
    MyCommissionTimelineMonth,
)
from cc_crm.services.commission_model import (
    CommissionConfig,
    RankConfig,
    bonus_for_quarter,
    commission_for_quarter,
    fixed_pay_for_quarter,
    money,
)
from cc_crm.services.commission_revenue import month_bounds, period_revenue, quarter_bounds
from cc_crm.services.commission_settings import load_config
from cc_crm.services.my_commission import _name, resolve_target

MONTHS_SHOWN = 12
ZERO = Decimal("0.00")


def last_months(today: date, count: int = MONTHS_SHOWN) -> list[tuple[int, int]]:
    """(Jahr, Monat) der letzten `count` Monate, der laufende zuletzt."""
    index = today.year * 12 + today.month - 1
    indices = range(index - count + 1, index + 1)
    return [(i // 12, i % 12 + 1) for i in indices]


def _months_from_quarter_start(first: tuple[int, int], today: date) -> list[tuple[int, int]]:
    """Alle Monate vom Quartalsbeginn des ersten angezeigten Monats bis zum laufenden Monat."""
    year, month = first
    quarter_first_month = 3 * ((month - 1) // 3) + 1
    start_index = year * 12 + quarter_first_month - 1
    end_index = today.year * 12 + today.month - 1
    return [(i // 12, i % 12 + 1) for i in range(start_index, end_index + 1)]


def monthly_fixed(rank: RankConfig, month_in_quarter: int) -> Decimal:
    """Ein Drittel des Quartalsfixums; der dritte Monat nimmt den Cent-Rest (Summe exakt)."""
    quarter_fixed = money(fixed_pay_for_quarter(rank))
    third = money(quarter_fixed / 3)
    return third if month_in_quarter < 3 else quarter_fixed - 2 * third


def month_values(
    config: CommissionConfig,
    rank: RankConfig | None,
    revenues: list[tuple[int, int, Decimal, int, int]],
    today: date,
) -> list[MyCommissionTimelineMonth]:
    """Reine Rechnung: `revenues` = (Jahr, Monat, Umsatz, Vermittlungs-Deals, Überlassungs-Deals) in
    zeitlicher Reihenfolge, lückenlos ab einem Quartalsbeginn. Liefert alle Monate mit Werten."""
    result: list[MyCommissionTimelineMonth] = []
    cumulative = Decimal("0")
    previous_commission = ZERO
    for year, month, revenue, placement, staffing in revenues:
        in_quarter = (month - 1) % 3 + 1
        if in_quarter == 1:
            cumulative, previous_commission = Decimal("0"), ZERO
        cumulative += revenue
        if rank is not None:
            through = commission_for_quarter(cumulative, rank, config.general).commission
            commission = through - previous_commission
            previous_commission = through
            fixed = monthly_fixed(rank, in_quarter)
            bonus = bonus_for_quarter(config.general, placement, staffing)
        else:
            commission = fixed = bonus = ZERO
        result.append(
            MyCommissionTimelineMonth(
                year=year,
                month=month,
                quarter=(month - 1) // 3 + 1,
                month_in_quarter=in_quarter,
                revenue=money(revenue),
                commission=commission,
                fixed_pay=fixed,
                bonus=bonus,
                total=money(commission + fixed + bonus),
                is_current=(year, month) == (today.year, today.month),
                is_provisional=(year, month) == (today.year, today.month),
            )
        )
    return result


def progress_for(
    config: CommissionConfig, rank: RankConfig, quarter_revenue_so_far: Decimal, today: date
) -> MyCommissionProgress:
    position = config.index(rank.key)
    is_top = position == len(config.ranks) - 1
    _, quarter_end = quarter_bounds(today.year, (today.month - 1) // 3 + 1)
    revenue = money(quarter_revenue_so_far)
    boundaries = [
        (config.general.commission_free_base, rank.rate1),
        (rank.threshold1, rank.rate2),
        (rank.threshold2, rank.rate3),
    ]
    next_band = next(((b, r) for b, r in boundaries if b > revenue), None)
    hurdle = None if is_top else rank.threshold2
    return MyCommissionProgress(
        is_top_rank=is_top,
        current_rank_label=rank.label,
        next_rank_label=None if is_top else config.ranks[position + 1].label,
        quarter_revenue=revenue,
        hurdle=hurdle,
        remaining=None if hurdle is None else money(max(hurdle - revenue, Decimal("0"))),
        percent=(
            None
            if not hurdle
            else min(Decimal("100"), (revenue / hurdle * 100).quantize(Decimal("0.1")))
        ),
        days_to_quarter_end=(quarter_end - today).days,
        next_band_remaining=None if next_band is None else money(next_band[0] - revenue),
        next_band_rate=None if next_band is None else next_band[1],
    )


def build_timeline(
    session: Session,
    viewer: User,
    user_id: uuid.UUID | None,
    today: date | None = None,
) -> MyCommissionTimeline:
    day = today or date.today()
    target = resolve_target(session, viewer, user_id)  # fremd UND nicht vorhanden: 404
    config = load_config(session)
    rank_key = session.scalar(
        select(CommissionUserRank.rank_key).where(CommissionUserRank.user_id == target.id)
    )
    rank = config.rank(rank_key) if rank_key in {r.key for r in config.ranks} else None
    shown = last_months(day)
    revenues: list[tuple[int, int, Decimal, int, int]] = []
    for year, month in _months_from_quarter_start(shown[0], day):
        start, end = month_bounds(year, month)
        data = period_revenue(session, start, min(end, day), config.revenue_basis).by_user.get(
            target.id
        )
        revenues.append(
            (
                year,
                month,
                data.total if data else Decimal("0"),
                data.placement_deals if data else 0,
                data.staffing_deals if data else 0,
            )
        )
    values = month_values(config, rank, revenues, day)
    by_key = {(v.year, v.month): v for v in values}
    months = [by_key[key] for key in shown]
    current = by_key[(day.year, day.month)]
    quarter = current.quarter
    so_far = [v for v in values if (v.year, v.quarter) == (day.year, quarter)]
    quarter_revenue = sum((v.revenue for v in so_far), Decimal("0"))
    return MyCommissionTimeline(
        user_id=target.id,
        display_name=_name(target),
        rank_label=rank.label if rank else None,
        year=day.year,
        quarter=quarter,
        months=months,
        current_month=current,
        quarter_revenue=money(quarter_revenue),
        quarter_commission=sum((v.commission for v in so_far), ZERO),
        quarter_fixed_pay=sum((v.fixed_pay for v in so_far), ZERO),
        quarter_bonus=sum((v.bonus for v in so_far), ZERO),
        quarter_total=sum((v.total for v in so_far), ZERO),
        progress=progress_for(config, rank, quarter_revenue, day) if rank else None,
    )
