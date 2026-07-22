from typing import Any, Literal

from pydantic import BaseModel, Field

ImportEntity = Literal[
    "candidates",
    "clients",
    "contacts",
    "jobs",
    "submissions",
    "tasks",
    "notes",
    "sourcing_metrics",
]


class ImportFilePayload(BaseModel):
    filename: str
    content_base64: str
    mapping: dict[str, str] = Field(default_factory=dict)


class ImportRow(BaseModel):
    row_number: int
    data: dict[str, Any]
    errors: list[str] = Field(default_factory=list)
    duplicate: bool = False


class ImportPreview(BaseModel):
    entity: ImportEntity
    columns: list[str]
    rows: list[ImportRow]
    valid_count: int
    error_count: int
    duplicate_count: int
    commit_supported: bool


class ImportCommitRequest(BaseModel):
    rows: list[ImportRow]
    confirmed: bool


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[str]
    duplicates: int
    merged: int = 0
    # Anzahl per candidate_number auf einen bestehenden Kandidaten gemergter
    # Zeilen (Master-Excel-Bulk-Korrektur, siehe ImportService.commit) -
    # bewusst getrennt von `merged` (Kanzlei-Adressfeld-Merge) und von
    # `duplicates`/`skipped`, da hier tatsaechlich Felder aktualisiert wurden.
    updated: int = 0
