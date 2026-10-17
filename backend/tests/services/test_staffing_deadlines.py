# NOMICON: Arbeitnehmerueberlassung - nur in der Nomicon-Kopie.
"""Fristen-Rechenkern: reine Funktionen, viele Randfaelle (Monatsende, Schaltjahr, Luecken)."""

from datetime import date

import pytest

from cc_crm.services.staffing_deadlines import (
    NO_CHAIN,
    DeadlineConfig,
    Span,
    Traffic,
    add_months,
    compute_deadline,
    full_months_between,
    merge_spans,
)

D = date


# --- Monatsarithmetik -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (D(2025, 1, 31), 1, D(2025, 2, 28)),
        (D(2024, 1, 31), 1, D(2024, 2, 29)),  # Schaltjahr
        (D(2023, 8, 31), 6, D(2024, 2, 29)),
        (D(2025, 8, 31), 9, D(2026, 5, 31)),
        (D(2025, 8, 31), 18, D(2027, 2, 28)),
        (D(2024, 2, 29), 12, D(2025, 2, 28)),
        (D(2024, 2, 29), 48, D(2028, 2, 29)),
        (D(2025, 12, 15), 1, D(2026, 1, 15)),  # Jahreswechsel
        (D(2025, 3, 31), 0, D(2025, 3, 31)),
    ],
)
def test_add_months_clips_to_month_end(start: date, months: int, expected: date) -> None:
    assert add_months(start, months) == expected


def test_full_months_between() -> None:
    assert full_months_between(D(2025, 1, 1), D(2025, 4, 1)) == (3, 0)
    assert full_months_between(D(2025, 1, 31), D(2025, 3, 1)) == (1, 1)  # 31.1.+1M = 28.2.
    assert full_months_between(D(2025, 1, 1), D(2025, 1, 1)) == (0, 0)
    assert full_months_between(D(2025, 1, 15), D(2025, 2, 14)) == (0, 30)


# --- Vereinigung ueberlappender Einsaetze ---------------------------------------------------


def test_merge_spans_overlap_adjacent_and_open() -> None:
    merged = merge_spans(
        [
            Span(D(2025, 5, 1), D(2025, 9, 30)),
            Span(D(2025, 1, 1), D(2025, 6, 30)),
            Span(D(2025, 10, 1), D(2025, 10, 31)),  # unmittelbar anschliessend
            Span(D(2026, 3, 1), None),
            Span(D(2026, 4, 1), D(2026, 4, 30)),  # liegt im offenen Einsatz
        ]
    )
    assert merged == [Span(D(2025, 1, 1), D(2025, 10, 31)), Span(D(2026, 3, 1), None)]


# --- Grundfall und Ampel --------------------------------------------------------------------


def test_contiguous_assignment() -> None:
    result = compute_deadline([Span(D(2025, 1, 1))], D(2025, 3, 31))
    assert result.has_chain
    assert result.chain_start == D(2025, 1, 1)
    assert result.counted_days == 90
    assert (result.elapsed_months, result.elapsed_days) == (3, 0)
    assert result.equal_pay_from == D(2025, 10, 1)  # Folgetag nach 9 Monaten
    assert not result.equal_pay_reached
    assert result.max_end_date == D(2026, 6, 30)  # letzter Tag der 18 Monate
    assert result.days_remaining == 456
    assert not result.exceeded
    assert result.traffic == Traffic.GREEN


@pytest.mark.parametrize(
    ("today", "remaining", "traffic", "exceeded"),
    [
        (D(2026, 4, 30), 61, Traffic.GREEN, False),
        (D(2026, 5, 1), 60, Traffic.GREEN, False),
        (D(2026, 5, 2), 59, Traffic.YELLOW, False),
        (D(2026, 5, 31), 30, Traffic.YELLOW, False),
        (D(2026, 6, 1), 29, Traffic.RED, False),
        (D(2026, 6, 30), 0, Traffic.RED, False),  # letzter zulaessiger Tag
        (D(2026, 7, 1), -1, Traffic.RED, True),
        (D(2026, 9, 1), -63, Traffic.RED, True),
    ],
)
def test_traffic_light_thresholds(
    today: date, remaining: int, traffic: Traffic, exceeded: bool
) -> None:
    result = compute_deadline([Span(D(2025, 1, 1))], today)
    assert result.max_end_date == D(2026, 6, 30)
    assert result.days_remaining == remaining
    assert result.traffic == traffic
    assert result.exceeded is exceeded


def test_equal_pay_threshold() -> None:
    spans = [Span(D(2025, 1, 1))]
    assert not compute_deadline(spans, D(2025, 9, 30)).equal_pay_reached
    assert compute_deadline(spans, D(2025, 10, 1)).equal_pay_reached


# --- Luecken ---------------------------------------------------------------------------------


def test_gap_of_exactly_three_months_keeps_the_count() -> None:
    spans = [Span(D(2025, 1, 1), D(2025, 3, 31)), Span(D(2025, 7, 1))]  # Luecke 1.4.-30.6.
    result = compute_deadline(spans, D(2025, 12, 31))
    assert result.chain_start == D(2025, 1, 1)
    assert result.counted_days == 90 + 184  # die Luecke zaehlt nicht mit
    assert (result.elapsed_months, result.elapsed_days) == (9, 1)
    assert result.max_end_date == D(2026, 9, 29)  # 30.6.2026 + 91 Tage Luecke


def test_gap_of_three_months_and_one_day_resets() -> None:
    spans = [Span(D(2025, 1, 1), D(2025, 3, 31)), Span(D(2025, 7, 2))]
    result = compute_deadline(spans, D(2025, 12, 31))
    assert result.chain_start == D(2025, 7, 2)
    assert result.counted_days == 183
    assert result.max_end_date == D(2027, 1, 1)


def test_gap_starting_at_month_end() -> None:
    # Ende 30.1.: Luecke beginnt 31.1.; 3 Monate spaeter = 30.4. (Abschneiden am Monatsende)
    ok = compute_deadline(
        [Span(D(2025, 1, 1), D(2025, 1, 30)), Span(D(2025, 4, 30))], D(2025, 5, 1)
    )
    assert ok.chain_start == D(2025, 1, 1)
    reset = compute_deadline(
        [Span(D(2025, 1, 1), D(2025, 1, 30)), Span(D(2025, 5, 1))], D(2025, 5, 2)
    )
    assert reset.chain_start == D(2025, 5, 1)


def test_chain_is_not_continuable_after_a_long_pause() -> None:
    spans = [Span(D(2025, 1, 1), D(2025, 3, 31))]
    assert compute_deadline(spans, D(2025, 7, 1)).has_chain  # genau 3 Monate: noch fortsetzbar
    assert compute_deadline(spans, D(2025, 7, 2)) == NO_CHAIN
    assert compute_deadline([], D(2025, 7, 2)) == NO_CHAIN


def test_old_chain_before_a_reset_is_forgotten() -> None:
    spans = [Span(D(2023, 1, 1), D(2023, 12, 31)), Span(D(2025, 1, 1))]
    result = compute_deadline(spans, D(2025, 2, 1))
    assert result.chain_start == D(2025, 1, 1)
    assert result.counted_days == 32


def test_pause_inside_the_gap_projects_continuous_continuation() -> None:
    result = compute_deadline([Span(D(2025, 1, 1), D(2025, 2, 28))], D(2025, 3, 15))
    assert result.has_chain
    assert result.counted_days == 59
    assert result.max_end_date == D(2026, 6, 30)  # wie ohne Unterbrechung


# --- Ueberlappung, Monatsende, Schaltjahr, Planung -----------------------------------------


def test_overlapping_assignments_count_once() -> None:
    spans = [Span(D(2025, 1, 1), D(2025, 6, 30)), Span(D(2025, 5, 1), D(2025, 9, 30))]
    result = compute_deadline(spans, D(2025, 12, 31))
    assert result.counted_days == 273
    assert result.chain_start == D(2025, 1, 1)


def test_start_on_the_31st() -> None:
    result = compute_deadline([Span(D(2025, 8, 31))], D(2025, 9, 1))
    assert result.equal_pay_from == D(2026, 5, 31)
    assert result.max_end_date == D(2027, 2, 27)  # 31.8.2025 + 18 Monate = 28.2.2027, minus 1 Tag


def test_start_on_leap_day() -> None:
    result = compute_deadline([Span(D(2024, 2, 29))], D(2024, 3, 1))
    assert result.equal_pay_from == D(2024, 11, 29)
    assert result.max_end_date == D(2025, 8, 28)


def test_future_planned_assignment_counts_nothing_yet() -> None:
    result = compute_deadline([Span(D(2026, 1, 1))], D(2025, 12, 1))
    assert result.has_chain
    assert result.counted_days == 0
    assert (result.elapsed_months, result.elapsed_days) == (0, 0)
    assert result.max_end_date == D(2027, 6, 30)
    assert result.traffic == Traffic.GREEN


def test_values_come_from_the_configuration() -> None:
    config = DeadlineConfig(
        max_months=12, equal_pay_months=6, reset_gap_months=1, yellow_days=20, red_days=10
    )
    spans = [Span(D(2025, 1, 1), D(2025, 2, 28)), Span(D(2025, 4, 1))]  # Luecke genau 1 Monat
    joined = compute_deadline(spans, D(2025, 4, 2), config)
    assert joined.chain_start == D(2025, 1, 1)
    assert joined.equal_pay_from == D(2025, 8, 1)  # 1.7. (6 Monate ab 1.1.) + 31 Tage Luecke
    reset = compute_deadline(
        [Span(D(2025, 1, 1), D(2025, 2, 28)), Span(D(2025, 4, 2))], D(2025, 4, 3), config
    )
    assert reset.chain_start == D(2025, 4, 2)
    contiguous = compute_deadline([Span(D(2025, 1, 1))], D(2025, 12, 15), config)
    assert contiguous.max_end_date == D(2025, 12, 31)
    assert contiguous.traffic == Traffic.YELLOW  # 16 Tage: unter 20, ueber 10


# --- Vorzeiten beim Kunden (anderer Verleiher, vor CRM-Start) --------------------------------


def test_prior_period_and_assignment_form_one_chain() -> None:
    prior = [Span(D(2025, 1, 1), D(2025, 6, 30))]  # 181 Tage
    result = compute_deadline([Span(D(2025, 7, 1), None)], D(2025, 9, 15), prior_spans=prior)
    assert result.chain_start == D(2025, 1, 1)
    assert result.counted_days == 181 + 77
    assert result.prior_days == 181
    assert result.max_end_date == D(2026, 6, 30)  # 18 Monate ab 1.1.2025


def test_gap_up_to_three_months_joins_prior_period_longer_resets() -> None:
    prior = [Span(D(2025, 1, 1), D(2025, 3, 31))]
    joined = compute_deadline([Span(D(2025, 6, 30), None)], D(2025, 7, 10), prior_spans=prior)
    assert joined.chain_start == D(2025, 1, 1)  # Lücke 1.4. bis 29.6. = noch 3 Monate
    reset = compute_deadline([Span(D(2025, 7, 2), None)], D(2025, 7, 10), prior_spans=prior)
    assert reset.chain_start == D(2025, 7, 2)  # 3 Monate und 1 Tag: Neustart
    assert reset.prior_days == 0


def test_prior_period_moves_equal_pay_date_forward() -> None:
    assignment = [Span(D(2025, 7, 1), None)]
    without = compute_deadline(assignment, D(2025, 9, 15))
    with_prior = compute_deadline(
        assignment, D(2025, 9, 15), prior_spans=[Span(D(2025, 1, 1), D(2025, 6, 30))]
    )
    assert without.equal_pay_from == D(2026, 4, 1)
    assert with_prior.equal_pay_from == D(2025, 10, 1)  # 9 Monate ab 1.1.2025
    assert with_prior.equal_pay_from < without.equal_pay_from  # type: ignore[operator]


def test_prior_period_alone_counts_until_the_gap_is_over() -> None:
    prior = [Span(D(2025, 1, 1), D(2025, 6, 30))]
    running = compute_deadline([], D(2025, 8, 1), prior_spans=prior)
    assert running.has_chain
    assert (running.counted_days, running.prior_days) == (181, 181)
    assert compute_deadline([], D(2025, 10, 1), prior_spans=prior).has_chain  # genau 3 Monate
    assert not compute_deadline([], D(2025, 10, 2), prior_spans=prior).has_chain


def test_prior_days_ignore_overlap_with_assignments() -> None:
    # Die Vorzeit überlappt den Einsatz: nichts wird doppelt gezählt, Vorzeit ist nur der Rest.
    result = compute_deadline(
        [Span(D(2025, 3, 1), D(2025, 4, 30))],
        D(2025, 8, 1),
        prior_spans=[Span(D(2025, 1, 1), D(2025, 3, 31))],
    )
    assert result.chain_start == D(2025, 1, 1)
    assert result.counted_days == 120  # 1.1. bis 30.4.
    assert result.prior_days == 59  # 1.1. bis 28.2. (März liegt schon im Einsatz)
