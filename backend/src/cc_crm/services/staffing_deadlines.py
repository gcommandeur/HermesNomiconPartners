# NOMICON: Arbeitnehmerüberlassung - nur in der Nomicon-Kopie.
"""Fristen der Arbeitnehmerüberlassung als REINE Funktionen (keine Datenbank, keine Uhr).

Fachliche Grundlage (Stand: Annahmen aus dem Nutzerauftrag, KEIN Rechtsrat - mit Fachanwalt oder
Verband bestätigen, Tarifverträge können abweichen):
- Höchstüberlassungsdauer: 18 Monate je Paar (Leiharbeitnehmer, Kunde).
- Equal Pay (gleiches Entgelt wie die Stammbelegschaft) ab dem 10. Monat, d.h. nach 9 Monaten.
- Eine Unterbrechung LAENGER als 3 Monate setzt den Zähler zurück; eine kuerzere (oder genau
  3 Monate) fuehrt die Zeiten zusammen.

Alle Werte stehen in `DeadlineConfig` (Standardwerte hier, einstellbar über app_settings, siehe
services/staffing_settings.py) - nichts davon ist im Rechenkern hart verdrahtet.

Rechenmodell: Gezaehlt werden die Einsatztage (Vereinigung ueberlappender Einsätze), Luecken
zählen nicht mit. "N Monate" sind dabei die Kalendertage, die N Monate ab Kettenbeginn lang sind
(`add_months(start, N) - start`). Ohne Lücke endet die Höchstdauer damit am Tag vor
`add_months(Kettenbeginn, 18)`; jede Lücke verschiebt die Frist um ihre Laenge nach hinten.
Monatsarithmetik schneidet am Monatsende ab (31.8. + 6 Monate = 28./29.2.)."""

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

# Benannte Standardwerte (Nutzervorgabe 2026-10-11) - einstellbar, nicht hartcodiert verwenden.
DEFAULT_MAX_ASSIGNMENT_MONTHS = 18  # Höchstüberlassungsdauer
DEFAULT_EQUAL_PAY_MONTHS = 9  # Equal Pay gilt ab dem Folgetag nach 9 Monaten
DEFAULT_RESET_GAP_MONTHS = 3  # Unterbrechung länger als 3 Monate setzt den Zähler zurück
DEFAULT_YELLOW_DAYS = 60  # Ampel gelb: weniger als 60 Tage Restlaufzeit
DEFAULT_RED_DAYS = 30  # Ampel rot: weniger als 30 Tage oder überschritten


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
    """Ein Einsatz als Zeitraum (beide Tage eingeschlossen). `end=None`: läuft noch (bis heute
    und darüber hinaus)."""

    start: date
    end: date | None = None


@dataclass(frozen=True)
class DeadlineResult:
    # False: kein laufender oder fortsetzbarer Zähler (z.B. keine Einsätze oder die letzte
    # Unterbrechung ist schon länger als die Grenze) - dann sind alle Daten None, Ampel gruen.
    has_chain: bool
    chain_start: date | None
    elapsed_months: int  # bisherige Dauer (Einsatztage bis heute) in vollen Monaten ...
    elapsed_days: int  # ... plus Resttage
    counted_days: int  # bisherige Einsatztage insgesamt
    equal_pay_from: date | None  # erster Tag, ab dem Equal Pay gilt
    equal_pay_reached: bool
    max_end_date: date | None  # letzter zulaessiger Einsatztag
    days_remaining: int | None  # max_end_date - heute (negativ = überschritten)
    exceeded: bool
    traffic: Traffic
    # Tage der Kette, die NUR aus Vorzeiten stammen (früher beim Kunden geleistet, nicht aus
    # Einsätzen des CRM). Schon in `counted_days` enthalten; dient der Anzeige "inkl. Vorzeit".
    prior_days: int = 0


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
    """Überlappende oder unmittelbar aufeinanderfolgende Einsätze zu einem Zeitraum
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
    """Lücke = Tage zwischen den Einsätzen. Länger als `reset_gap_months` => Neustart.
    Genau 3 Monate zählen noch zusammen, 3 Monate und 1 Tag nicht."""
    return next_start > add_months(previous_end + timedelta(days=1), config.reset_gap_months)


def _current_chain(spans: Sequence[Span], config: DeadlineConfig) -> list[Span]:
    """Die letzte zusammenhängende Kette (nach Reset-Regel) aus bereits vereinigten Spans."""
    chain: list[Span] = []
    for span in spans:
        if chain:
            last_end = chain[-1].end
            if last_end is not None and _gap_resets(last_end, span.start, config):
                chain = []
        chain.append(span)
    return chain


def _nth_day(chain: Sequence[Span], n: int) -> date:
    """Datum des n-ten Einsatztages (n >= 1). Über das Ende der bekannten Einsätze hinaus wird
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


def _prior_only_days(chain: Sequence[Span], assignment_spans: Sequence[Span], today: date) -> int:
    """Tage der Kette bis heute, die von keinem Einsatz abgedeckt sind (also nur Vorzeit).
    `assignment_spans` müssen bereits vereinigt (`merge_spans`) sein."""
    covered: list[Span] = []
    for link in chain:
        for own in assignment_spans:
            start = max(link.start, own.start)
            ends = [d for d in (link.end, own.end) if d is not None]
            end = min(ends) if ends else None
            if end is None or start <= end:
                covered.append(Span(start, end))
    return _days_counted(chain, today) - _days_counted(merge_spans(covered), today)


def _traffic(days_remaining: int, config: DeadlineConfig) -> Traffic:
    if days_remaining < config.red_days:  # inkl. überschritten (negativ)
        return Traffic.RED
    if days_remaining < config.yellow_days:
        return Traffic.YELLOW
    return Traffic.GREEN


def compute_deadline(
    spans: Iterable[Span],
    today: date,
    config: DeadlineConfig | None = None,
    prior_spans: Iterable[Span] = (),
) -> DeadlineResult:
    """Fristen für EIN Paar (Leiharbeitnehmer, Kunde). `spans`: alle nicht abgebrochenen
    Einsätze dieses Paares (Beginn, Ende oder None). `prior_spans`: Vorzeiten beim selben
    Kunden (früher geleistet, z.B. über einen anderen Verleiher) - immer abgeschlossen, sie
    gehen wie Einsätze in Vereinigung und Reset-Regel ein.

    Liegt der letzte Einsatz schon länger als `reset_gap_months` zurück, gibt es keinen
    fortsetzbaren Zähler mehr (`has_chain=False`): ein neuer Einsatz fängt bei null an."""
    cfg = config or DeadlineConfig()
    assignment_spans = merge_spans(spans)
    merged = merge_spans([*assignment_spans, *prior_spans])
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
        prior_days=_prior_only_days(chain, assignment_spans, today),
    )
