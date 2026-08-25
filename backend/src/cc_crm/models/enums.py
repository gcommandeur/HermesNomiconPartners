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
    """Die "Pitch"-Stufe (vor QUALIFICATION_CALL) wurde bewusst wieder
    entfernt (Task #136 hatte sie eingefuehrt) - die Pipeline beginnt jetzt
    direkt bei QUALIFICATION_CALL. Bestehende Submissions/Feedback-Eintraege
    mit dem historischen Wert "pitch" wurden per Alembic-Migration auf
    QUALIFICATION_CALL migriert (siehe alembic/versions/
    c4d7e1a9f3b2_remove_pitch_submission_status.py)."""

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


class SourcingSourceType(StrEnum):
    """Quelle, aus der ein SourcingLead stammt (siehe models/sourcing_lead.py)."""

    STEUERBERATERVERZEICHNIS = "steuerberaterverzeichnis"
    WPK_BERUFSREGISTER = "wpk_berufsregister"
    BRAK_ANWALTSVERZEICHNIS = "brak_anwaltsverzeichnis"
    KANZLEI_TEAM_PAGE = "kanzlei_team_page"


class SourcingLeadStatus(StrEnum):
    """Review-Status eines SourcingLeads: Leads landen NIE direkt im
    Kandidatenbestand, sondern warten hier auf menschliche Bestaetigung
    (Datenqualitaet + Datenschutz - keine ungeprueften Personendaten in
    `candidates`). POSSIBLE_DUPLICATE: Fuzzy-Namensabgleich hat einen
    bestehenden Kandidaten nahegelegt - im Review separat sichtbar statt
    stillschweigend verworfen (koennte z.B. ein Arbeitgeberwechsel eines
    Bestandskandidaten sein)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSSIBLE_DUPLICATE = "possible_duplicate"


class SourcingRunStatus(StrEnum):
    """Laufzeit-Status eines SourcingRun (siehe models/sourcing_run.py) -
    aktuell nur fuer den Hintergrund-Lauf "alle Kanzleien scannen" befuellt,
    da nur dieser lange genug laeuft, um stopp-/anzeigebar sein zu muessen."""

    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"


class Rolle(StrEnum):
    """Normalisierte Berufsrollen-Taxonomie fuer Kandidaten (siehe
    Candidate.rollen) - feste 10 Zielrollen + SONSTIGE statt Freitext, damit
    z.B. eine Vakanzsuche nach "Steuerberater" auch Kandidaten findet, die
    das als EINE von mehreren gleichzeitig gueltigen Rollen tragen (z.B.
    Steuerberater UND Partner). Deshalb ist Candidate.rollen eine LISTE,
    kein Einzelwert - Rollen sind hier keine zeitliche Abfolge, sondern
    gleichzeitig gueltige Titel. Basiert auf einer Recherche zu aktuellen
    deutschen Stellenanzeigen/Berufsbildern fuer Steuer-/Wirtschaftspruefungs-
    /Rechtskanzleien (siehe cv_extraction.py-Prompt fuer die vollstaendige
    Abgrenzung zwischen den Werten)."""

    STEUERFACHANGESTELLTE = "steuerfachangestellte"
    STEUERFACHWIRT = "steuerfachwirt"
    BILANZBUCHHALTER = "bilanzbuchhalter"
    STEUERBERATER = "steuerberater"
    PARTNER = "partner"
    PRUEFUNGSASSISTENT = "pruefungsassistent"
    PRUEFUNGSLEITER = "pruefungsleiter"
    WIRTSCHAFTSPRUEFER = "wirtschaftspruefer"
    RECHTSFACHANGESTELLTE = "rechtsfachangestellte"
    RECHTSANWALT = "rechtsanwalt"
    SONSTIGE = "sonstige"


class Abschlussart(StrEnum):
    """Strukturierte Abschlussart(en) fuer Candidate.abschluesse - macht
    ausbildung_titel/qualification (Freitext, siehe cv_extraction.py-Prompt)
    filterbar (z.B. "alle mit Studium" oder "alle mit Berufsexamen"). Liste,
    da mehrere Abschlussarten gleichzeitig zutreffen koennen (z.B. Ausbildung
    UND spaeteres Studium UND Berufsexamen)."""

    AUSBILDUNG = "ausbildung"
    STUDIUM_BACHELOR = "studium_bachelor"
    STUDIUM_MASTER = "studium_master"
    STUDIUM_PROMOTION = "studium_promotion"
    BERUFSEXAMEN_STB = "berufsexamen_stb"
    BERUFSEXAMEN_WP = "berufsexamen_wp"
    BERUFSEXAMEN_RA = "berufsexamen_ra"
    FORTBILDUNG = "fortbildung"
    KEIN_ABSCHLUSS_ERKENNBAR = "kein_abschluss_erkennbar"


class Rechtsgebiet(StrEnum):
    """Strukturierte Rechtsgebiete fuer Candidate.rechtsgebiete - bei
    rechtsanwalt/rechtsfachangestellte reicht Freitext (fachliche_
    schwerpunkte) nicht zum Filtern. Liste, da mehrere Rechtsgebiete
    gleichzeitig zutreffen koennen."""

    ARBEITSRECHT = "arbeitsrecht"
    STEUERRECHT = "steuerrecht"
    GESELLSCHAFTSRECHT = "gesellschaftsrecht"
    HANDELSRECHT = "handelsrecht"
    VERTRAGSRECHT = "vertragsrecht"
    FAMILIENRECHT = "familienrecht"
    ERBRECHT = "erbrecht"
    INSOLVENZRECHT = "insolvenzrecht"
    IMMOBILIENRECHT = "immobilienrecht"
    IP_RECHT = "ip_recht"
    DATENSCHUTZRECHT = "datenschutzrecht"
    PROZESSRECHT = "prozessrecht"
    SONSTIGES = "sonstiges"


class WarrantyStatus(StrEnum):
    """Gewährleistungsstatus eines Placements, berechnet aus
    start_date + guarantee_period_months (siehe services/warranty.py)."""

    LAUFEND = "laufend"
    BALD_ABLAUFEND = "bald_ablaufend"
    ABGELAUFEN = "abgelaufen"


class MailDirection(StrEnum):
    """Richtung einer per IMAP eingelesenen bzw. per SMTP verschickten Mail
    (siehe models/mail.py). OUTBOUND ist noetig, weil der IMAP-Sync auch die
    eigenen, im Sent-Ordner liegenden Mails sieht - die duerfen NICHT als
    eingehende Aktivitaet verbucht werden."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MailMatchStatus(StrEnum):
    """Zuordnungsstand einer eingelesenen Mail zum CRM-Bestand.

    PENDING_REVIEW ist der bewusst haeufige Fall bei LinkedIn-Nachrichten von
    noch unbekannten Personen: es wird NIE automatisch ein Kandidat angelegt
    (gleiche Governance wie beim Sourcing-Lead-Review, siehe
    SourcingLeadStatus) - der Mensch entscheidet. UNMATCHED dagegen sind
    Mails, zu denen es keine sinnvolle Zuordnung geben kann (z.B.
    Newsletter): kein Review noetig, nur archiviert.
    """

    MATCHED = "matched"
    PENDING_REVIEW = "pending_review"
    UNMATCHED = "unmatched"
    IGNORED = "ignored"
