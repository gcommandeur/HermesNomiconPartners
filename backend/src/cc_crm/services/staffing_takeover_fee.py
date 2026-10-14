# NOMICON: Uebernahme-Fee gestaffelt nach Einsatzdauer - nur in der Nomicon-Kopie.
"""Staffel der Uebernahme-Fee: je laenger der Einsatz bis zur Uebernahme gedauert hat, desto kleiner
der Anteil des Vermittlungshonorars (in Prozent des vollen Honorars der Kanzlei bzw. des Kunden).

Die Staffel ist EINSTELLBAR (Tabelle `app_settings`, Schluessel `staffing_takeover_fee_tiers`, nur
Admins). Die Startwerte unten sind PLATZHALTER, nicht abgestimmt - der Nutzer muss sie bestaetigen
bzw. durch die vertraglich vereinbarte Staffel ersetzen. Kein Rechtsrat."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.app_setting import AppSetting
from cc_crm.models.recruiting import AuditLog

KEY = "staffing_takeover_fee_tiers"
HUNDRED = Decimal("100")


@dataclass(frozen=True)
class FeeTier:
    up_to_months: int | None  # bis einschliesslich N volle Monate Einsatz; None = darueber hinaus
    percent_of_fee: Decimal  # Anteil des vollen Honorars, 0 bis 100


# PLATZHALTER - mit dem Nutzer zu klaeren
DEFAULT_TIERS: tuple[FeeTier, ...] = (
    FeeTier(3, Decimal("100")),
    FeeTier(6, Decimal("75")),
    FeeTier(9, Decimal("50")),
    FeeTier(12, Decimal("25")),
    FeeTier(None, Decimal("0")),
)


def months_between(start: date, end: date) -> int:
    """Volle Kalendermonate zwischen Einsatzbeginn und Uebernahme (nie negativ)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def tier_percent(months: int, tiers: tuple[FeeTier, ...] | list[FeeTier]) -> Decimal:
    """Anteil des vollen Honorars fuer einen Einsatz von `months` vollen Monaten."""
    for tier in tiers:
        if tier.up_to_months is None or months <= tier.up_to_months:
            return tier.percent_of_fee
    return tiers[-1].percent_of_fee if tiers else HUNDRED


def validate_tiers(tiers: list[FeeTier]) -> None:
    if not tiers:
        raise BusinessRuleError("Mindestens eine Stufe ist nötig.")
    previous = -1
    for index, tier in enumerate(tiers):
        last = index == len(tiers) - 1
        if not Decimal("0") <= tier.percent_of_fee <= HUNDRED:
            raise BusinessRuleError("Der Anteil muss zwischen 0 und 100 Prozent liegen.")
        if last:
            if tier.up_to_months is not None:
                raise BusinessRuleError(
                    "Die letzte Stufe gilt für alle längeren Einsätze (ohne Monatsgrenze)."
                )
        else:
            if tier.up_to_months is None or tier.up_to_months <= previous:
                raise BusinessRuleError("Die Monatsgrenzen müssen aufsteigen.")
            previous = tier.up_to_months


def _to_json(tiers: list[FeeTier]) -> list[dict[str, Any]]:
    return [
        {"up_to_months": t.up_to_months, "percent_of_fee": str(t.percent_of_fee)} for t in tiers
    ]


def load_tiers(session: Session) -> list[FeeTier]:
    row = session.scalar(select(AppSetting).where(AppSetting.key == KEY))
    if row is not None and isinstance(row.value, list):
        try:
            tiers = [
                FeeTier(
                    None if item["up_to_months"] is None else int(item["up_to_months"]),
                    Decimal(str(item["percent_of_fee"])),
                )
                for item in row.value
            ]
            validate_tiers(tiers)
            return tiers
        except (KeyError, TypeError, ValueError, BusinessRuleError, ArithmeticError):
            pass
    return list(DEFAULT_TIERS)


def save_tiers(
    session: Session, tiers: list[FeeTier], actor_email: str, actor_id: Any
) -> list[FeeTier]:
    validate_tiers(tiers)
    old = load_tiers(session)
    row = session.scalar(select(AppSetting).where(AppSetting.key == KEY))
    if row is None:
        session.add(AppSetting(key=KEY, value=_to_json(tiers)))
    else:
        row.value = _to_json(tiers)
    session.add(
        AuditLog(
            entity_type="staffing_takeover_fee_tiers",
            entity_id=actor_id,
            action="updated",
            changed_by=actor_email,
            old_values={"tiers": _to_json(old)},
            new_values={"tiers": _to_json(tiers)},
        )
    )
    session.commit()
    return tiers
