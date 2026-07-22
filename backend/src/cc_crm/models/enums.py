from enum import StrEnum


class CandidateStatus(StrEnum):
    ACTIVE = "active"
    PASSIVE = "passive"
    PLACED = "placed"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class ClientStatus(StrEnum):
    """Ampel-Logik fürs Beziehungsstatus-Tracking (Nutzer-Vorgabe):
    - ACTIVE (grün): aktive Kundenbeziehung.
    - ACQUISITION (gelb): in Verhandlung oder Status unklar.
    - PROSPECT (grau): noch keine Kundenbeziehung - z.B. frisch recherchierte
      Standorte großer Netzwerke (PWC, BRL, ...), bei denen noch kein
      tatsächlicher Kontakt bestand. Da wir laufend viele weitere Kanzleien
      ergänzen, landet hier bewusst der Großteil neuer Einträge als Standard.
    - BLOCKED (rot): kein Kontakt / "do not touch".
    - ARCHIVED (grau, wie PROSPECT): Beziehung war aktiv, ist aber beendet/
      nicht mehr relevant - inhaltlich verschieden von PROSPECT (nie
      angefangen vs. beendet), visuell aber ebenfalls neutral/grau.
    Status ist jederzeit manuell im CRM änderbar (Kanzlei bearbeiten -> Status)."""

    ACTIVE = "active"
    ACQUISITION = "acquisition"
    PROSPECT = "prospect"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class HonorarStufe(StrEnum):
    """Honorar-Stufe je Kanzlei-Zahlungsfähigkeit/-größe.

    Richtwerte (Startpunkt, bei Bedarf anpassbar):
    - STANDARD (27 %): größere/etablierte Kanzleien, reguläre Zahlungsfähigkeit
    - NACHLASS_1 (25 %): kleinere Kanzleien mit spürbar begrenztem Budget
    - NACHLASS_2 (23 %, Platzhalter): sehr kleine/Einzelkanzleien, deutlich
      eingeschränkte Zahlungsfähigkeit
    - INDIVIDUELL: abweichende, individuell verhandelte Konditionen
    """

    STANDARD = "standard"
    NACHLASS_1 = "nachlass_1"
    NACHLASS_2 = "nachlass_2"
    INDIVIDUELL = "individuell"


class Anrede(StrEnum):
    """Grammatikalisches Geschlecht des Kandidaten für die Profilgenerierung
    (z.B. "Kandidatin"/"Kandidat" + passende Pronomen im Anonymen Profil)."""

    FRAU = "frau"
    HERR = "herr"
    DIVERS = "divers"


class JobStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    ON_HOLD = "on_hold"
    FILLED = "filled"
    CLOSED = "closed"


class SubmissionStatus(StrEnum):
    PITCH = "pitch"
    QUALIFICATION_CALL = "qualification_call"
    CV_IN = "cv_in"
    CV_OUT = "cv_out"
    INTERVIEW = "interview"
    OFFER = "offer"
    PLACEMENT = "placement"
    CANCELLED = "cancelled"


class SubmissionCancellationReason(StrEnum):
    CANDIDATE_REJECTED = "candidate_rejected"
    CLIENT_REJECTED = "client_rejected"
    CANDIDATE_GHOSTING = "candidate_ghosting"


class FeedbackType(StrEnum):
    CLIENT = "client"
    CANDIDATE = "candidate"
    INTERNAL = "internal"


class InterviewStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class OfferStatus(StrEnum):
    DRAFT = "draft"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"


class PlacementStatus(StrEnum):
    PLANNED = "planned"
    STARTED = "started"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    DUE = "due"
    PAID = "paid"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ClosingStatus(StrEnum):
    """Ergebnis des Closing-Probability-Modells (Quali-Call-Scoring)."""

    HOT = "hot"
    WARM = "warm"
    RISK = "risk"
    STOP = "stop"


class CalendarEventType(StrEnum):
    """Typ eines Kalender-Termins (siehe models/calendar_event.py) - bewusst
    knapp gehalten (kein generisches Tagging-System), da die drei Werte den
    tatsaechlichen Terminarten im Recruiting-Alltag entsprechen."""

    INTERVIEW = "interview"
    QUALI_CALL = "quali_call"
    OTHER = "other"


class WarrantyStatus(StrEnum):
    """Gewährleistungsstatus eines Placements, berechnet aus
    start_date + guarantee_period_months (siehe services/warranty.py)."""

    LAUFEND = "laufend"
    BALD_ABLAUFEND = "bald_ablaufend"
    ABGELAUFEN = "abgelaufen"
