# NOMICON: gemeinsamer Kandidatenstatus - nur in der Nomicon-Kopie.
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Openness = Literal["yes", "no", "unknown"]
EngagementStatus = Literal["frei", "im_direct", "im_einsatz", "beides", "vermittelt"]
ConflictMode = Literal["warn", "block"]
EngagementFilter = Literal["free_direct", "free_staffing", "engaged"]


class EngagementItemRead(BaseModel):
    """Ein Prozess oder Einsatz des Kandidaten. Ohne Zugriff auf den Datensatz nur Kanal, Stufe,
    Mitarbeiter und Datum: Kanzlei und IDs bleiben leer (`details_visible=False`)."""

    channel: Literal["direct", "staffing"]
    kind: Literal["process", "placement", "assignment"]
    stage: str
    owner_name: str | None
    since: date | None
    until: date | None
    details_visible: bool
    client_name: str | None = None
    entity_id: uuid.UUID | None = None


class CandidateEngagementRead(BaseModel):
    candidate_id: uuid.UUID
    status: EngagementStatus
    open_for_direct: Openness
    open_for_staffing: Openness
    items: list[EngagementItemRead]


class EngagementPrefsUpdate(BaseModel):
    open_for_direct: Openness | None = None
    open_for_staffing: Openness | None = None


class EngagementSummaryRequest(BaseModel):
    candidate_ids: list[uuid.UUID] = Field(max_length=500)


class EngagementSettingsRead(BaseModel):
    conflict_mode: ConflictMode


class EngagementSettingsUpdate(BaseModel):
    conflict_mode: ConflictMode
