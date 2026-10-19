# NOMICON: Ansicht "Gesamt" (Geschaeftsfuehrung) - nur in der Nomicon-Kopie.
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

Period = Literal["week", "month", "quarter"]


class GrossProfitRead(BaseModel):
    direct: Decimal  # bezahlte Vermittlungshonorare im Zeitraum
    staffing: Decimal  # Marge freigegebener Stunden im Zeitraum
    total: Decimal
    staffing_hours: Decimal
    staffing_missing_rates: int  # freigegebene Stundenzettel ohne Satz oder Lohn (nicht enthalten)


class ForecastRead(BaseModel):
    direct_weighted: Decimal
    direct_without_probability: int
    direct_without_fee: int
    staffing_margin: Decimal
    staffing_counted: int
    staffing_excluded: int
    total: Decimal


class BothBusinessClientRead(BaseModel):
    client_id: uuid.UUID
    client_name: str
    processes: int
    assignments: int
    placements: int
    taken_over: (
        int  # Vermittlungen an Kandidaten, die dort zuvor oder gleichzeitig eingesetzt waren
    )


class TakeoverRateRead(BaseModel):
    pairs: int  # (Leiharbeitnehmer, Kunde)-Paare mit Einsatz
    taken_over: int
    rate: Decimal | None  # 0 bis 1, None ohne Paare


class ManagementAlertRead(BaseModel):
    kind: Literal[
        "deadline_red",
        "deadline_yellow",
        "license",
        "invoices_overdue",
        "processes_without_owner",
    ]
    severity: Literal["red", "yellow"]
    count: int
    text: str
    href: str


class ManagementOverviewRead(BaseModel):
    period: Period
    date_from: date
    date_to: date
    employer_factor: Decimal
    gross_profit: GrossProfitRead
    forecast: ForecastRead
    both_business_clients: list[BothBusinessClientRead]
    takeover: TakeoverRateRead
    alerts: list[ManagementAlertRead]
    assumptions: list[str]
