# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Rechenkern des Provisionsmodells nach dem Karriereplan (Oktober 2026). Die erwarteten Werte sind
von Hand nach den dokumentierten Regeln (services/commission_model.py, Kopf) gerechnet; die zwei
Beispiele der Praesentation sind enthalten. Stimmt eine Zahl nicht, ist das zu melden, nicht der
Test anzupassen."""

from dataclasses import replace
from decimal import Decimal

import pytest

from cc_crm.services.commission_model import (
    DEFAULT_CONFIG,
    CommissionConfig,
    ConfigError,
    GeneralConfig,
    Traffic,
    bonus_for_quarter,
    break_even_revenue,
    commission_for_quarter,
    employer_cost_for_quarter,
    evaluate_quarter,
    fixed_pay_for_quarter,
    margin,
    promoted_rank_key,
    target_revenue,
    validate_config,
)

D = Decimal
G = DEFAULT_CONFIG.general
CONSULTANT = DEFAULT_CONFIG.rank("consultant")


def commission(revenue: str, rank: str = "consultant") -> Decimal:
    return commission_for_quarter(D(revenue), DEFAULT_CONFIG.rank(rank), G).commission


# --- Startwerte laut Karriereplan ---------------------------------------------------------------


def test_default_values_match_the_career_plan() -> None:
    assert G.commission_free_base == 10000
    assert G.placement_bonus == 300 and G.staffing_bonus == 300
    table = {
        r.key: (r.label, r.fixed_yearly, r.rate1, r.threshold1, r.rate2, r.threshold2, r.rate3)
        for r in DEFAULT_CONFIG.ranks
    }
    assert table == {
        "consultant": ("Consultant", 40000, 10, 25000, 12, 48000, 14),
        "specialist": ("Specialist Consultant", 42000, 15, 30000, D("17.5"), 60000, 20),
        "senior": ("Senior Consultant", 44000, 20, 35000, D("22.5"), 96000, 25),
        "manager": ("Manager", 50000, 25, 45000, D("27.5"), 120000, 30),
        "principal": ("Principal", 54000, 30, 60000, D("32.5"), 144000, 35),
        "director": ("Director", 60000, 35, 85000, D("37.5"), 168000, 40),
    }
    assert [r.key for r in DEFAULT_CONFIG.ranks][0] == "consultant"  # aufsteigend, kein Junior
    assert "junior" not in {r.key for r in DEFAULT_CONFIG.ranks}
    assert validate_config(DEFAULT_CONFIG) is DEFAULT_CONFIG


def test_fixed_pay_is_a_quarter_of_the_yearly_value() -> None:
    assert fixed_pay_for_quarter(CONSULTANT) == D("10000")
    assert fixed_pay_for_quarter(DEFAULT_CONFIG.rank("manager")) == D("12500")


# --- Gestaffelte Provision ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("revenue", "expected"),
    [
        ("0", "0.00"),
        ("9999.99", "0.00"),
        ("10000", "0.00"),  # die ersten 10.000 EUR ohne Provision
        ("15000", "500.00"),  # 5.000 x 10 %
        ("25000", "1500.00"),  # 15.000 x 10 %
        ("30000", "2100.00"),  # 1.500 + 5.000 x 12 %
        ("36000", "2820.00"),  # 1.500 + 11.000 x 12 %  (Beispiel der Praesentation)
        ("48000", "4260.00"),  # 1.500 + 23.000 x 12 %
        ("60000", "5940.00"),  # 4.260 + 12.000 x 14 %
        ("-500", "0.00"),  # negativer Umsatz (Stornos) gibt keine Provision
    ],
)
def test_staggered_commission_consultant(revenue: str, expected: str) -> None:
    assert commission(revenue) == D(expected)


def test_commission_breakdown_by_band() -> None:
    result = commission_for_quarter(D("60000"), CONSULTANT, G)
    assert (result.band1_revenue, result.band2_revenue, result.band3_revenue) == (
        15000,
        23000,
        12000,
    )
    assert (result.band1_commission, result.band2_commission, result.band3_commission) == (
        D("1500.00"),
        D("2760.00"),
        D("1680.00"),
    )
    assert result.commission == D("5940.00")


def test_commission_is_continuous_and_monotonic_at_every_threshold() -> None:
    for rank in DEFAULT_CONFIG.ranks:
        previous = D("0")
        for revenue in range(0, 250001, 500):
            current = commission_for_quarter(D(revenue), rank, G).commission
            assert current >= previous, (rank.key, revenue)
            previous = current
        for threshold in (rank.threshold1, rank.threshold2):
            below = commission_for_quarter(threshold - D("0.01"), rank, G).commission
            above = commission_for_quarter(threshold + D("0.01"), rank, G).commission
            assert above - below < D("0.05"), (rank.key, threshold)  # kein Sprung


def test_commission_other_ranks() -> None:
    # Manager bei 96.000 (Beispiel der Praesentation): 35.000 x 25 % + 51.000 x 27,5 %
    assert commission("96000", "manager") == D("22775.00")
    # Director bei 100.000: 75.000 x 35 % = 26.250 + 15.000 x 37,5 % = 5.625
    assert commission("100000", "director") == D("31875.00")
    # Senior Consultant bei 120.000: 25.000 x 20 % + 61.000 x 22,5 % + 24.000 x 25 %
    assert commission("120000", "senior") == D("24725.00")


def test_free_base_above_threshold1_skips_band1() -> None:
    general = replace(G, commission_free_base=D("30000"))
    result = commission_for_quarter(D("40000"), CONSULTANT, general)
    assert result.band1_revenue == 0
    assert result.band2_revenue == D("10000")  # von 30.000 bis 40.000
    assert result.commission == D("1200.00")


# --- Beispiele der Praesentation (Karriereplan) --------------------------------------------------


def test_presentation_example_consultant() -> None:
    # Consultant, Quartalsumsatz 36.000, 3 Vermittlungen: 2.820 + 900 + 10.000 = 13.720
    result = evaluate_quarter(D("36000"), "consultant", DEFAULT_CONFIG, placement_deals=3)
    assert result.breakdown.commission == D("2820.00")
    assert result.bonus == D("900.00")
    assert result.fixed_pay == D("10000.00")
    assert result.gross == D("13720.00")


def test_presentation_example_manager() -> None:
    # Manager, Quartalsumsatz 96.000, 8 Vermittlungen (Vermittlung und Ueberlassung zusammen)
    result = evaluate_quarter(
        D("96000"), "manager", DEFAULT_CONFIG, placement_deals=5, staffing_deals=3
    )
    assert result.breakdown.commission == D("22775.00")
    assert result.bonus == D("2400.00")
    assert result.fixed_pay == D("12500.00")
    assert result.gross == D("37675.00")


def test_bonus_is_per_deal_and_configurable_separately() -> None:
    assert bonus_for_quarter(G, 0, 0) == 0
    assert bonus_for_quarter(G, 2, 1) == D("900.00")
    split = replace(G, placement_bonus=D("250"), staffing_bonus=D("400"))
    assert bonus_for_quarter(split, 2, 1) == D("900.00")  # 500 + 400
    assert bonus_for_quarter(split, -3, 0) == 0


def test_bonus_is_not_part_of_the_commissionable_revenue() -> None:
    without = evaluate_quarter(D("36000"), "consultant", DEFAULT_CONFIG)
    with_bonus = evaluate_quarter(D("36000"), "consultant", DEFAULT_CONFIG, placement_deals=3)
    assert with_bonus.breakdown.commission == without.breakdown.commission
    assert with_bonus.revenue == without.revenue
    # ... kostet aber (mit Arbeitgeberanteil) wie ein Gehaltsbestandteil
    assert with_bonus.employer_cost - without.employer_cost == D("1107.00")  # 900 x 1,23


# --- Kosten, Marge, Ampel --------------------------------------------------------------------


def test_employer_cost_and_margin() -> None:
    # 10.000 x 1,23 + 1.500
    assert employer_cost_for_quarter(CONSULTANT, D("0"), G) == D("13800.00")
    # 12.100 x 1,23 + 1.500
    assert employer_cost_for_quarter(CONSULTANT, D("2100"), G) == D("16383.00")
    assert margin(D("30000"), D("16383")) == (D("13617.00"), D("45.39"))
    assert margin(D("0"), D("13800")) == (D("-13800.00"), None)


@pytest.mark.parametrize(
    ("revenue", "traffic"),
    [
        ("0", Traffic.RED),
        ("14000", Traffic.RED),  # unter dem Break-even (14.332,96)
        ("20000", Traffic.YELLOW),  # Marge 24,85 %
        ("60000", Traffic.GREEN),  # Marge 64,82 %
    ],
)
def test_traffic_light(revenue: str, traffic: Traffic) -> None:
    assert evaluate_quarter(D(revenue), "consultant", DEFAULT_CONFIG).traffic == traffic


def test_evaluate_quarter_numbers() -> None:
    result = evaluate_quarter(D("60000"), "consultant", DEFAULT_CONFIG)
    assert result.breakdown.commission == D("5940.00")
    assert result.fixed_pay == D("10000.00")
    assert result.employer_cost == D("21106.20")  # 15.940 x 1,23 + 1.500
    assert result.margin == D("38893.80")
    assert result.margin_percent == D("64.82")


def test_break_even_and_target_revenue() -> None:
    # Break-even Consultant (Band 10.000-25.000): R = 12.570 / (1 - 0,123) = 14.332,96
    assert break_even_revenue(CONSULTANT, G) == D("14332.96")
    # Ziel-Marge 50 % (Band 25.000-48.000): R = 11.955 / (0,5 - 0,1476) = 33.924,52
    assert abs(target_revenue(CONSULTANT, G) - D("33924.52")) <= D("0.01")
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
    assert employer_cost_for_quarter(CONSULTANT, D("0"), cheap) == D("10000.00")
    assert evaluate_quarter(D("0"), "consultant", config).employer_cost == D("10000.00")
    # Ohne Arbeitgeberanteil und Zusatzkosten decken 10.000 EUR Umsatz das Fixgehalt (unter der
    # Freigrenze fallen keine Provisionen an).
    assert break_even_revenue(CONSULTANT, cheap) == D("10000.00")
    assert break_even_revenue(CONSULTANT, cheap) < break_even_revenue(CONSULTANT, G)


# --- Befoerderungs-Kaskade ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("revenue", "start", "expected"),
    [
        ("47999.99", "consultant", None),
        ("48000", "consultant", "specialist"),  # Schwelle 2 des eigenen Rangs erreicht
        ("60000", "consultant", "senior"),  # 48.000 -> 60.000 erreicht -> bei 96.000 Schluss
        ("200000", "consultant", "director"),  # Kaskade ueber alle Raenge
        ("95999", "senior", None),
        ("96000", "senior", "manager"),
        ("119999", "manager", None),
        ("120000", "manager", "principal"),
        ("144000", "principal", "director"),
        ("500000", "director", None),  # Director: keine Befoerderung
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
        _with(threshold1=D("48000")),  # Schwelle 1 nicht kleiner als Schwelle 2
        _with(1, threshold2=D("48000")),  # Huerde nicht hoeher als beim Rang davor
        _with(rate1=D("101")),
        _with(fixed_yearly=D("-1")),
        CommissionConfig(replace(G, employer_factor=D("0.9")), DEFAULT_CONFIG.ranks),
        CommissionConfig(replace(G, target_margin=D("96")), DEFAULT_CONFIG.ranks),
        CommissionConfig(replace(G, commission_free_base=D("-1")), DEFAULT_CONFIG.ranks),
        CommissionConfig(replace(G, placement_bonus=D("-1")), DEFAULT_CONFIG.ranks),
        CommissionConfig(replace(G, staffing_bonus=D("-1")), DEFAULT_CONFIG.ranks),
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


# --- Stufen frei aenderbar: Verweise laufen ueber den Schluessel ---------------------------------


def test_ranks_can_be_renamed_reordered_added_and_removed_by_key() -> None:
    renamed = tuple(replace(r, label=f"Stufe {i}") for i, r in enumerate(DEFAULT_CONFIG.ranks))
    config = validate_config(CommissionConfig(G, renamed))
    # Verweis ueber den Schluessel, nicht ueber den Namen
    assert config.rank("manager").label == "Stufe 3"
    assert evaluate_quarter(D("96000"), "manager", config).breakdown.commission == D("22775.00")

    # eine Stufe hinzufuegen (zwischen Manager und Principal) und eine entfernen (Specialist)
    extra = replace(
        DEFAULT_CONFIG.rank("manager"),
        key="lead",
        label="Lead",
        threshold2=D("132000"),
    )
    ranks = [r for r in DEFAULT_CONFIG.ranks if r.key != "specialist"]
    ranks.insert([r.key for r in ranks].index("manager") + 1, extra)
    changed = validate_config(CommissionConfig(G, tuple(ranks)))
    assert [r.key for r in changed.ranks] == [
        "consultant",
        "senior",
        "manager",
        "lead",
        "principal",
        "director",
    ]
    assert promoted_rank_key(D("132000"), "lead", changed) == "principal"
    with pytest.raises(KeyError):
        changed.rank("specialist")  # entfernt: Aufrufer behandeln den Schluessel als "ohne Rang"


def test_general_config_defaults_are_a_fresh_value_object() -> None:
    assert GeneralConfig() == G
