"""Natural-language search over the candidate pool.

Converts a free-text query ("aktive Steuerberater in Köln mit Umsatzsteuer-
Erfahrung") into a structured filter via an LLM query-parser prompt, then runs
that filter against the existing CandidateRepository.filtered() query plus an
in-Python pass for fachliche_schwerpunkte (a JSON list column, not trivial to
filter generically in SQLite).

Deliberately resilient: if the LLM call fails or returns something unparsable
(no API key configured, Anthropic unreachable, malformed JSON), search falls
back to treating the whole query as a plain substring search rather than
breaking the search bar entirely - "kein KI-Ergebnis" should never mean
"keine Suche funktioniert mehr".
"""

import json
import re

from sqlalchemy.orm import Session

from cc_crm.integrations.ai.anthropic_client import generate_text
from cc_crm.schemas.candidate import CandidateRead
from cc_crm.schemas.search import NlSearchFilter, NlSearchResponse
from cc_crm.services.candidates import CandidateService

SYSTEM_PROMPT = """Du bist ein Such-Assistent für ein Recruiting-CRM (Personalberatung
für Steuer-, Wirtschaftsprüfungs- und Rechtskanzleien). Du wandelst eine
freitextliche, deutschsprachige Suchanfrage eines Recruiters in ein striktes
JSON-Filterobjekt um.

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück, keine Erklärungen, kein Markdown,
kein Codeblock - nur das rohe JSON.

Felder (alle optional, weglassen bzw. null setzen wenn nicht aus der Anfrage
ableitbar):
{
  "status": "active" | "passive" | "placed" | "blocked" | "archived" | null,
  "role": string | null,       // Rolle/Berufsbezeichnung, z.B. "Steuerberater"
  "region": string | null,     // Ort/Region, z.B. "Köln"
  "search": string | null,     // freie Stichwörter, die sonst nirgends reinpassen
  "fachliche_schwerpunkte": string[]   // fachliche Themen/Spezialisierungen, z.B. ["Umsatzsteuer"]
}

Regeln:
- Erfinde keine Werte, die nicht aus der Anfrage hervorgehen.
- "aktiv"/"aktive Kandidaten" -> status="active". Ähnlich für passiv/platziert/gesperrt/archiviert.
- Wenn nichts Sinnvolles erkennbar ist, gib ein leeres Objekt {} zurück.

Beispiel:
Anfrage: "aktive Steuerberater in Köln mit Umsatzsteuer-Erfahrung"
Antwort: {"status": "active", "role": "Steuerberater", "region": "Köln",
"fachliche_schwerpunkte": ["Umsatzsteuer"]}
"""

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(raw: str) -> str:
    fenced = _JSON_FENCE.search(raw)
    return fenced.group(1) if fenced else raw.strip()


class NlSearchService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.candidates = CandidateService(session)

    def search(self, query: str, *, limit: int = 200) -> NlSearchResponse:
        parsed = self._parse_query(query)

        entities, _total = self.candidates.candidates.filtered(
            status=parsed.status,
            role=parsed.role,
            region=parsed.region,
            search=parsed.search,
            offset=0,
            limit=limit,
        )

        results = list(entities)
        if parsed.fachliche_schwerpunkte:
            wanted = {item.lower() for item in parsed.fachliche_schwerpunkte}
            results = [
                candidate
                for candidate in results
                if wanted & {item.lower() for item in (candidate.fachliche_schwerpunkte or [])}
            ]

        hint = None
        if len(results) < 3:
            hint = (
                "Weniger als 3 Treffer - Filter ist möglicherweise zu eng. "
                "Suchbegriff anders formulieren oder allgemeiner fassen."
            )

        return NlSearchResponse(
            items=[CandidateRead.model_validate(candidate) for candidate in results],
            total_count=len(results),
            filters_used=parsed.model_dump(exclude_none=True, exclude_defaults=True),
            hint=hint,
        )

    def _parse_query(self, query: str) -> NlSearchFilter:
        try:
            raw = generate_text(system_prompt=SYSTEM_PROMPT, user_message=query, max_tokens=300)
            data = json.loads(_extract_json(raw))
            if not isinstance(data, dict):
                raise ValueError("LLM response was not a JSON object")
            return NlSearchFilter.model_validate(data)
        except Exception:
            # Resilient fallback (covers: no API key / AIProviderError,
            # malformed JSON, schema validation errors, anything unforeseen):
            # treat the whole query as a plain substring search instead of
            # breaking the search bar outright.
            return NlSearchFilter(search=query)
