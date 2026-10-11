# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Fristen der Arbeitnehmerueberlassung als REINE Funktionen (keine Datenbank, keine Uhr).

Fachliche Grundlage (Stand: Annahmen aus dem Nutzerauftrag, KEIN Rechtsrat - mit Fachanwalt oder
Verband bestaetigen, Tarifvertraege koennen abweichen):
- Hoechstueberlassungsdauer: 18 Monate je Paar (Leiharbeitnehmer, Kunde).
- Equal Pay (gleiches Entgelt wie die Stammbelegschaft) ab dem 10. Monat, d.h. nach 9 Monaten.
- Eine Unterbrechung LAENGER als 3 Monate setzt den Zaehler zurueck; eine kuerzere (oder genau
  3 Monate) fuehrt die Zeiten zusammen.

Alle Werte stehen in `DeadlineConfig` (Standardwerte hier, einstellbar ueber app_settings, siehe
services/staffing_settings.py) - nichts davon ist im Rechenkern hart verdrahtet.

Rechenmodell: Gezaehlt werden die Einsatztage (Vereinigung ueberlappender Einsaetze), Luecken
zaehlen nicht mit. "N Monate" sind dabei die Kalendertage, die N Monate ab Kettenbeginn lang sind
(`add_months(start, N) - start`). Ohne Luecke endet die Hoechstdauer damit am Tag vor
`add_months(Kettenbeginn, 18)`; jede Luecke verschiebt die Frist um ihre Laenge nach hinten.
Monatsarithmetik schneidet am Monatsende ab (31.8. + 6 Monate = 28./29.2.)."""

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

# Benannte Standardwerte (Nutzervorgabe 2026-10-11) - einstellbar, nicht hartcodiert verwenden.
DEFAULT_MAX_ASSIGNMENT_MONTHS = 18  # Hoechstueberlassungsdauer
DEFAULT_EQUAL_PAY_MONTHS = 9  # Equal Pay gilt ab dem Folgetag nach 9 Monaten
DEFAULT_RESET_GAP_MONTHS = 3  # Unterbrechung laenger als 3 Monate setzt den Zaehler zurueck
DEFAULT_YELLOW_DAYS = 60  # Ampel gelb: weniger als 60 Tage Restlaufzeit
DEFAULT_RED_DAYS = 30  # Ampel rot: weniger als 30 Tage oder ueberschritten


@dataclass(frozen=True)
class DeadlineConfig:
    max_months: int = DEFAULT_MAX_ASSIGNMENT_MONTHS
    equal_pay_months: int = DEFAULT_EQUAL_PAY_MONTHS
    reset_gap_months: int = DEFAULT_RESET_GAP_MONTHS
    yellow_days: int = DEFAULT_YELLOW_DAYS
    red_days: int = DEFAULT_RED_DAYS


class Traffic(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass(frozen=True)
class Span:
    """Ein Einsatz als Zeitraum (beide Tage eingeschlossen). `end=None`: laeuft noch (bis heute
    und darueber hinaus)."""

    start: date
    end: date | None = None


@dataclass(frozen=True)
class DeadlineResult:
    # False: kein laufender oder fortsetzbarer Zaehler (z.B. keine Einsaetze oder die letzte
    # Unterbrechung ist schon laenger als die Grenze) - dann sind alle Daten None, Ampel gruen.
    has_chain: bool
    chain_start: date | None
    elapsed_months: int  # bisherige Dauer (Einsatztage bis heute) in vollen Monaten ...
    elapsed_days: int  # ... plus Resttage
    counted_days: int  # bisherige Einsatztage insgesamt
    equal_pay_from: date | None  # erster Tag, ab dem Equal Pay gilt
    equal_pay_reached: bool
    max_end_date: date | None  # letzter zulaessiger Einsatztag
    days_remaining: int | None  # max_end_date - heute (negativ = ueberschritten)
    exceeded: bool
    traffic: Traffic


NO_CHAIN = DeadlineResult(
    has_chain=False,
    chain_start=None,
    elapsed_months=0,
    elapsed_days=0,
    counted_days=0,
    equal_pay_from=None,
    equal_pay_reached=False,
    max_end_date=None,
    days_remaining=None,
    exceeded=False,
    traffic=Traffic.GREEN,
)


def add_months(value: date, months: int) -> date:
    """Monate addieren, Tag am Monatsende abschneiden (31.1. + 1 Monat = 28./29.2.)."""
    index = value.year * 12 + (value.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def full_months_between(start: date, end: date) -> tuple[int, int]:
    """(volle Monate, Resttage) von `start` bis `end` (end exklusiv, end >= start)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if add_months(start, months) > end:
        months -= 1
    return months, (end - add_months(start, months)).days


def merge_spans(spans: Iterable[Span]) -> list[Span]:
    """Ueberlappende oder unmittelbar aufeinanderfolgende Einsaetze zu einem Zeitraum
    vereinigen. Sortiert nach Beginn; ein offenes Ende bleibt offen."""
    merged: list[Span] = []
    for span in sorted(spans, key=lambda s: (s.start, s.end or date.max)):
        if merged:
            last = merged[-1]
            if last.end is None:
                continue  # offener Einsatz deckt alles Spaetere ab
            if span.start <= last.end + timedelta(days=1):
                end = None if span.end is None else max(last.end, span.end)
                merged[-1] = Span(last.start, end)
                continue
        merged.append(span)
    return merged


def _gap_resets(previous_end: date, next_start: date, config: DeadlineConfig) -> bool:
    """Luecke = Tage zwischen den Einsaetzen. Laenger als `reset_gap_months` => Neustart.
    Genau 3 Monate zaehlen noch zusammen, 3 Monate und 1 Tag nicht."""
    return next_start > add_months(previous_end + timedelta(days=1), config.reset_gap_months)


def _current_chain(spans: Sequence[Span], config: DeadlineConfig) -> list[Span]:
    """Die letzte zusammenhaengende Kette (nach Reset-Regel) aus bereits vereinigten Spans."""
    chain: list[Span] = []
    for span in spans:
        if chain:
            last_end = chain[-1].end
            if last_end is not None and _gap_resets(last_end, span.start, config):
                chain = []
        chain.append(span)
    return chain


def _nth_day(chain: Sequence[Span], n: int) -> date:
    """Datum des n-ten Einsatztages (n >= 1). Ueber das Ende der bekannten Einsaetze hinaus wird
    ununterbrochene Fortsetzung angenommen (Projektion)."""
    remaining = n
    for span in chain:
        if span.end is None:
            return span.start + timedelta(days=remaining - 1)
        length = (span.end - span.start).days + 1
        if remaining <= length:
            return span.start + timedelta(days=remaining - 1)
        remaining -= length
    last_end = chain[-1].end
    assert last_end is not None
    return last_end + timedelta(days=remaining)


def _days_counted(chain: Sequence[Span], today: date) -> int:
    total = 0
    for span in chain:
        end = today if span.end is None else min(span.end, today)
        if end >= span.start:
            total += (end - span.start).days + 1
    return total


def _traffic(days_remaining: int, config: DeadlineConfig) -> Traffic:
    if days_remaining < config.red_days:  # inkl. ueberschritten (negativ)
        return Traffic.RED
    if days_remaining < config.yellow_days:
        return Traffic.YELLOW
    return Traffic.GREEN


def compute_deadline(
    spans: Iterable[Span], today: date, config: DeadlineConfig | None = None
) -> DeadlineResult:
    """Fristen fuer EIN Paar (Leiharbeitnehmer, Kunde). `spans`: alle nicht abgebrochenen
    Einsaetze dieses Paares (Beginn, Ende oder None).

    Liegt der letzte Einsatz schon laenger als `reset_gap_months` zurueck, gibt es keinen
    fortsetzbaren Zaehler mehr (`has_chain=False`): ein neuer Einsatz faengt bei null an."""
    cfg = config or DeadlineConfig()
    merged = merge_spans(spans)
    if not merged:
        return NO_CHAIN
    chain = _current_chain(merged, cfg)
    last_end = chain[-1].end
    if last_end is not None and _gap_resets(last_end, today, cfg):
        return NO_CHAIN
    start = chain[0].start
    window_max = (add_months(start, cfg.max_months) - start).days
    window_equal = (add_months(start, cfg.equal_pay_months) - start).days
    max_end = _nth_day(chain, window_max)
    equal_from = _nth_day(chain, window_equal) + timedelta(days=1)
    counted = _days_counted(chain, today)
    months, extra_days = full_months_between(start, start + timedelta(days=counted))
    remaining = (max_end - today).days
    return DeadlineResult(
        has_chain=True,
        chain_start=start,
        elapsed_months=months,
        elapsed_days=extra_days,
        counted_days=counted,
        equal_pay_from=equal_from,
        equal_pay_reached=today >= equal_from,
        max_end_date=max_end,
        days_remaining=remaining,
        exceeded=remaining < 0,
        traffic=_traffic(remaining, cfg),
    )
