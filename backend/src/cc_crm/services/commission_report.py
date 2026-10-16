# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Quartalsbericht des Provisionsmodells und Rangzuordnung (alles nur fuer Admins)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError, EntityNotFoundError
from cc_crm.models.commission import CommissionUserRank
from cc_crm.models.user import User
from cc_crm.schemas.commission import (
    CommissionConfigRead,
    CommissionConfigUpdate,
    CommissionReportRead,
    CommissionRevenueBasis,
    CommissionRowRead,
    CommissionTotalsRead,
    CommissionUnassignedRead,
    CommissionUserRankRead,
    CommissionUserRankUpdate,
)
from cc_crm.services import staffing_audit as audit
from cc_crm.services.commission_model import (
    CommissionConfig,
    ConfigError,
    RevenueBasis,
    Traffic,
    evaluate_quarter,
    margin,
    money,
    traffic_light,
)
from cc_crm.services.commission_revenue import quarter_bounds, quarter_revenue
from cc_crm.services.commission_settings import (
    from_json,
    load_config,
    save_config,
    to_json,
)

NOTICE = (
    "Annahmen, die mit der Excel 'Nomicon_Provisionsmodell' abzugleichen sind: gestaffelte "
    "Provision je Quartal auf den Umsatz oberhalb der Freigrenze, Kosten = (Fixgehalt + Provision) "
    "x Arbeitgeber-Faktor + Zusatzkosten, Befoerderung bei Erreichen der Schwelle 2 (Kaskade). "
    "Die Umsatzbasis ist einstellbar und noch zu bestaetigen."
)
CONFIG_ENTITY = "commission_config"
RANK_ENTITY = "commission_rank"
# feste Kennung fuer den (einzigen) Konfigurationseintrag im Audit-Log
CONFIG_ID = uuid.UUID("00000000-0000-4000-8000-00000000c0f1")


def current_quarter(today: date | None = None) -> tuple[int, int]:
    day = today or date.today()
    return day.year, (day.month - 1) // 3 + 1


def config_read(config: CommissionConfig) -> CommissionConfigRead:
    return CommissionConfigRead.model_validate({**to_json(config), "notice": NOTICE})


def update_config(
    session: Session, payload: CommissionConfigUpdate, actor: User
) -> CommissionConfigRead:
    try:
        config = from_json(payload.model_dump(mode="json"))
        before = to_json(load_config(session))
        saved = save_config(session, config)
    except ConfigError as error:
        raise BusinessRuleError(str(error)) from error
    audit.log_event(
        session,
        CONFIG_ENTITY,
        CONFIG_ID,
        "config_changed",
        actor.email,
        {"changed": to_json(saved) != before},
    )
    session.commit()
    return config_read(saved)


def _name(user: User) -> str:
    return user.display_name or user.email


def build_report(
    session: Session, year: int, quarter: int, config: CommissionConfig | None = None
) -> CommissionReportRead:
    cfg = config or load_config(session)
    start, end = quarter_bounds(year, quarter)
    revenue = quarter_revenue(session, year, quarter, cfg.revenue_basis)
    ranked = session.execute(
        select(User, CommissionUserRank.rank_key)
        .join(CommissionUserRank, CommissionUserRank.user_id == User.id)
        .where(User.is_active.is_(True))
        .order_by(User.display_name, User.email)
    ).all()
    keys = {r.key for r in cfg.ranks}
    rows: list[CommissionRowRead] = []
    for user, rank_key in ranked:
        if rank_key not in keys:
            continue  # Rang inzwischen aus dem Modell entfernt: erscheint unter "ohne Rang"
        data = revenue.by_user.get(user.id)
        fees = data.fees if data else Decimal("0")
        staffing = data.staffing if data else Decimal("0")
        result = evaluate_quarter(fees + staffing, rank_key, cfg)
        rank = cfg.rank(rank_key)
        promotion = cfg.rank(result.promotion_to) if result.promotion_to else None
        rows.append(
            CommissionRowRead(
                user_id=user.id,
                display_name=_name(user),
                rank_key=rank_key,
                rank_label=rank.label,
                revenue_fees=money(fees),
                revenue_staffing=money(staffing),
                revenue=money(result.revenue),
                commission=result.breakdown.commission,
                band1_revenue=money(result.breakdown.band1_revenue),
                band2_revenue=money(result.breakdown.band2_revenue),
                band3_revenue=money(result.breakdown.band3_revenue),
                band1_commission=result.breakdown.band1_commission,
                band2_commission=result.breakdown.band2_commission,
                band3_commission=result.breakdown.band3_commission,
                fixed_pay=result.fixed_pay,
                placement_deals=result.placement_deals,
                staffing_deals=result.staffing_deals,
                bonus=result.bonus,
                gross=result.gross,
                employer_cost=result.employer_cost,
                margin=result.margin,
                margin_percent=result.margin_percent,
                break_even_revenue=result.break_even_revenue,
                target_revenue=result.target_revenue,
                traffic=result.traffic,
                promotion_hurdle=(
                    rank.threshold2 if cfg.index(rank_key) < len(cfg.ranks) - 1 else None
                ),
                promotion_to_key=promotion.key if promotion else None,
                promotion_to_label=promotion.label if promotion else None,
            )
        )
    ranked_ids = {row.user_id for row in rows}
    unassigned: list[CommissionUnassignedRead] = []
    names = {
        user.id: _name(user)
        for user in session.scalars(select(User).where(User.id.in_(list(revenue.by_user))))
    }
    for user_id, data in revenue.by_user.items():
        if user_id in ranked_ids or data.total == 0:
            continue
        unassigned.append(
            CommissionUnassignedRead(
                user_id=user_id,
                display_name=names.get(user_id, "Unbekannt"),
                revenue_fees=money(data.fees),
                revenue_staffing=money(data.staffing),
                revenue=money(data.total),
            )
        )
    unassigned.sort(key=lambda item: item.display_name)

    total_revenue = sum((row.revenue for row in rows), Decimal("0"))
    total_cost = sum((row.employer_cost for row in rows), Decimal("0"))
    amount, percent = margin(total_revenue, total_cost)
    totals = CommissionTotalsRead(
        revenue=total_revenue,
        commission=sum((row.commission for row in rows), Decimal("0")),
        fixed_pay=sum((row.fixed_pay for row in rows), Decimal("0")),
        employer_cost=total_cost,
        margin=amount,
        margin_percent=percent,
        traffic=traffic_light(total_revenue, total_cost, cfg.general) if rows else Traffic.GREEN,
    )
    basis: RevenueBasis = cfg.revenue_basis
    return CommissionReportRead(
        year=year,
        quarter=quarter,
        period_start=start,
        period_end=end,
        target_margin=cfg.general.target_margin,
        rows=rows,
        unassigned=unassigned,
        totals=totals,
        revenue_basis=CommissionRevenueBasis(
            placement_fees=basis.placement_fees,  # type: ignore[arg-type]
            include_staffing=basis.include_staffing,
            staffing=basis.staffing,  # type: ignore[arg-type]
        ),
        notice=NOTICE,
    )


def list_user_ranks(session: Session) -> list[CommissionUserRankRead]:
    users = session.scalars(
        select(User).where(User.is_active.is_(True)).order_by(User.display_name, User.email)
    ).all()
    assigned = {row.user_id: row for row in session.scalars(select(CommissionUserRank)).all()}
    return [
        CommissionUserRankRead(
            user_id=user.id,
            display_name=_name(user),
            email=user.email,
            rank_key=assigned[user.id].rank_key if user.id in assigned else None,
            effective_from=assigned[user.id].effective_from if user.id in assigned else None,
        )
        for user in users
    ]


def set_user_rank(
    session: Session, user_id: uuid.UUID, payload: CommissionUserRankUpdate, actor: User
) -> CommissionUserRankRead:
    user = session.get(User, user_id)
    if user is None:
        raise EntityNotFoundError("Nutzer nicht gefunden")
    config = load_config(session)
    if payload.rank_key is not None and payload.rank_key not in {r.key for r in config.ranks}:
        raise BusinessRuleError("Unbekannter Rang.")
    row = session.scalar(select(CommissionUserRank).where(CommissionUserRank.user_id == user_id))
    old_key = row.rank_key if row else None
    if payload.rank_key is None:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(
            CommissionUserRank(
                user_id=user_id,
                rank_key=payload.rank_key,
                effective_from=payload.effective_from,
                updated_by=actor.email,
            )
        )
    else:
        row.rank_key = payload.rank_key
        row.effective_from = payload.effective_from
        row.updated_by = actor.email
    audit.log_event(
        session,
        RANK_ENTITY,
        user_id,
        "rank_changed",
        actor.email,
        {"from": old_key, "to": payload.rank_key},
    )
    session.commit()
    for item in list_user_ranks(session):
        if item.user_id == user_id:
            return item
    return CommissionUserRankRead(
        user_id=user.id,
        display_name=_name(user),
        email=user.email,
        rank_key=None,
        effective_from=None,
    )
