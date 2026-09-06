import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from cc_crm.schemas.base import EntityRead


class DocumentCreate(BaseModel):
    owner_type: str = Field(pattern="^(candidate|client|submission|placement|fee)$")
    owner_id: uuid.UUID
    document_type: str = Field(min_length=1, max_length=60)
    filename: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=500)
    content_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    uploaded_by: str | None = None
    sent_with_submission_id: uuid.UUID | None = None


class DocumentRead(DocumentCreate, EntityRead):
    has_generic_filename: bool = False


class SourcingMetricCreate(BaseModel):
    period_start: date
    period_end: date
    source: str = Field(default="LinkedIn", max_length=80)
    campaign: str | None = Field(default=None, max_length=240)
    pitches: int = Field(default=0, ge=0)
    responses: int = Field(default=0, ge=0)
    positive_responses: int = Field(default=0, ge=0)
    qualification_calls: int = Field(default=0, ge=0)
    notes: str | None = None


class SourcingMetricRead(SourcingMetricCreate, EntityRead):
    pass


class EmailTemplateRead(BaseModel):
    key: str
    name: str
    subject: str
    body: str
    placeholders: list[str]


class EmailDraftCreate(BaseModel):
    template_key: str
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    candidate_submission_id: uuid.UUID | None = None
    recipient: str | None = None
    subject: str
    body: str


class EmailDraftRead(EmailDraftCreate, EntityRead):
    provider: str
    external_draft_id: str | None
    drafted_at: datetime | None


class ProfileSuggestion(BaseModel):
    candidate_id: uuid.UUID
    text: str
    is_draft: bool = True


class CockpitItem(BaseModel):
    kind: str
    title: str
    detail: str
    due_at: datetime | None = None
    candidate_id: uuid.UUID | None = None
    client_company_id: uuid.UUID | None = None
    submission_id: uuid.UUID | None = None
    priority: str = "normal"
    # Nur bei kind="task" gesetzt (siehe CockpitService.build) - die
    # Dashboard-To-Do-Sektion braucht die Task-ID fuer die Snooze/Resolve-
    # Aktionen (POST /tasks/{id}/snooze bzw. /resolve).
    task_id: uuid.UUID | None = None


class CockpitKpis(BaseModel):
    """Zwei unterschiedliche Fragen, bewusst GETRENNT ausgewiesen (Nutzer-
    Entscheidung "KPIs stimmen nicht", Punkt 3d): Pipeline-Kennzahlen ("wie
    viele Prozesse haben Stufe X ERREICHT") beruhen durchgehend auf der
    echten Statuswechsel-Historie (AuditLog) - das bildet ab, was im Kanban
    tatsaechlich passiert, unabhaengig davon, ob ein zugehoeriges Formular
    ausgefuellt wurde. Kaufmaennische Kennzahlen (Umsatz, Ø Fee, Rechnungs-
    status) beruhen weiterhin auf den gepflegten Offer-/Placement-
    Datensaetzen, weil dort Gehalt/Fee/Rechnungsdaten haengen - ein reiner
    Statuswechsel liefert die nicht. Wo beide nebeneinander stehen (offer/
    offer_stage_reached_count, placements/placement_stage_reached_count),
    ist die Differenz eine Kennzahl fuer sich: sie zeigt unfertige
    Erfassungen (siehe CockpitRead.data_gaps)."""

    qualification_calls: int
    cv_available: int
    # "Neue Prozesse" - im Zeitraum ANGELEGTE CandidateSubmissions
    # (unabhaengig vom aktuellen/erreichten Status). Historisch als
    # "CV-Outs" beschriftet, was NICHT stimmte (siehe cv_outs_reached_count
    # fuer die tatsaechliche CV-Out-Pipeline-Kennzahl) - Feldname bleibt aus
    # Kompatibilitaetsgruenden, nur die Bedeutung/Beschriftung wurde
    # richtiggestellt.
    submissions: int
    # PIPELINE: im Zeitraum tatsaechlich CV_OUT erreicht (Statuswechsel-
    # Transition, nicht Anlagezeitpunkt der Submission).
    cv_outs_reached_count: int
    # PIPELINE: im Zeitraum tatsaechlich INTERVIEW erreicht (Transition) -
    # vorher: aktueller Bestand an Submissions mit status==interview,
    # UNABHAENGIG vom period-Zeitraum (Inkonsistenz zu offers/placements
    # unten, siehe Nutzer-Feedback Punkt 3c).
    interviews: int
    # KAUFMAENNISCH: echte Offer-Objekte, im Zeitraum ANGELEGT.
    offers: int
    # PIPELINE: im Zeitraum tatsaechlich OFFER erreicht (Transition).
    offer_stage_reached_count: int
    # KAUFMAENNISCH: echte Placement-Objekte, im Zeitraum ANGELEGT.
    placements: int
    # PIPELINE: im Zeitraum tatsaechlich PLACEMENT erreicht (Transition).
    placement_stage_reached_count: int
    expected_fees: float
    realized_fees: float
    # Anzahl DISTINCT Placements mit mindestens einer Fee im Status
    # draft/issued/due (nicht paid/cancelled) - Basis fuer den "X Placement(s)
    # haben offenen Rechnungsstatus"-Hinweis im Cockpit (vorher ein
    # hartcodierter Platzhaltertext, siehe Nutzer-Feedback "Prozesse
    # abschliessen...", Punkt 1).
    open_invoice_placement_count: int
    # PIPELINE: Anzahl geloggter Pitch/InMail-Ereignisse im Zeitraum (siehe
    # models/candidate_pitch_log.py::CandidatePitchLog) - Stufe 1 der
    # konsolidierten 7-Stufen-Pipeline (Nutzer-Vorgabe: "die 7 Stufen sind
    # 1. Pitch/InMail, 2. Quali Call, ... 7. Placement"). Ersetzt die
    # vorherige manuelle SourcingFunnel.pitches-Zahl (siehe sourcing unten,
    # Nutzer-Entscheidung "Ersetzen").
    pitches: int


class CockpitRates(BaseModel):
    pitch_to_qualification_call_rate: float
    submission_to_interview: float
    interview_to_offer: float
    offer_to_placement: float
    placement_to_paid: float


class SourcingFunnel(BaseModel):
    has_data: bool
    pitches: int
    responses: int
    positive_responses: int
    qualification_calls: int
    pitch_to_response_rate: float | None
    response_to_qualification_call_rate: float | None


class RecruitingKpis(BaseModel):
    """Etablierte Standard-Recruiting-Kennzahlen (siehe CockpitService::
    _recruiting_kpis) - bewusst NICHT auf den gewaehlten period-Zeitraum
    beschraenkt, sondern ueber den gesamten historischen Bestand berechnet,
    da Median-Durchlaufzeiten ueber wenige Wochen/Monate zu wenig Datenpunkte
    haetten, um aussagekraeftig zu sein. None, solange keine einzige
    Placement/Interview-Transition vorliegt (keine Kennzahl vorspiegeln)."""

    # Gemessen ab PROZESS-ANLAGE (CandidateSubmission.created_at) bis zur
    # Placement-Erfassung, NICHT ab CV-Out o.ae. - Nutzer-Entscheidung Punkt
    # 3e: das entspricht dem tatsaechlichen Ablauf, hier nur zur Klarheit
    # explizit benannt statt implizit "irgendein Start".
    time_to_fill_days: float | None
    time_to_interview_days: float | None
    average_fee_per_placement: float | None


class CockpitRead(BaseModel):
    period: str
    important: list[CockpitItem]
    hot_processes: list[CockpitItem]
    kpis: CockpitKpis
    recruiting_kpis: RecruitingKpis
    rates: CockpitRates
    sourcing: SourcingFunnel
    # Prozesse im Status OFFER/PLACEMENT OHNE zugehoerigen Offer-/Placement-
    # Datensatz - unfertige Erfassungen (Kanban-Drag ohne ausgefuelltes
    # Formular), die die kaufmaennischen Kennzahlen (offers/placements)
    # unterzaehlen wuerden. Sichtbar machen statt nur die Differenz zu den
    # Pipeline-Kennzahlen stillschweigend hinnehmen (Nutzer-Entscheidung
    # Punkt 3d).
    data_gaps: list[CockpitItem]
