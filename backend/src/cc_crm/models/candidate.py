import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from cc_crm.models.enums import Anrede, CandidateStatus, Rolle


class Candidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidates"

    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    phone: Mapped[str | None] = mapped_column(String(80))
    job_title: Mapped[str | None] = mapped_column(String(180), index=True)
    qualification: Mapped[str | None] = mapped_column(String(240))
    postal_code: Mapped[str | None] = mapped_column(String(20), index=True)
    city: Mapped[str | None] = mapped_column(String(160))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    salary_expectation: Mapped[str | None] = mapped_column(String(120))
    notice_period: Mapped[str | None] = mapped_column(String(160))
    available_from: Mapped[date | None] = mapped_column(Date)
    last_contact_at: Mapped[date | None] = mapped_column(Date, index=True)
    next_step: Mapped[str | None] = mapped_column(String(240))
    cv_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Stichtag-Zaehler fuer Analytics ("CV In"), getrennt vom reinen
    # cv_available-Anzeige-Flag (siehe candidates-table.tsx-Indikatorpunkt):
    # cv_available wurde beim Datenuebertrag pauschal fuer 2481 Alt-
    # Kandidaten gesetzt, ohne echtes Funnel-Ereignis - Analytics zaehlte das
    # faelschlich als "CV In" mit (Nutzer-Feedback 2026-07-15). Bleibt NULL
    # fuer alle Alt-Kandidaten (per Migration nicht befuellt) und wird ab
    # jetzt nur noch gesetzt, wenn cv_available echt (neu) auf True wechselt
    # (siehe CandidateService.update()) - Analytics zaehlt nur Zeilen mit
    # gesetztem Wert.
    cv_in_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    short_profile: Mapped[str | None] = mapped_column(Text)
    consent_received: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, native_enum=False, length=32),
        default=CandidateStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    candidate_number: Mapped[str | None] = mapped_column(String(40), unique=True, index=True)
    # Grammatikalisches Geschlecht für die Profilgenerierung (Kandidatin/Kandidat + Pronomen).
    anrede: Mapped[Anrede | None] = mapped_column(Enum(Anrede, native_enum=False, length=16))
    # Wer den Kandidaten empfohlen hat (Freitext) - Basis für ein späteres
    # Referral-Follow-up nach erfolgreichem Placement.
    referred_by: Mapped[str | None] = mapped_column(String(240))

    # --- Quali-Call-Erweiterung (2026-07) ---
    fachliche_schwerpunkte: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # Software/IT-Tools (DATEV, SAP, Lexware, MS Office, ...) - eigenes Feld
    # statt Teil von fachliche_schwerpunkte (2026-08, CV-Backfill-Neuaufsetzung),
    # weil der anonyme Profilstil EDV-Kenntnisse granular und getrennt von
    # den uebrigen fachlichen Schwerpunkten braucht. Gleiches Strukturmuster
    # wie fachliche_schwerpunkte.
    edv_kenntnisse: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    ausbildung_titel: Mapped[str | None] = mapped_column(String(240))
    # Liste von Stationen: [{"kanzleityp": str, "kanzleigroesse": str,
    # "dauer_jahre": int, "rolle": <Rolle-Wert oder null>}, ...] - "rolle" ist
    # NEU (CV-Extraktion Neuaufsetzung), aeltere Eintraege ohne diesen Key
    # sind beim Lesen gueltig (siehe schemas/candidate.py::BeruflicheStation).
    berufliche_stationen: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    # Normalisierte Rollen-Kategorien (siehe models/enums.py::Rolle) - LISTE,
    # weil ein Kandidat mehrere gleichzeitig gueltige Rollen tragen kann (z.B.
    # Rechtsanwalt UND Steuerberater), keine zeitliche Abfolge. job_title
    # bleibt daneben als Freitext-Originaltitel aus dem CV erhalten - rollen
    # ist die durchsuchbare, normalisierte Kategorie-Liste dazu (gleiches
    # Strukturmuster wie fachliche_schwerpunkte). Bewusst weiterhin
    # sa.JSON() statt JSONB (kein anderes JSON-Feld in diesem Projekt nutzt
    # JSONB, SQLite-Kompatibilitaet fuer die lokale Entwicklung bleibt damit
    # erhalten) - falls spaeter ein haeufig genutzter Rollen-Filter auf
    # Postgres-Array-Containment (@>) entsteht, dann an dieser Stelle auf
    # JSONB + GIN-Index migrieren.
    rollen: Mapped[list[Rolle]] = mapped_column(JSON, default=list, nullable=False)
    # INTERN — niemals in anonyme Profile / ausgehende Dokumente übernehmen
    # (siehe services/profile_generator.py::_build_quali_call_payload, das
    # bewusst eine Allowlist statt einer Blockliste ist - dieses Feld taucht
    # dort schlicht nicht auf). Klarname des aktuellen/letzten Arbeitgebers,
    # anders als aktuelles_umfeld_kanzleityp/-kanzleigroesse (die bewusst
    # bereits anonymisiert/kategorial sind und deshalb im Profil verwendet
    # werden duerfen).
    current_employer_internal: Mapped[str | None] = mapped_column(String(240))
    aktuelles_umfeld_kanzleityp: Mapped[str | None] = mapped_column(String(160))
    aktuelles_umfeld_kanzleigroesse: Mapped[str | None] = mapped_column(String(160))
    # INTERN — niemals in anonyme Profile / ausgehende Dokumente übernehmen.
    wechselgrund: Mapped[str | None] = mapped_column(Text)
    remote_teilzeit_wuensche: Mapped[str | None] = mapped_column(String(240))
    passender_kanzleityp: Mapped[str | None] = mapped_column(String(160))
    # INTERN — niemals in anonyme Profile / ausgehende Dokumente übernehmen.
    no_gos: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    freitext_notizen: Mapped[str | None] = mapped_column(Text)

    # Vollstaendiges Ergebnis der letzten CV-Extraktion (siehe
    # services/cv_extraction.py::extract_candidate_fields), unabhaengig
    # davon, welche der Werte auch als eigene Spalte uebernommen wurden -
    # damit kuenftige Funktionen (neue Anzeige-Felder, andere CRM-Bereiche)
    # bereits ausgelesene CV-Informationen wiederverwenden koennen, ohne das
    # CV erneut per KI auslesen zu muessen. Bewusst nullable ohne Default
    # (anders als die Listenfelder oben): "noch nie ausgelesen" ist ein
    # legitimer, haeufiger Zustand (kein CV hochgeladen), keine leere
    # Datenstruktur.
    cv_extraction_raw: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Zustaendiger Mitarbeiter (Komfort-Filter "Meine Kandidaten", KEINE
    # Sichtbarkeitsgrenze - jeder Nutzer sieht weiterhin alle Kandidaten,
    # anders als beim Kalender). Nullable: "nicht zugewiesen" ist ein
    # gueltiger Zustand, Bestandsdaten werden nicht rueckwirkend zugewiesen.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
