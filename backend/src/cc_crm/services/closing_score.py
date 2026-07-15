from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.enums import ClosingStatus
from cc_crm.models.region_modifier import RegionModifier

# Gates: Kandidat gilt als nicht platzierbar (STOP), egal wie die anderen
# Dimensionen ausfallen, sobald Markt-Fit oder Entscheidungsklarheit sehr
# niedrig sind.
_STOP_GATE_MAX = 1

_THRESHOLDS: list[tuple[float, ClosingStatus]] = [
    (80.0, ClosingStatus.HOT),
    (65.0, ClosingStatus.WARM),
    (50.0, ClosingStatus.RISK),
]


class ClosingScoreService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def region_modifier(self, postal_code: str | None) -> float:
        """Laengste passende PLZ-Praefix-Konfiguration aus region_modifiers,
        0.0 falls kein Eintrag passt oder keine PLZ vorliegt."""
        if not postal_code:
            return 0.0
        entries = self.session.scalars(select(RegionModifier)).all()
        best: RegionModifier | None = None
        for entry in entries:
            if postal_code.startswith(entry.plz_prefix) and (
                best is None or len(entry.plz_prefix) > len(best.plz_prefix)
            ):
                best = entry
        return best.modifier if best is not None else 0.0

    def calculate(
        self,
        *,
        pain_staerke: int,
        entscheidungsklarheit: int,
        markt_fit: int,
        momentum: int | None,
        postal_code: str | None,
    ) -> tuple[float, ClosingStatus]:
        modifier = self.region_modifier(postal_code)
        effektiver_markt_fit = min(5.0, max(0.0, markt_fit + modifier))
        momentum_value = momentum if momentum is not None else 0
        raw = (
            (pain_staerke + entscheidungsklarheit + effektiver_markt_fit + momentum_value)
            / 20
            * 100
        )
        probability = round(min(100.0, max(0.0, raw)), 1)

        if markt_fit <= _STOP_GATE_MAX or entscheidungsklarheit <= _STOP_GATE_MAX:
            return probability, ClosingStatus.STOP

        for threshold, status in _THRESHOLDS:
            if probability >= threshold:
                return probability, status
        return probability, ClosingStatus.STOP


ACTION_RECOMMENDATIONS = {
    ClosingStatus.HOT: "Fokus tägliche Führung",
    ClosingStatus.WARM: "Markt verbreiten",
    ClosingStatus.RISK: "Nachschärfen oder stoppen",
    ClosingStatus.STOP: "Kein CV OUT",
}
