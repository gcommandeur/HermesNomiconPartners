# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Provisionsmodell als REINE Rechenfunktionen (keine Datenbank, keine Uhr).

Startwerte stammen aus der Excel "Nomicon_Provisionsmodell" (Nutzerauftrag 2026-10-11) und sind in
`DEFAULT_CONFIG` hinterlegt - alles ist einstellbar (services/commission_settings.py). Die Excel
selbst liegt dieser Umgebung NICHT vor; die folgenden Annahmen sind aus den Beschreibungen
abgeleitet und im Bericht an den Nutzer als offene Fragen aufgefuehrt:

1. Gestaffelt (marginal) je Quartal und Mitarbeiter, Schwellen bezogen auf den GESAMTEN
   Quartalsumsatz R. Die ersten `commission_free_base` (10.000 EUR) bringen keine Provision. Dann
   gilt Stufe 1 von der Freigrenze bis Schwelle 1, Stufe 2 bis Schwelle 2, Stufe 3 darueber:
   Provision = Satz1 * (min(R, S1) - F) + Satz2 * (min(R, S2) - max(S1, F))
               + Satz3 * (R - max(S2, F)), jeweils nicht negativ (F = Freigrenze).
2. Kosten je Quartal = (3 * Fixgehalt + Provision) * Arbeitgeber-Faktor + 3 * Zusatzkosten.
3. Marge = Umsatz - Kosten; Ampel: gruen ab Ziel-Marge, gelb ab Break-even, rot darunter.
   Break-even = Umsatz, bei dem die Marge 0 ist; Ziel-Umsatz = Umsatz fuer die Ziel-Marge.
4. Befoerderung: Erreicht der Quartalsumsatz die Schwelle 2 des Rangs ("zugleich
   Befoerderungshuerde"), steigt der Mitarbeiter auf; die Kaskade prueft danach den naechsten Rang
   usw., bis die Huerde nicht mehr erreicht wird oder es keinen hoeheren Rang gibt (Director: keine
   Befoerderung).
5. (Karriereplan Oktober 2026) Das Fixgehalt steht je JAHR im Modell; der Quartalswert ist ein
   Viertel. Der Vermittlungsbonus (300 EUR je Deal, getrennt einstellbar fuer Vermittlung und
   Ueberlassung) ist NICHT Teil des provisionspflichtigen Umsatzes: Brutto im Quartal = Fix +
   Provision + Bonus. Er zaehlt als Gehaltsbestandteil in die Arbeitgeberkosten. Break-even und
   Ziel-Umsatz rechnen ohne Bonus.
Die Honorarparameter (Honorarsatz auf Zielgehalt 28 %, Mindesthonorar 12.000 EUR) sind hinterlegt
und einstellbar, gehen aber NICHT in die Provisionsrechnung ein."""

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

CENT = Decimal("0.01")
HUNDRED = Decimal("100")
MONTHS_PER_QUARTER = 3
QUARTERS_PER_YEAR = 4


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class RankConfig:
    key: str
    label: str
    fixed_yearly: Decimal  # Fixgehalt je Jahr (brutto); der Quartalswert ist ein Viertel
    rate1: Decimal  # Prozent
    threshold1: Decimal  # Quartalsumsatz, bis zu dem Satz 1 gilt
    rate2: Decimal
    threshold2: Decimal  # Quartalsumsatz, bis zu dem Satz 2 gilt (zugleich Befoerderungshuerde)
    rate3: Decimal


@dataclass(frozen=True)
class GeneralConfig:
    commission_free_base: Decimal = Decimal("10000")  # Umsatz ohne Provision je Quartal
    employer_factor: Decimal = Decimal("1.23")  # Arbeitgeberkosten auf Gehalt und Provision
    extra_cost_monthly: Decimal = Decimal("500")  # Zusatzkosten je Monat und Kopf
    fee_rate_on_target_salary: Decimal = Decimal("28")  # Prozent (nur hinterlegt)
    min_fee: Decimal = Decimal("12000")  # Mindesthonorar (nur hinterlegt)
    target_margin: Decimal = Decimal("50")  # Prozent
    placement_bonus: Decimal = Decimal("300")  # EUR je Vermittlungs-Deal (Fee bezahlt)
    staffing_bonus: Decimal = Decimal("300")  # EUR je Ueberlassungs-Deal (Einsatz/Verlaengerung)


@dataclass(frozen=True)
class RevenueBasis:
    """Was als Umsatz zaehlt (OFFEN, vom Nutzer zu bestaetigen; Annahme siehe Kopf)."""

    placement_fees: str = "paid"  # "paid" = nur bezahlte, "issued" = ab Rechnung gestellt
    include_staffing: bool = True  # Ueberlassungsrechnungen mitzaehlen
    staffing: str = "issued"  # "issued" = ab gestellt (AÜ-Rechnungssumme), "paid" = nur bezahlte


@dataclass(frozen=True)
class CommissionConfig:
    general: GeneralConfig
    ranks: tuple[RankConfig, ...]  # aufsteigend: niedrigster Rang zuerst
    revenue_basis: RevenueBasis = RevenueBasis()

    def rank(self, key: str) -> RankConfig:
        for rank in self.ranks:
            if rank.key == key:
                return rank
        raise KeyError(key)

    def index(self, key: str) -> int:
        for position, rank in enumerate(self.ranks):
            if rank.key == key:
                return position
        raise KeyError(key)


def _rank(
    key: str, label: str, fixed: int, r1: str, t1: int, r2: str, t2: int, r3: str
) -> RankConfig:
    return RankConfig(
        key, label, Decimal(fixed), Decimal(r1), Decimal(t1), Decimal(r2), Decimal(t2), Decimal(r3)
    )


# Startwerte laut Karriereplan (Oktober 2026), alles im Admin-Bereich aenderbar. Den Rang "Junior"
# gibt es nicht mehr.
DEFAULT_CONFIG = CommissionConfig(
    general=GeneralConfig(),
    ranks=(
        _rank("consultant", "Consultant", 40000, "10", 25000, "12", 48000, "14"),
        _rank("specialist", "Specialist Consultant", 42000, "15", 30000, "17.5", 60000, "20"),
        _rank("senior", "Senior Consultant", 44000, "20", 35000, "22.5", 96000, "25"),
        _rank("manager", "Manager", 50000, "25", 45000, "27.5", 120000, "30"),
        _rank("principal", "Principal", 54000, "30", 60000, "32.5", 144000, "35"),
        _rank("director", "Director", 60000, "35", 85000, "37.5", 168000, "40"),
    ),
)


class Traffic(StrEnum):
    GREEN = "green"  # Marge mindestens Ziel-Marge
    YELLOW = "yellow"  # ueber Break-even, unter Ziel
    RED = "red"  # unter Break-even


@dataclass(frozen=True)
class CommissionBreakdown:
    revenue: Decimal
    free_base: Decimal
    band1_revenue: Decimal  # provisionspflichtiger Umsatz je Stufe
    band2_revenue: Decimal
    band3_revenue: Decimal
    band1_commission: Decimal
    band2_commission: Decimal
    band3_commission: Decimal
    commission: Decimal


def commission_for_quarter(
    revenue: Decimal, rank: RankConfig, general: GeneralConfig
) -> CommissionBreakdown:
    """Gestaffelte Provision fuer einen Quartalsumsatz (Annahme 1 im Modulkopf)."""
    free = general.commission_free_base
    revenue = max(revenue, Decimal("0"))
    band1 = max(Decimal("0"), min(revenue, rank.threshold1) - free)
    band2 = max(Decimal("0"), min(revenue, rank.threshold2) - max(rank.threshold1, free))
    band3 = max(Decimal("0"), revenue - max(rank.threshold2, free))
    c1 = band1 * rank.rate1 / HUNDRED
    c2 = band2 * rank.rate2 / HUNDRED
    c3 = band3 * rank.rate3 / HUNDRED
    return CommissionBreakdown(
        revenue=revenue,
        free_base=free,
        band1_revenue=band1,
        band2_revenue=band2,
        band3_revenue=band3,
        band1_commission=money(c1),
        band2_commission=money(c2),
        band3_commission=money(c3),
        commission=money(c1 + c2 + c3),
    )


def fixed_pay_for_quarter(rank: RankConfig) -> Decimal:
    return rank.fixed_yearly / QUARTERS_PER_YEAR


def bonus_for_quarter(general: GeneralConfig, placement_deals: int, staffing_deals: int) -> Decimal:
    """Vermittlungsbonus: einmalig je Deal, unabhaengig von der Dealgroesse und der Rolle."""
    return money(
        general.placement_bonus * max(placement_deals, 0)
        + general.staffing_bonus * max(staffing_deals, 0)
    )


def employer_cost_for_quarter(
    rank: RankConfig, commission: Decimal, general: GeneralConfig, bonus: Decimal = Decimal("0")
) -> Decimal:
    """Arbeitgeberkosten eines Quartals (Annahme 2 und 5 im Modulkopf)."""
    pay = fixed_pay_for_quarter(rank) + commission + bonus
    return money(pay * general.employer_factor + general.extra_cost_monthly * MONTHS_PER_QUARTER)


def margin(revenue: Decimal, cost: Decimal) -> tuple[Decimal, Decimal | None]:
    """(Marge in EUR, Marge in Prozent des Umsatzes; None bei Umsatz 0)."""
    amount = money(revenue - cost)
    if revenue <= 0:
        return amount, None
    return amount, (amount / revenue * HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)


def traffic_light(revenue: Decimal, cost: Decimal, general: GeneralConfig) -> Traffic:
    amount, percent = margin(revenue, cost)
    if amount < 0 or percent is None:
        return Traffic.RED
    return Traffic.GREEN if percent >= general.target_margin else Traffic.YELLOW


def revenue_for_margin(
    rank: RankConfig, general: GeneralConfig, target_margin_percent: Decimal
) -> Decimal:
    """Quartalsumsatz, bei dem die Marge genau `target_margin_percent` betraegt (0 = Break-even).

    Loesung per Intervallhalbierung auf `R*(1-m) - Kosten(R) = 0`. Die Funktion ist streng steigend,
    solange `Satz_max * Arbeitgeber-Faktor < 1 - m` (das prueft die Konfigurationsvalidierung)."""
    share = Decimal(1) - target_margin_percent / HUNDRED

    def gap(value: Decimal) -> Decimal:
        commission = commission_for_quarter(value, rank, general).commission
        return value * share - employer_cost_for_quarter(rank, commission, general)

    low, high = Decimal("0"), Decimal("1000000000")
    if gap(high) <= 0:
        return high
    for _ in range(90):
        middle = (low + high) / 2
        if gap(middle) < 0:
            low = middle
        else:
            high = middle
    return money(high)


def break_even_revenue(rank: RankConfig, general: GeneralConfig) -> Decimal:
    return revenue_for_margin(rank, general, Decimal("0"))


def target_revenue(rank: RankConfig, general: GeneralConfig) -> Decimal:
    return revenue_for_margin(rank, general, general.target_margin)


def promoted_rank_key(revenue: Decimal, rank_key: str, config: CommissionConfig) -> str | None:
    """Rang nach der Befoerderungs-Kaskade (Annahme 4) oder None, wenn keine Befoerderung folgt."""
    position = config.index(rank_key)
    start = position
    while position < len(config.ranks) - 1 and revenue >= config.ranks[position].threshold2:
        position += 1
    return None if position == start else config.ranks[position].key


@dataclass(frozen=True)
class QuarterResult:
    rank_key: str
    revenue: Decimal
    breakdown: CommissionBreakdown
    fixed_pay: Decimal
    placement_deals: int
    staffing_deals: int
    bonus: Decimal
    gross: Decimal  # Fix + Provision + Bonus
    employer_cost: Decimal
    margin: Decimal
    margin_percent: Decimal | None
    break_even_revenue: Decimal
    target_revenue: Decimal
    traffic: Traffic
    promotion_to: str | None


def evaluate_quarter(
    revenue: Decimal,
    rank_key: str,
    config: CommissionConfig,
    placement_deals: int = 0,
    staffing_deals: int = 0,
) -> QuarterResult:
    rank = config.rank(rank_key)
    general = config.general
    breakdown = commission_for_quarter(revenue, rank, general)
    bonus = bonus_for_quarter(general, placement_deals, staffing_deals)
    cost = employer_cost_for_quarter(rank, breakdown.commission, general, bonus)
    amount, percent = margin(breakdown.revenue, cost)
    fixed = money(fixed_pay_for_quarter(rank))
    return QuarterResult(
        rank_key=rank_key,
        revenue=breakdown.revenue,
        breakdown=breakdown,
        fixed_pay=fixed,
        placement_deals=placement_deals,
        staffing_deals=staffing_deals,
        bonus=bonus,
        gross=money(fixed + breakdown.commission + bonus),
        employer_cost=cost,
        margin=amount,
        margin_percent=percent,
        break_even_revenue=break_even_revenue(rank, general),
        target_revenue=target_revenue(rank, general),
        traffic=traffic_light(breakdown.revenue, cost, general),
        promotion_to=promoted_rank_key(breakdown.revenue, rank_key, config),
    )


class ConfigError(ValueError):
    """Ungueltige Konfiguration (mit deutscher Meldung)."""


def validate_config(config: CommissionConfig) -> CommissionConfig:
    general = config.general
    if not config.ranks:
        raise ConfigError("Es braucht mindestens eine Stufe.")
    keys = [rank.key for rank in config.ranks]
    if len(set(keys)) != len(keys) or any(not key.strip() for key in keys):
        raise ConfigError("Rang-Schluessel muessen eindeutig und nicht leer sein.")
    for value, name in (
        (general.commission_free_base, "Umsatz ohne Provision"),
        (general.extra_cost_monthly, "Zusatzkosten"),
        (general.min_fee, "Mindesthonorar"),
        (general.placement_bonus, "Vermittlungsbonus"),
        (general.staffing_bonus, "Ueberlassungsbonus"),
    ):
        if value < 0:
            raise ConfigError(f"{name} darf nicht negativ sein.")
    if general.employer_factor < 1 or general.employer_factor > 3:
        raise ConfigError("Der Arbeitgeber-Faktor muss zwischen 1 und 3 liegen.")
    if not Decimal("0") <= general.fee_rate_on_target_salary <= HUNDRED:
        raise ConfigError("Der Honorarsatz muss zwischen 0 und 100 Prozent liegen.")
    if not Decimal("0") <= general.target_margin < Decimal("95"):
        raise ConfigError("Die Ziel-Marge muss zwischen 0 und unter 95 Prozent liegen.")
    previous: RankConfig | None = None
    for rank in config.ranks:
        if rank.fixed_yearly < 0:
            raise ConfigError(f"{rank.label}: Fixgehalt darf nicht negativ sein.")
        for rate in (rank.rate1, rank.rate2, rank.rate3):
            if not Decimal("0") <= rate <= HUNDRED:
                raise ConfigError(
                    f"{rank.label}: Saetze muessen zwischen 0 und 100 Prozent liegen."
                )
        if not Decimal("0") <= rank.threshold1 < rank.threshold2:
            raise ConfigError(f"{rank.label}: Schwelle 1 muss kleiner als Schwelle 2 sein.")
        if previous is not None and rank.threshold2 <= previous.threshold2:
            raise ConfigError(
                f"{rank.label}: Die Befoerderungshuerde muss hoeher sein als beim Rang davor."
            )
        previous = rank
        # Der Break-even ist nur eindeutig, wenn jeder zusaetzliche Euro Umsatz mehr bringt, als er
        # an Provision samt Arbeitgeberanteil kostet.
        top_rate = max(rank.rate1, rank.rate2, rank.rate3) / HUNDRED
        if top_rate * general.employer_factor >= Decimal(1) - general.target_margin / HUNDRED:
            raise ConfigError(
                f"{rank.label}: Provisionssatz und Ziel-Marge passen nicht zusammen "
                "(Provision samt Arbeitgeberanteil frisst die Marge auf)."
            )
    return config


def with_rank_changes(config: CommissionConfig, ranks: tuple[RankConfig, ...]) -> CommissionConfig:
    return replace(config, ranks=ranks)
