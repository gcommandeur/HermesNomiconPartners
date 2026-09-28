from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KpiPointRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Admin-konfigurierbares Punkte-System (Auftrag "Geschaeftsfuehrer-
    Ansicht + KPI-Punkte-System + Live-Ranking"): ein Datensatz pro Stufe
    der bestehenden 6-stufigen Kennzahlen-Pipeline (STAGE_ORDER in
    frontend/src/lib/stage-labels.ts, deckungsgleich mit SubmissionStatus
    ausser CANCELLED) plus "pitch" fuer die vorgelagerte Pitch/InMail-Stufe
    (PITCH_LABEL, siehe services/kpi_scoring.py::STAGE_KEYS) - macht daraus
    zusammen die "konsolidierte 7-Stufen-Pipeline", die an mehreren Stellen
    im Code bereits so benannt wird (z.B. CandidatePitchLog-Docstring).

    `points` ist beim ersten Migrations-Lauf fuer JEDE Stufe bewusst 0
    vorbelegt (Nutzer-Vorgabe: "wird noch definiert" - echte Platzhalter
    statt geratener Werte), bis der Nutzer sie im neuen Admin-Bereich
    (Einstellungen -> KPI-Punkte) selbst eintraegt. `stage` ist ein freier
    String (kein DB-Enum) mit siebenmal genau einer Zeile - passt zum sonst
    in diesem Codebase ueblichen Muster loser String-Referenzen (siehe
    MailingGroup.template_key) statt eines DB-Enums, das bei einer
    spaeteren Pipeline-Aenderung eine eigene Migration braeuchte."""

    __tablename__ = "kpi_point_rules"

    stage: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
