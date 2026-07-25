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
    api_prefix: str = "/api/v1"
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
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    # Lokales Verzeichnis für hochgeladene Dokumente (CVs, Verträge, etc.) -
    # Fallback, wenn kein S3-kompatibler Speicher konfiguriert ist (siehe unten).
    # Relativ zum Backend-Arbeitsverzeichnis, falls kein absoluter Pfad gesetzt ist.
    documents_storage_dir: Path = Path("data/documents")
    # Maximale Dateigröße für Dokumenten-Uploads (siehe api/v1/operational.py) -
    # als Setting statt hartkodierter Konstante, damit sie ohne Code-Änderung
    # anpassbar ist (z.B. per Umgebungsvariable CC_CRM_MAX_UPLOAD_SIZE_MB).
    max_upload_size_mb: int = 25

    # S3-kompatibler Objektspeicher (z.B. Cloudflare R2, AWS S3, Backblaze B2) für
    # Dokumente - empfohlen für produktiven Betrieb/Hosting, da lokale Dateien bei
    # den meisten Hosting-Plattformen bei jedem Deploy/Neustart verloren gehen.
    # Ist s3_bucket gesetzt, wird automatisch S3 statt lokalem Ordner verwendet.
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None  # z.B. https://<account-id>.r2.cloudflarestorage.com
    s3_region: str = "auto"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None

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
