# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Rechenkern des Provisionsmodells. WICHTIG: Die Excel "Nomicon_Provisionsmodell" liegt der
Entwicklung nicht vor - alle erwarteten Werte sind von Hand nach den dokumentierten Annahmen
(services/commission_model.py, Kopf) gerechnet. Stimmen die Excel-Beispielzahlen nicht, ist die
Annahme zu klaeren, nicht der Test anzupassen."""

from dataclasses import replace
from decimal import Decimal

import pytest

from cc_crm.services.commission_model import (
    DEFAULT_CONFIG,
    CommissionConfig,
    ConfigError,
    GeneralConfig,
    Traffic,
    break_even_revenue,
    commission_for_quarter,
    employer_cost_for_quarter,
    evaluate_quarter,
    margin,
    promoted_rank_key,
    target_revenue,
    validate_config,
)

D = Decimal
G = DEFAULT_CONFIG.general
JUNIOR = DEFAULT_CONFIG.rank("junior")


def commission(revenue: str, rank: str = "junior") -> Decimal:
    return commission_for_quarter(D(revenue), DEFAULT_CONFIG.rank(rank), G).commission


# --- Startwerte aus der Excel -------------------------------------------------------------------


def test_default_values_match_the_excel_start_values() -> None:
    assert G.commission_free_base == 10000
    assert G.employer_factor == D("1.23")
    assert G.extra_cost_monthly == 500
    assert G.fee_rate_on_target_salary == 28
    assert G.min_fee == 12000
    assert G.target_margin == 50
    table = {
        r.key: (r.fixed_monthly, r.rate1, r.threshold1, r.rate2, r.threshold2, r.rate3)
        for r in DEFAULT_CONFIG.ranks
    }
    assert table == {
        "junior": (3000, 10, 15000, 12, 30000, 14),
        "consultant": (3500, 12, 20000, 14, 40000, 16),
        "specialist": (3500, 14, 25000, 16, 55000, 18),
        "senior": (3500, 16, 35000, 18, 80000, 20),
        "principal": (3750, 18, 50000, 20, 120000, 22),
        "director": (4000, 22, 75000, 25, 160000, 30),
    }
    assert [r.key for r in DEFAULT_CONFIG.ranks][0] == "junior"  # aufsteigend
    assert validate_config(DEFAULT_CONFIG) is DEFAULT_CONFIG


# --- Gestaffelte Provision ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("revenue", "expected"),
    [
        ("0", "0.00"),
        ("9999.99", "0.00"),
        ("10000", "0.00"),  # die ersten 10.000 EUR ohne Provision
        ("15000", "500.00"),  # 5.000 x 10 %
        ("20000", "1100.00"),  # 500 + 5.000 x 12 %
        ("30000", "2300.00"),  # 500 + 15.000 x 12 %
        ("40000", "3700.00"),  # 2.300 + 10.000 x 14 %
        ("-500", "0.00"),  # negativer Umsatz (Stornos) gibt keine Provision
    ],
)
def test_staggered_commission_junior(revenue: str, expected: str) -> None:
    assert commission(revenue) == D(expected)


def test_commission_breakdown_by_band() -> None:
    result = commission_for_quarter(D("40000"), JUNIOR, G)
    assert (result.band1_revenue, result.band2_revenue, result.band3_revenue) == (
        5000,
        15000,
        10000,
    )
    assert (result.band1_commission, result.band2_commission, result.band3_commission) == (
        D("500.00"),
        D("1800.00"),
        D("1400.00"),
    )
    assert result.commission == D("3700.00")


def test_commission_is_continuous_and_monotonic_at_every_threshold() -> None:
    for rank in DEFAULT_CONFIG.ranks:
        previous = D("0")
        for revenue in range(0, 200001, 500):
            current = commission_for_quarter(D(revenue), rank, G).commission
            assert current >= previous, (rank.key, revenue)
            previous = current
        for threshold in (rank.threshold1, rank.threshold2):
            below = commission_for_quarter(threshold - D("0.01"), rank, G).commission
            above = commission_for_quarter(threshold + D("0.01"), rank, G).commission
            assert above - below < D("0.05"), (rank.key, threshold)  # kein Sprung


def test_commission_other_ranks() -> None:
    # Director bei 100.000: 65.000 x 22 % = 14.300 + 25.000 x 25 % = 6.250
    assert commission("100000", "director") == D("20550.00")
    # Senior bei 90.000: 25.000 x 16 % = 4.000 + 45.000 x 18 % = 8.100 + 10.000 x 20 % = 2.000
    assert commission("90000", "senior") == D("14100.00")


def test_free_base_above_threshold1_skips_band1() -> None:
    general = replace(G, commission_free_base=D("20000"))
    result = commission_for_quarter(D("25000"), JUNIOR, general)
    assert result.band1_revenue == 0
    assert result.band2_revenue == D("5000")  # von 20.000 bis 25.000
    assert result.commission == D("600.00")


# --- Kosten, Marge, Ampel --------------------------------------------------------------------


def test_employer_cost_and_margin() -> None:
    assert employer_cost_for_quarter(JUNIOR, D("0"), G) == D("12570.00")  # 9.000 x 1,23 + 1.500
    assert employer_cost_for_quarter(JUNIOR, D("1100"), G) == D("13923.00")  # 10.100 x 1,23 + 1.500
    assert margin(D("20000"), D("13923")) == (D("6077.00"), D("30.39"))
    assert margin(D("0"), D("12570")) == (D("-12570.00"), None)


@pytest.mark.parametrize(
    ("revenue", "traffic"),
    [
        ("0", Traffic.RED),
        ("12000", Traffic.RED),  # unter dem Break-even (12.930,44)
        ("20000", Traffic.YELLOW),  # Marge 30,39 %
        ("40000", Traffic.GREEN),  # Marge 57,20 %
    ],
)
def test_traffic_light(revenue: str, traffic: Traffic) -> None:
    assert evaluate_quarter(D(revenue), "junior", DEFAULT_CONFIG).traffic == traffic


def test_evaluate_quarter_numbers() -> None:
    result = evaluate_quarter(D("40000"), "junior", DEFAULT_CONFIG)
    assert result.breakdown.commission == D("3700.00")
    assert result.fixed_pay == D("9000.00")
    assert result.employer_cost == D("17121.00")  # 12.700 x 1,23 + 1.500
    assert result.margin == D("22879.00")
    assert result.margin_percent == D("57.20")


def test_break_even_and_target_revenue() -> None:
    # Break-even Junior (Band 10.000-15.000): R = 11.340 / (1 - 0,123) = 12.930,44
    assert break_even_revenue(JUNIOR, G) == D("12930.44")
    # Ziel-Marge 50 % (Band > 30.000): R = 10.233 / (0,5 - 0,1722) = 31.217,20
    assert abs(target_revenue(JUNIOR, G) - D("31217.20")) <= D("0.01")
    for rank in DEFAULT_CONFIG.ranks:
        be = break_even_revenue(rank, G)
        at_be = evaluate_quarter(be, rank.key, DEFAULT_CONFIG)
        assert abs(at_be.margin) <= D("0.02"), rank.key
        target = target_revenue(rank, G)
        at_target = evaluate_quarter(target, rank.key, DEFAULT_CONFIG)
        assert abs(at_target.margin_percent - G.target_margin) <= D("0.01"), rank.key
        assert be < target
    # hoehere Raenge haben hoehere Fixkosten, also hoehere Schwellen
    breaks = [break_even_revenue(r, G) for r in DEFAULT_CONFIG.ranks]
    assert breaks == sorted(breaks)


def test_values_come_from_the_configuration() -> None:
    cheap = replace(G, employer_factor=D("1.00"), extra_cost_monthly=D("0"), target_margin=D("40"))
    config = CommissionConfig(cheap, DEFAULT_CONFIG.ranks)
    assert employer_cost_for_quarter(JUNIOR, D("0"), cheap) == D("9000.00")
    assert evaluate_quarter(D("0"), "junior", config).employer_cost == D("9000.00")
    # Ohne Arbeitgeberanteil und Zusatzkosten decken 9.000 EUR Umsatz das Fixgehalt (unter der
    # Freigrenze fallen keine Provisionen an).
    assert break_even_revenue(JUNIOR, cheap) == D("9000.00")
    assert break_even_revenue(JUNIOR, cheap) < break_even_revenue(JUNIOR, G)


# --- Befoerderungs-Kaskade ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("revenue", "start", "expected"),
    [
        ("29999.99", "junior", None),
        ("30000", "junior", "consultant"),  # Huerde 30.000 erreicht
        ("45000", "junior", "specialist"),  # 30.000 -> 40.000 -> bei 55.000 Schluss
        ("200000", "junior", "director"),  # Kaskade ueber alle Raenge
        ("79999", "senior", None),
        ("80000", "senior", "principal"),
        ("500000", "director", None),  # Director: keine Befoerderung
        ("200000", "principal", "director"),
    ],
)
def test_promotion_cascade(revenue: str, start: str, expected: str | None) -> None:
    assert promoted_rank_key(D(revenue), start, DEFAULT_CONFIG) == expected
    assert evaluate_quarter(D(revenue), start, DEFAULT_CONFIG).promotion_to == expected


# --- Konfigurationspruefung --------------------------------------------------------------------


def _with(rank_index: int = 0, **changes: object) -> CommissionConfig:
    ranks = list(DEFAULT_CONFIG.ranks)
    ranks[rank_index] = replace(ranks[rank_index], **changes)  # type: ignore[arg-type]
    return CommissionConfig(G, tuple(ranks))


@pytest.mark.parametrize(
    "config",
    [
        _with(threshold1=D("30000")),  # Schwelle 1 nicht kleiner als Schwelle 2
        _with(1, threshold2=D("30000")),  # Huerde nicht hoeher als beim Rang davor
        _with(rate1=D("101")),
        _with(fixed_monthly=D("-1")),
        CommissionConfig(replace(G, employer_factor=D("0.9")), DEFAULT_CONFIG.ranks),
        CommissionConfig(replace(G, target_margin=D("96")), DEFAULT_CONFIG.ranks),
        CommissionConfig(replace(G, commission_free_base=D("-1")), DEFAULT_CONFIG.ranks),
        CommissionConfig(G, ()),
        CommissionConfig(
            G, (DEFAULT_CONFIG.ranks[0], DEFAULT_CONFIG.ranks[0])
        ),  # doppelter Schluessel
        CommissionConfig(
            replace(G, target_margin=D("70")), DEFAULT_CONFIG.ranks
        ),  # frisst die Marge
    ],
)
def test_invalid_configurations_are_rejected(config: CommissionConfig) -> None:
    with pytest.raises(ConfigError):
        validate_config(config)


def test_general_config_defaults_are_a_fresh_value_object() -> None:
    assert GeneralConfig() == G
