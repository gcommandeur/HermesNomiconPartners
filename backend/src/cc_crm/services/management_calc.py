# NOMICON: Ansicht "Gesamt" (Geschaeftsfuehrung) - nur in der Nomicon-Kopie.
"""Reine Rechenfunktionen der Ansicht "Gesamt": keine Datenbank, keine Uhr, handgerechnet testbar.

ANNAHME (im Bericht und in der Oberflaeche genannt): Die Marge der Ueberlassung je Stunde ist
`Verrechnungssatz - Stundenlohn x Arbeitgeber-Faktor`. Der Faktor ist der bereits einstellbare
Arbeitgeber-Faktor des Provisionsmodells (Standard 1,23); es gibt keine eigene Lohnberechnung,
keine Steuer- oder Sozialversicherungslogik."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

PERIOD_DAYS = {
    "week": 7,
    "month": 30,
    "quarter": 90,
}  # wie die KPI-Zeitraeume der Geschaeftsfuehrung
_CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def period_bounds(period: str, today: date) -> tuple[date, date]:
    """Rollierendes Fenster der letzten N Tage einschliesslich heute."""
    days = PERIOD_DAYS.get(period)
    if days is None:
        raise ValueError("period muss week, month oder quarter sein")
    return today - timedelta(days=days - 1), today


def margin_per_hour(
    billing_rate: Decimal, hourly_wage: Decimal, employer_factor: Decimal
) -> Decimal:
    return billing_rate - hourly_wage * employer_factor


def staffing_margin(
    hours: Decimal, billing_rate: Decimal, hourly_wage: Decimal, employer_factor: Decimal
) -> Decimal:
    """Marge freigegebener Stunden: Stunden x (Satz - Lohn x Faktor), auf Cent gerundet."""
    return money(hours * margin_per_hour(billing_rate, hourly_wage, employer_factor))


@dataclass(frozen=True)
class DirectItem:
    expected_fee: Decimal | None
    probability: Decimal | None  # 0 bis 1


@dataclass(frozen=True)
class DirectForecast:
    weighted: Decimal  # Summe Fee x Wahrscheinlichkeit, nur wo beides vorliegt
    without_probability: int  # Fee vorhanden, Wahrscheinlichkeit fehlt (nicht in `weighted`)
    without_fee: int  # Wahrscheinlichkeit oder nicht, aber keine Fee (nicht in `weighted`)


def direct_forecast(items: Iterable[DirectItem]) -> DirectForecast:
    """Prognose Direct = erwartete Fee x Abschlusswahrscheinlichkeit. Es wird nichts erfunden: wer
    eine der beiden Angaben nicht hat, fehlt in der Summe und wird gezaehlt."""
    weighted = Decimal("0")
    no_probability = 0
    no_fee = 0
    for item in items:
        if item.expected_fee is None:
            no_fee += 1
        elif item.probability is None:
            no_probability += 1
        else:
            weighted += item.expected_fee * item.probability
    return DirectForecast(money(weighted), no_probability, no_fee)


@dataclass(frozen=True)
class StaffingItem:
    margin_per_hour: Decimal | None  # None: Satz oder Lohn fehlt
    weekly_hours: Decimal | None
    planned_end: date | None
    max_end: date | None  # Hoechstueberlassungsdauer des Paares


@dataclass(frozen=True)
class StaffingForecast:
    margin: Decimal
    counted: int
    excluded: int  # fehlende Angaben (Satz, Lohn, Wochenstunden oder Ende)


def forecast_end(planned_end: date | None, max_end: date | None) -> date | None:
    """Geplantes Ende, nie ueber die Hoechstdauer hinaus; fehlt eines, gilt das andere."""
    candidates = [d for d in (planned_end, max_end) if d is not None]
    return min(candidates) if candidates else None


def remaining_weeks(end: date, today: date) -> Decimal:
    days = max((end - today).days, 0)
    return Decimal(days) / Decimal(7)


def staffing_forecast(items: Iterable[StaffingItem], today: date) -> StaffingForecast:
    """Prognose Ueberlassung = Marge je Stunde x Wochenstunden x Restwochen aktiver Einsaetze."""
    total = Decimal("0")
    counted = 0
    excluded = 0
    for item in items:
        end = forecast_end(item.planned_end, item.max_end)
        if item.margin_per_hour is None or item.weekly_hours is None or end is None:
            excluded += 1
            continue
        total += item.margin_per_hour * item.weekly_hours * remaining_weeks(end, today)
        counted += 1
    return StaffingForecast(money(total), counted, excluded)
