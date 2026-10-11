# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Speicherung des Provisionsmodells (Saetze, Schwellen, Gehaelter, Umsatzbasis) als JSON in
`app_settings` (Schluessel `commission_config`). Fehlt der Eintrag oder ist er unbrauchbar, gelten
die Startwerte aus der Excel (commission_model.DEFAULT_CONFIG)."""

from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.app_setting import AppSetting
from cc_crm.services.commission_model import (
    DEFAULT_CONFIG,
    CommissionConfig,
    ConfigError,
    GeneralConfig,
    RankConfig,
    RevenueBasis,
    validate_config,
)

KEY = "commission_config"
_PLACEMENT_BASIS = ("paid", "issued")
_STAFFING_BASIS = ("issued", "paid")


def to_json(config: CommissionConfig) -> dict[str, Any]:
    general = config.general
    return {
        "general": {
            "commission_free_base": str(general.commission_free_base),
            "employer_factor": str(general.employer_factor),
            "extra_cost_monthly": str(general.extra_cost_monthly),
            "fee_rate_on_target_salary": str(general.fee_rate_on_target_salary),
            "min_fee": str(general.min_fee),
            "target_margin": str(general.target_margin),
        },
        "ranks": [
            {
                "key": r.key,
                "label": r.label,
                "fixed_monthly": str(r.fixed_monthly),
                "rate1": str(r.rate1),
                "threshold1": str(r.threshold1),
                "rate2": str(r.rate2),
                "threshold2": str(r.threshold2),
                "rate3": str(r.rate3),
            }
            for r in config.ranks
        ],
        "revenue_basis": {
            "placement_fees": config.revenue_basis.placement_fees,
            "include_staffing": config.revenue_basis.include_staffing,
            "staffing": config.revenue_basis.staffing,
        },
    }


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise ConfigError("Ungueltige Zahl in der Konfiguration.") from error


def from_json(data: Any) -> CommissionConfig:
    """Wirft ConfigError bei unbrauchbaren Daten."""
    try:
        general = GeneralConfig(**{k: _dec(v) for k, v in data["general"].items()})
        ranks = tuple(
            RankConfig(
                key=str(r["key"]),
                label=str(r["label"]),
                fixed_monthly=_dec(r["fixed_monthly"]),
                rate1=_dec(r["rate1"]),
                threshold1=_dec(r["threshold1"]),
                rate2=_dec(r["rate2"]),
                threshold2=_dec(r["threshold2"]),
                rate3=_dec(r["rate3"]),
            )
            for r in data["ranks"]
        )
        basis_data = data["revenue_basis"]
        basis = RevenueBasis(
            placement_fees=str(basis_data["placement_fees"]),
            include_staffing=bool(basis_data["include_staffing"]),
            staffing=str(basis_data["staffing"]),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ConfigError("Die gespeicherte Konfiguration ist unvollstaendig.") from error
    if basis.placement_fees not in _PLACEMENT_BASIS or basis.staffing not in _STAFFING_BASIS:
        raise ConfigError("Ungueltige Umsatzbasis.")
    return validate_config(CommissionConfig(general, ranks, basis))


def load_config(session: Session) -> CommissionConfig:
    row = session.scalar(select(AppSetting).where(AppSetting.key == KEY))
    if row is None:
        return DEFAULT_CONFIG
    try:
        return from_json(row.value)
    except ConfigError:
        return DEFAULT_CONFIG


def save_config(session: Session, config: CommissionConfig) -> CommissionConfig:
    validate_config(config)
    if config.revenue_basis.placement_fees not in _PLACEMENT_BASIS:
        raise ConfigError("Ungueltige Umsatzbasis fuer Vermittlungshonorare.")
    if config.revenue_basis.staffing not in _STAFFING_BASIS:
        raise ConfigError("Ungueltige Umsatzbasis fuer Ueberlassungsrechnungen.")
    row = session.scalar(select(AppSetting).where(AppSetting.key == KEY))
    if row is None:
        session.add(AppSetting(key=KEY, value=to_json(config)))
    else:
        row.value = to_json(config)
    session.commit()
    return config
