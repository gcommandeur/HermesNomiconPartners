# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Zeitstrahl "Meine Provision": Monatswerte summieren sich exakt zur Quartalsprovision, auch über
eine Stufengrenze hinweg; laufender Monat vorläufig; Fortschritt zur nächsten Rolle."""

from datetime import date
from decimal import Decimal

import pytest

from cc_crm.services.commission_model import DEFAULT_CONFIG, commission_for_quarter
from cc_crm.services.commission_timeline import (
    last_months,
    month_values,
    monthly_fixed,
    progress_for,
)

D = Decimal
CONFIG = DEFAULT_CONFIG
SENIOR = CONFIG.rank("senior")  # frei 10.000, Satz 1 bis 35.000, Satz 2 bis 96.000
TODAY = date(2026, 5, 20)  # zweiter Monat des 2. Quartals


def rows(*months: tuple[int, int, str, int, int]):  # type: ignore[no-untyped-def]
    return [(y, m, D(rev), p, s) for y, m, rev, p, s in months]


def test_months_of_a_quarter_add_up_to_the_quarter_commission_across_band_borders() -> None:
    # 20.000 / 30.000 / 50.000: der Umsatz überschreitet im 2. und 3. Monat die Stufengrenzen
    values = month_values(
        CONFIG,
        SENIOR,
        rows((2026, 4, "20000", 0, 0), (2026, 5, "30000", 0, 0), (2026, 6, "50000", 0, 0)),
        date(2026, 7, 5),
    )
    quarter = commission_for_quarter(D("100000"), SENIOR, CONFIG.general).commission
    assert sum(v.commission for v in values) == quarter  # exakt, kein Cent Abweichung
    # Stufen laufen mit: Monat 1 = 10.000 über der Freigrenze zu 20 %
    assert values[0].commission == D("2000.00")
    # Monat 2: Quartalsumsatz 50.000 -> 25.000*20 % + 15.000*22,5 % = 8.375; minus 2.000
    assert values[1].commission == D("6375.00")
    assert [v.month_in_quarter for v in values] == [1, 2, 3]


def test_quarters_start_over_and_fix_adds_up_exactly() -> None:
    values = month_values(
        CONFIG,
        SENIOR,
        rows(
            (2026, 6, "40000", 0, 0),  # letzter Monat des 2. Quartals
            (2026, 7, "40000", 0, 0),  # erster Monat des 3. Quartals: Freigrenze gilt neu
            (2026, 8, "0", 0, 0),
            (2026, 9, "0", 0, 0),
        ),
        date(2026, 10, 1),
    )
    q3 = values[1:]
    first = commission_for_quarter(D("40000"), SENIOR, CONFIG.general).commission
    assert q3[0].commission == first  # kein Übertrag aus dem Vorquartal
    assert sum(v.commission for v in q3) == first
    quarter_fix = SENIOR.fixed_yearly / 4
    assert (
        sum(v.fixed_pay for v in q3) == quarter_fix
    )  # 11.000 exakt (dritter Monat nimmt den Rest)


def test_fixed_pay_split_is_exact_for_odd_amounts() -> None:
    rank = CONFIG.rank("consultant")
    odd = rank.__class__(**{**rank.__dict__, "fixed_yearly": D("40001")})
    parts = [monthly_fixed(odd, n) for n in (1, 2, 3)]
    assert sum(parts) == D("10000.25")


def test_bonus_comes_in_the_month_of_the_deal_and_current_month_is_provisional() -> None:
    values = month_values(
        CONFIG,
        SENIOR,
        rows((2026, 4, "10000", 1, 0), (2026, 5, "12000", 0, 2)),
        TODAY,
    )
    assert values[0].bonus == D("300.00") and not values[0].is_provisional
    assert values[1].bonus == D("600.00")
    assert values[1].is_current and values[1].is_provisional
    assert not values[0].is_current


def test_without_a_rank_only_revenue_is_shown() -> None:
    (only,) = month_values(CONFIG, None, rows((2026, 5, "25000", 1, 1)), TODAY)
    assert only.revenue == D("25000.00")
    assert (only.commission, only.fixed_pay, only.bonus, only.total) == (D("0.00"),) * 4


def test_total_is_commission_plus_fix_plus_bonus() -> None:
    (month,) = month_values(CONFIG, SENIOR, rows((2026, 4, "20000", 1, 0)), date(2026, 4, 30))
    assert month.total == month.commission + month.fixed_pay + month.bonus


def test_last_twelve_months_cross_the_year_boundary() -> None:
    months = last_months(date(2026, 2, 10))
    assert len(months) == 12
    assert months[0] == (2025, 3) and months[-1] == (2026, 2)


def test_progress_to_next_role_and_days_to_quarter_end() -> None:
    progress = progress_for(CONFIG, SENIOR, D("68000"), TODAY)
    assert progress.next_rank_label == "Manager" and not progress.is_top_rank
    assert progress.hurdle == D("96000") and progress.remaining == D("28000.00")
    assert progress.percent == D("70.8")
    assert progress.days_to_quarter_end == (date(2026, 6, 30) - TODAY).days == 41
    # nächste Provisionsstufe (hier schon über der 2. Grenze 35.000, noch unter 96.000)
    assert progress.next_band_remaining == D("28000.00") and progress.next_band_rate == D("25")


def test_progress_is_capped_and_never_negative_after_the_hurdle() -> None:
    progress = progress_for(CONFIG, SENIOR, D("120000"), TODAY)
    assert progress.remaining == D("0.00") and progress.percent == D("100")
    assert progress.next_band_remaining is None


def test_top_rank_shows_distance_to_next_commission_step_instead() -> None:
    director = CONFIG.rank("director")
    progress = progress_for(CONFIG, director, D("70000"), TODAY)
    assert progress.is_top_rank and progress.hurdle is None and progress.remaining is None
    assert progress.next_rank_label is None
    assert progress.next_band_remaining == D("15000.00")  # bis 85.000 (Stufe 2)
    assert progress.next_band_rate == D("37.5")


@pytest.mark.parametrize("revenue", ["0", "9999", "10000", "35000", "96000", "250000"])
def test_single_month_equals_quarter_commission_for_any_revenue(revenue: str) -> None:
    (month,) = month_values(CONFIG, SENIOR, rows((2026, 4, revenue, 0, 0)), date(2026, 4, 30))
    assert month.commission == commission_for_quarter(D(revenue), SENIOR, CONFIG.general).commission
