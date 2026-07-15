from pydantic import BaseModel, Field

from cc_crm.models.enums import CandidateStatus
from cc_crm.schemas.candidate import CandidateRead


class NlSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class NlSearchFilter(BaseModel):
    """Structured filter the query-parser LLM extracts from a free-text
    search. Kept deliberately close to what CandidateRepository.filtered()
    already accepts, plus fachliche_schwerpunkte for an additional in-Python
    filter (JSON list column, not trivial to query generically in SQLite)."""

    status: CandidateStatus | None = None
    role: str | None = None
    region: str | None = None
    search: str | None = None
    fachliche_schwerpunkte: list[str] = Field(default_factory=list)


class NlSearchResponse(BaseModel):
    items: list[CandidateRead]
    total_count: int
    filters_used: dict[str, object]
    hint: str | None = None
