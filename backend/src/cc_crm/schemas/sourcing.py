import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from cc_crm.models.enums import SourcingLeadStatus, SourcingSourceType
from cc_crm.schemas.base import EntityRead


class SourcingLeadCreate(BaseModel):
    source_type: SourcingSourceType
    source_url: str | None = None
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    current_employer: str | None = Field(default=None, max_length=240)
    city: str | None = Field(default=None, max_length=160)
    postal_code: str | None = Field(default=None, max_length=20)
    raw_data: dict[str, Any] | None = None
    matched_client_company_id: uuid.UUID | None = None


_AREA_SOURCES = (
    SourcingSourceType.STEUERBERATERVERZEICHNIS,
    SourcingSourceType.WPK_BERUFSREGISTER,
)


class SourcingRunRequest(BaseModel):
    source_type: SourcingSourceType
    # Fuer die Verzeichnis-Quellen (Steuerberaterverzeichnis, WPK). Max. 20
    # Gebiete pro Lauf: der Lauf ist synchron (Ergebnis-Zahlen direkt in der
    # Antwort) und pausiert zwischen Requests - mehr Gebiete wuerden den
    # Request zu lange offen halten.
    plz_or_ort: list[str] | None = Field(default=None, min_length=1, max_length=20)
    # Fuer kanzlei_team_page: gezielte Kanzleien (synchron, max. 10) ...
    client_company_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=10)
    # ... oder alle erfassten Kanzleien mit Website (als Background-Task,
    # Ergebnis erscheint fortlaufend in der Lead-Liste).
    scan_all_companies: bool = False

    @model_validator(mode="after")
    def _validate_source_params(self) -> Self:
        if self.source_type in _AREA_SOURCES:
            if not self.plz_or_ort:
                raise ValueError("plz_or_ort ist fuer diese Quelle erforderlich")
        elif self.source_type == SourcingSourceType.KANZLEI_TEAM_PAGE:
            if not self.client_company_ids and not self.scan_all_companies:
                raise ValueError(
                    "kanzlei_team_page braucht client_company_ids oder scan_all_companies"
                )
        else:
            # BRAK-Anwaltsverzeichnis: Listen-Suche waere zwar moeglich, wird
            # aber bewusst nicht automatisiert angebunden (nur 6 Treffer pro
            # Seite ueber zustandsbehaftete JSF-Postbacks - siehe
            # Phase-3-Bericht). Quelle bleibt der manuellen Recherche
            # vorbehalten.
            raise ValueError("Diese Quelle ist nicht als automatisierter Sourcing-Lauf verfuegbar")
        return self


class SourcingRunResult(BaseModel):
    found: int = 0
    created: int = 0
    skipped_existing: int = 0
    possible_duplicates: int = 0
    errors: list[str] = Field(default_factory=list)
    # Anzahl Kanzleien, deren Team-Scan als Background-Task gestartet wurde
    # (scan_all_companies) - die Zaehler oben bleiben dann 0, die Leads
    # erscheinen fortlaufend in der Liste.
    background_started: int = 0


class SourcingLeadRead(EntityRead):
    source_type: SourcingSourceType
    source_url: str | None
    first_name: str
    last_name: str
    current_employer: str | None
    city: str | None
    postal_code: str | None
    raw_data: dict[str, Any] | None
    matched_client_company_id: uuid.UUID | None
    status: SourcingLeadStatus
    duplicate_of_candidate_id: uuid.UUID | None
    created_candidate_id: uuid.UUID | None
    found_at: datetime
    reviewed_at: datetime | None
    reviewed_by_user_id: uuid.UUID | None
