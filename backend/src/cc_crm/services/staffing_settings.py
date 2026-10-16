# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Einstellbare rechtliche Werte der Überlassung (Tabelle `app_settings`, nur Admins).

Die Standardwerte stehen als benannte Konstanten in services/staffing_deadlines.py. HINWEIS (auch
in der Oberflaeche): kein Rechtsrat - mit Fachanwalt oder Verband bestätigen; Tarifverträge
können abweichen."""

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.app_setting import AppSetting
from cc_crm.services.staffing_deadlines import DeadlineConfig

KEY_PREFIX = "staffing_"
# DeadlineConfig-Feld -> app_settings-Schluessel
FIELDS: dict[str, str] = {
    "max_months": "staffing_max_assignment_months",
    "equal_pay_months": "staffing_equal_pay_months",
    "reset_gap_months": "staffing_reset_gap_months",
    "yellow_days": "staffing_yellow_days",
    "red_days": "staffing_red_days",
}


def load_config(session: Session) -> DeadlineConfig:
    """Gespeicherte Werte, fehlende oder ungültige fallen auf den Standard zurück."""
    rows = {
        row.key: row.value
        for row in session.scalars(
            select(AppSetting).where(AppSetting.key.in_(list(FIELDS.values())))
        ).all()
    }
    defaults = asdict(DeadlineConfig())
    values: dict[str, int] = {}
    for field, key in FIELDS.items():
        raw = rows.get(key)
        values[field] = (
            raw
            if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0
            else defaults[field]
        )
    try:
        return _validated(DeadlineConfig(**values))
    except BusinessRuleError:
        return DeadlineConfig()


def _validated(config: DeadlineConfig) -> DeadlineConfig:
    for field, value in asdict(config).items():
        if not isinstance(value, int) or value <= 0:
            raise BusinessRuleError(f"Wert '{field}' muss eine positive ganze Zahl sein.")
    if config.equal_pay_months >= config.max_months:
        raise BusinessRuleError("Equal Pay muss vor der Höchstüberlassungsdauer beginnen.")
    if config.red_days > config.yellow_days:
        raise BusinessRuleError("Die rote Schwelle darf nicht größer als die gelbe sein.")
    return config


def save_config(session: Session, config: DeadlineConfig) -> DeadlineConfig:
    _validated(config)
    existing = {
        row.key: row
        for row in session.scalars(
            select(AppSetting).where(AppSetting.key.in_(list(FIELDS.values())))
        ).all()
    }
    for field, key in FIELDS.items():
        value = asdict(config)[field]
        if key in existing:
            existing[key].value = value
        else:
            session.add(AppSetting(key=key, value=value))
    session.commit()
    return config
