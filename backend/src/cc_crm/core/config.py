import logging
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import AnyUrl, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("cc_crm.config")

# backend/src/cc_crm/core/config.py -> backend/ (3 parents up). Resolved as an
# absolute path so .env is found regardless of the process's working
# directory - a relative "env_file=\".env\"" only works if the process
# happens to be launched with cwd=backend/, and silently falls back to the
# hardcoded Postgres default below otherwise (which then hangs for minutes
# per request until the connection times out, instead of failing fast).
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ROOT / ".env"),
        env_prefix="CC_CRM_",
        extra="ignore",
    )

    environment: str = "local"
    # NOMICON: Demo-Login ohne Passwort/2FA, NUR lokal (siehe services/demo_login.py). Standard aus.
    demo_login: bool = False
    # Firmenschicht (siehe docs/PROJEKT_STAND.md > Zweite Firma): alles
    # Firmenspezifische liegt in Konfiguration, nicht im Code - dann lassen sich
    # Aenderungen aus Hermes ohne Konflikte in eine Kopie fuer eine andere Firma
    # uebernehmen. Standard = Commandeur Consulting (nichts aendert sich).
    company_name: str = "Commandeur Consulting"
    # Text im Briefkopf der von der Agentur selbst erzeugten anonymen Profile
    # (services/cv_extraction.py::is_agency_letterhead): daran erkennt Hermes ein
    # eigenes Profil und uebernimmt die Agenturadresse nicht als Kandidatendaten.
    # In der Kopie auf den Namen im eigenen Briefkopf setzen.
    agency_letterhead_marker: str = "Commandeur Consulting GmbH"
    # Word-Vorlage mit dem Briefkopf des anonymen Profils (docx). Leer = die
    # mitgelieferte backend/templates/anonymes_profil_master.docx.
    profile_template_path: str | None = None
    api_prefix: str = "/api/v1"
    # Betrieb: Logs als JSON (eine Zeile pro Request), Sentry nur mit DSN.
    log_level: str = "INFO"
    json_logs: bool = True
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.0
    # Beim Start `alembic upgrade head` ausfuehren (Standard, wie bisher). Bei
    # mehreren Instanzen besser aus und stattdessen ein Pre-Deploy-Job, siehe
    # docs/DEPLOYMENT.md.
    migrate_on_startup: bool = True
    # Die Job-Warteschlange (services/job_queue.py) im Webprozess mitlaufen
    # lassen. Standard an, damit es OHNE eigene Worker-Komponente funktioniert;
    # mit separatem Worker (scripts/run_worker.py) hier auf false stellen.
    embedded_worker: bool = True
    database_url: str = "postgresql+psycopg://cc_crm:change-me@localhost:5432/cc_crm"
    cors_origins: list[AnyUrl] = []
    sql_echo: bool = False
    default_vat_rate: Decimal = Decimal("19.00")
    # Schwellwert (Monate) für die Reaktivierungsliste: Kandidaten, deren
    # last_contact_at länger als das her ist, gelten als "wiedervorlagereif".
    reactivation_threshold_months: int = 6
    # Tage vor Ablauf der Gewährleistung (Placement.start_date +
    # guarantee_period_months), zu denen automatisch ein Follow-up-Task
    # erzeugt wird ("bald_ablaufend").
    warranty_follow_up_days_before: int = 14
    # Lesende Claude-Schnittstelle (MCP, api/v1/mcp.py): STANDARDMAESSIG AUS. Erst
    # einschalten, wenn die Auftragsverarbeitung mit Anthropic geklaert ist - ohne
    # den Schalter liefert der Endpunkt 404 und es verlassen keine Daten das System.
    ai_enabled: bool = False
    # Darf der anonymisierte Profiltext (`short_profile`) in der MCP-Ausgabe eines einzelnen
    # Kandidaten an Claude gehen? STANDARDMAESSIG AUS: der Text ist KI-erzeugt und vom Berater
    # geprueft, aber technisch nicht auf Anonymitaet geprueft (kann Arbeitgeber/Stationen nennen).
    ai_include_profile: bool = False
    # Maximale MCP-Werkzeugaufrufe pro Nutzer und Tag (UTC).
    mcp_daily_limit: int = 500
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    # Fernet-Schluessel fuer die Postfach-Passwoerter (siehe
    # models/mail.py::MailAccount.encrypted_password). Ohne gesetzten
    # Schluessel laesst sich kein Postfach anlegen - bewusst ein harter
    # Fehler statt eines stillen Klartext-Fallbacks (siehe
    # services/mail_credentials.py). Erzeugen mit:
    #   python -c "from cryptography.fernet import Fernet;
    #              print(Fernet.generate_key().decode())"
    mail_credentials_encryption_key: str | None = None
    # Microsoft-Graph-OAuth fuer M365-Postfaecher (Auftrag "M365-Postfach-
    # Integration") - Delegated Permissions, Single-Tenant-App-Registrierung
    # in Entra ID (siehe integrations/microsoft_graph/). Alle drei muessen
    # gesetzt sein, damit der "Mit Microsoft anmelden"-Flow funktioniert;
    # ohne sie bleibt provider=imap_smtp die einzige Option (kein harter
    # Fehler beim Start, nur beim tatsaechlichen Verbindungsversuch, gleiche
    # Haltung wie mail_credentials_encryption_key oben).
    ms_graph_client_id: str | None = None
    ms_graph_tenant_id: str | None = None
    ms_graph_client_secret: str | None = None
    # "Mit Microsoft anmelden" verbindet gleichzeitig das eigene Postfach/den Kalender
    # (Mail senden, Termine mit Teams-Link). Braucht die Graph-Rechte in Entra ID
    # (Admin-Zustimmung). Bei Problemen auf false stellen: dann meldet der Login nur an.
    ms_login_connects_mailbox: bool = True
    # Name des Session-Cookies, den das Frontend liest (frontend/src/lib/api/
    # client.ts::AUTH_COOKIE_NAME) - der Microsoft-SSO-Callback laeuft im
    # Backend und setzt ihn selbst, siehe api/v1/microsoft_login.py.
    auth_cookie_name: str = "cc_crm_token"
    # Lokales Verzeichnis für hochgeladene Dokumente (CVs, Verträge, etc.) -
    # Fallback, wenn kein S3-kompatibler Speicher konfiguriert ist (siehe unten).
    # Relativ zum Backend-Arbeitsverzeichnis, falls kein absoluter Pfad gesetzt ist.
    documents_storage_dir: Path = Path("data/documents")
    # Maximale Dateigröße für Dokumenten-Uploads (siehe api/v1/operational.py) -
    # als Setting statt hartkodierter Konstante, damit sie ohne Code-Änderung
    # anpassbar ist (z.B. per Umgebungsvariable CC_CRM_MAX_UPLOAD_SIZE_MB).
    max_upload_size_mb: int = 25

    # CV-Auswertung (services/cv_extraction.py): Liefert pypdf ueber alle Seiten
    # im Schnitt weniger nicht-leere Zeichen pro Seite als dieser Wert, gilt das
    # PDF als gescannt (kein brauchbarer Text-Layer) und wird per Vision statt
    # per Text-Call ausgewertet. Env: CC_CRM_CV_SCAN_MIN_CHARS_PER_PAGE.
    cv_scan_min_chars_per_page: int = 200
    # Wie viele Seiten eines gescannten PDFs gerendert und gemeinsam per Vision
    # ausgelesen werden (Tokenkosten wachsen linear mit der Seitenzahl).
    cv_vision_max_pages: int = 4

    # S3-kompatibler Objektspeicher (z.B. Cloudflare R2, AWS S3, Backblaze B2) für
    # Dokumente - empfohlen für produktiven Betrieb/Hosting, da lokale Dateien bei
    # den meisten Hosting-Plattformen bei jedem Deploy/Neustart verloren gehen.
    # Ist s3_bucket gesetzt, wird automatisch S3 statt lokalem Ordner verwendet.
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None  # z.B. https://<account-id>.r2.cloudflarestorage.com
    s3_region: str = "auto"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

    # Ziel-Adresse fuer Sicherheitswarnungen (z.B. geblockter Brute-Force-
    # Versuch auf /auth/login) - siehe services/security_alerts.py. Ohne
    # gesetzte Adresse bleibt das Feature inaktiv (nur ein Log-Eintrag statt
    # eines Mail-Versands), damit ein fehlendes Setup nie den eigentlichen
    # Login-Flow beeintraechtigt.
    security_alert_email: str | None = None
    # Transaktionale E-Mails (Sicherheitswarnungen, 2FA-Login-Codes - siehe
    # integrations/email/resend_client.py) laufen ueber Resend statt SMTP:
    # bewusst KEINE Abhaengigkeit vom verbundenen M365-Postfach fuer etwas so
    # Kritisches wie den Login (M365-SMTP-Auth ist bei modernen Tenants oft
    # gesperrt, und nach dem Graph-Sync-Vorfall keine weitere M365-
    # Abhaengigkeit an dieser Stelle). resend_from_email braucht eine in
    # Resend verifizierte Absender-Domain.
    resend_api_key: str | None = None
    resend_from_email: str | None = None

    @model_validator(mode="after")
    def _strip_bucket_prefix_from_s3_endpoint(self) -> "Settings":
        """Live auf Produktion bestätigt: `S3_ENDPOINT_URL` war auf die
        bucket-spezifische ("virtual-hosted-style") Adresse gesetzt
        (`https://<bucket>.<region>.digitaloceanspaces.com`), bei der der
        Bucket-Name bereits Teil des Hostnamens ist. `services/storage.py`
        übergibt an JEDEN boto3-Aufruf zusätzlich `Bucket=s3_bucket` - boto3
        hängt den Bucket-Namen dann ein zweites Mal vor den bereits
        bucket-spezifischen Host, was zu einer falsch adressierten URL führt
        (vom Anbieter mit einem irreführenden `NoSuchKey` statt einem
        aussagekräftigeren Fehler quittiert - jeder S3-Aufruf schlug fehl,
        unabhängig davon, ob das jeweilige Objekt existierte). Repariert das
        automatisch, falls dieser Konfigurationsfehler erneut auftritt,
        statt erneut lautlos jeden S3-Aufruf scheitern zu lassen - der
        korrekte Wert ist der regionale Endpoint OHNE Bucket-Namen im Host,
        der Bucket wird ausschließlich als separater Parameter übergeben."""
        if self.s3_endpoint_url and self.s3_bucket:
            bucket_prefix = f"https://{self.s3_bucket}."
            if self.s3_endpoint_url.startswith(bucket_prefix):
                fixed = "https://" + self.s3_endpoint_url.removeprefix(bucket_prefix)
                logger.warning(
                    "CC_CRM_S3_ENDPOINT_URL enthielt den Bucket-Namen als Host-Präfix "
                    "(%s) - automatisch auf den regionalen Endpoint ohne Bucket-Präfix "
                    "korrigiert (%s). Bitte die Umgebungsvariable selbst auf den "
                    "korrigierten Wert setzen, damit sich niemand auf diese "
                    "Notkorrektur verlassen muss.",
                    self.s3_endpoint_url,
                    fixed,
                )
                self.s3_endpoint_url = fixed
        return self

    @property
    def resolved_database_url(self) -> str:
        """`database_url` with a relative sqlite path resolved against
        backend/ instead of the process's cwd - same class of bug as the
        .env lookup above: "sqlite:///./cc_crm_local.db" silently pointed at
        a *different*, freshly-created empty database file whenever the
        process wasn't launched with cwd=backend/ (e.g. "no such table:
        users" instead of the real, populated local DB)."""
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return self.database_url
        raw_path = self.database_url.removeprefix(prefix)
        path = Path(raw_path)
        if not path.is_absolute():
            path = (_BACKEND_ROOT / path).resolve()
        return f"{prefix}{path.as_posix()}"

    @property
    def resolved_documents_storage_dir(self) -> Path:
        if self.documents_storage_dir.is_absolute():
            return self.documents_storage_dir
        return (_BACKEND_ROOT / self.documents_storage_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
