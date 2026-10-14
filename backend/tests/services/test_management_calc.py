# NOMICON: Ansicht "Gesamt" - Rechenfunktionen gegen handgerechnete Beispiele.
from datetime import date, timedelta
from decimal import Decimal

import pytest

from cc_crm.services.management_calc import (
    DirectItem,
    StaffingItem,
    direct_forecast,
    forecast_end,
    margin_per_hour,
    period_bounds,
    remaining_weeks,
    staffing_forecast,
    staffing_margin,
)

TODAY = date(2026, 10, 14)
D = Decimal


def test_margin_uses_rate_minus_wage_times_employer_factor() -> None:
    # 27,80 - 15,40 x 1,23 = 27,80 - 18,942 = 8,858 je Stunde
    assert margin_per_hour(D("27.80"), D("15.40"), D("1.23")) == D("8.858")
    # 40 Stunden x 8,858 = 354,32
    assert staffing_margin(D("40"), D("27.80"), D("15.40"), D("1.23")) == D("354.32")
    # negative Marge bleibt negativ (Verlust sichtbar, nicht auf 0 gekappt)
    assert staffing_margin(D("10"), D("12.00"), D("10.00"), D("1.23")) == D("-3.00")


def test_direct_forecast_weights_only_where_fee_and_probability_exist() -> None:
    result = direct_forecast(
        [
            DirectItem(D("10000"), D("0.5")),  # 5.000
            DirectItem(D("20000"), D("0.25")),  # 5.000
            DirectItem(D("8000"), None),  # Fee ohne Wahrscheinlichkeit: nicht erfunden
            DirectItem(None, D("0.9")),  # Wahrscheinlichkeit ohne Fee: nicht erfunden
            DirectItem(None, None),
        ]
    )
    assert result.weighted == D("10000.00")
    assert (result.without_probability, result.without_fee) == (1, 2)


def test_forecast_end_never_exceeds_the_maximum_duration() -> None:
    assert forecast_end(
        TODAY + timedelta(days=14), TODAY + timedelta(days=100)
    ) == TODAY + timedelta(days=14)
    assert forecast_end(
        TODAY + timedelta(days=100), TODAY + timedelta(days=21)
    ) == TODAY + timedelta(days=21)
    assert forecast_end(None, TODAY + timedelta(days=7)) == TODAY + timedelta(days=7)
    assert forecast_end(TODAY + timedelta(days=7), None) == TODAY + timedelta(days=7)
    assert forecast_end(None, None) is None


def test_remaining_weeks_and_staffing_forecast() -> None:
    assert remaining_weeks(TODAY + timedelta(days=14), TODAY) == D(2)
    assert remaining_weeks(TODAY - timedelta(days=3), TODAY) == D(0)  # vorbei: nichts mehr
    margin = D("8.858")
    result = staffing_forecast(
        [
            # Ende in 14 Tagen (2 Wochen): 8,858 x 40 x 2 = 708,64
            StaffingItem(margin, D("40"), TODAY + timedelta(days=14), TODAY + timedelta(days=100)),
            # geplant in 100 Tagen, Hoechstdauer in 21 Tagen (3 Wochen): 8,858 x 40 x 3 = 1062,96
            StaffingItem(margin, D("40"), TODAY + timedelta(days=100), TODAY + timedelta(days=21)),
            # Ende schon vorbei: zaehlt mit 0
            StaffingItem(margin, D("40"), TODAY - timedelta(days=5), None),
            # fehlende Angaben: ausgeschlossen, nicht geraten
            StaffingItem(None, D("40"), TODAY + timedelta(days=14), None),
            StaffingItem(margin, None, TODAY + timedelta(days=14), None),
            StaffingItem(margin, D("40"), None, None),
        ],
        TODAY,
    )
    assert result.margin == D("1771.60")
    assert (result.counted, result.excluded) == (3, 3)


def test_period_bounds_are_rolling_windows_including_today() -> None:
    assert period_bounds("week", TODAY) == (date(2026, 10, 8), TODAY)
    assert period_bounds("month", TODAY) == (date(2026, 9, 15), TODAY)
    assert period_bounds("quarter", TODAY) == (date(2026, 7, 17), TODAY)
    with pytest.raises(ValueError):
        period_bounds("year", TODAY)
