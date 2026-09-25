"""One-time enrichment pass: fills structured Candidate fields (job_title,
qualification, city, salary_expectation, notice_period, fachliche_schwerpunkte)
by having an LLM read each candidate's imported Bullhorn-notes Timeline and
extract whatever it can.

Why this exists: import_bullhorn_notes.py could only reconstruct candidates
from a Notes-only export (no structured master data) - job_title/qualification/
city/fachliche_schwerpunkte were left empty, which makes Matching (services/
matching.py) score everything near-zero. The actual information often DOES
exist, just as free text inside the note bodies (e.g. "Möchte nur
Lohnbuchhaltung machen..."). This script recovers what it reasonably can.

Run manually, once, with the backend stopped (same SQLite-file-contention
reasoning as the import script):

    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\enrich_candidates_from_notes.py

Safety / idempotency:
- Requires CC_CRM_ANTHROPIC_API_KEY to be configured (same as Phase 2/4) -
  aborts early with a clear message if it isn't, rather than silently no-op'ing
  308 times.
- Only processes candidates where job_title AND qualification are BOTH still
  empty - safe to re-run, and won't clobber anything a consultant has since
  edited by hand in the CRM.
- LLM is instructed not to invent values; genuinely uninformative notes
  correctly produce an empty/partial result, which is normal, not a bug.
- This is inference from informal internal notes, not a verified quali call -
  spot-check a sample in the CRM before relying on it for outreach.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cc_crm.core.errors import AIProviderError  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.integrations.ai.anthropic_client import generate_text  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.schemas.candidate import CandidateUpdate  # noqa: E402
from cc_crm.services.activities import ActivityService  # noqa: E402
from cc_crm.services.candidates import CandidateService  # noqa: E402

SYSTEM_PROMPT = """Du bist Recruiting-Assistent für eine auf Steuern, Wirtschaftsprüfung
und Rechtskanzleien spezialisierte Personalberatung. Du bekommst die rohen
internen Notizen (Anrufe, Prescreens, E-Mails) zu einem Kandidaten aus dem
alten Bullhorn-System und extrahierst daraus so viele der folgenden
strukturierten Felder wie aus dem Text erkennbar sind.

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück, keine Erklärung, kein Markdown,
kein Codeblock - nur das rohe JSON.

Felder (weglassen bzw. null, wenn nicht klar aus dem Text ableitbar):
{
  "job_title": string | null,          // aktuelle/gewünschte Rolle, z.B. "Bilanzbuchhalter/in"
  "qualification": string | null,      // Ausbildung/Abschluss, z.B. "Steuerfachangestellte"
  "city": string | null,               // Ort/Region, z.B. "München" oder "Raum Köln"
  "salary_expectation": string | null, // Gehaltsvorstellung wie im Text, z.B. "ca. 45.000 EUR"
  "notice_period": string | null,      // Kündigungsfrist/Verfügbarkeit wie im Text
  "fachliche_schwerpunkte": string[]   // fachliche Themen/Skills als kurze Stichworte, max 5
}

Regeln:
- Erfinde nichts. Wenn ein Feld nicht klar aus dem Text hervorgeht, lasse es
  weg bzw. setze null.
- Der Text ist eine Mischung aus Deutsch und Englisch, oft stichwortartig -
  das ist normal für interne Notizen, kein Fehler.
- Enthält der Text nichts Verwertbares, gib {} zurück.
"""

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(raw: str) -> str:
    fenced = _JSON_FENCE.search(raw)
    return fenced.group(1) if fenced else raw.strip()


def _needs_enrichment(candidate: Candidate) -> bool:
    return not (candidate.job_title or "").strip() and not (candidate.qualification or "").strip()


def main() -> None:
    session = SessionLocal()
    try:
        candidates_service = CandidateService(session)
        activities_service = ActivityService(session)

        all_candidates = candidates_service.list(offset=0, limit=10_000)
        targets = [c for c in all_candidates if _needs_enrichment(c)]
        print(
            f"Kandidaten insgesamt: {len(all_candidates)} - "
            f"davon ohne job_title/qualification: {len(targets)}"
        )

        enriched = 0
        skipped_no_notes = 0
        skipped_no_result = 0
        failed = 0

        for index, candidate in enumerate(targets, start=1):
            activities = activities_service.activities.filtered(
                candidate_id=candidate.id, limit=100
            )
            notes_text = "\n---\n".join(a.details for a in activities if a.details)
            if not notes_text.strip():
                skipped_no_notes += 1
                continue

            try:
                raw = generate_text(
                    system_prompt=SYSTEM_PROMPT, user_message=notes_text, max_tokens=400
                )
                data = json.loads(_extract_json(raw))
                if not isinstance(data, dict):
                    raise ValueError("LLM response was not a JSON object")
            except (AIProviderError, ValueError, TypeError, json.JSONDecodeError) as exc:
                print(
                    f"  [{index}/{len(targets)}] {candidate.first_name} {candidate.last_name}: "
                    f"FEHLER ({exc})"
                )
                failed += 1
                continue

            update_fields = {
                key: value
                for key, value in data.items()
                if key
                in {
                    "job_title",
                    "qualification",
                    "city",
                    "salary_expectation",
                    "notice_period",
                    "fachliche_schwerpunkte",
                }
                and value
            }
            if not update_fields:
                skipped_no_result += 1
                continue

            candidates_service.update(candidate.id, CandidateUpdate(**update_fields))
            enriched += 1
            if index % 25 == 0:
                print(f"  ... {index}/{len(targets)} verarbeitet")
            time.sleep(0.2)  # light pacing, no need to hammer the API

        print("---")
        print(f"Angereichert: {enriched}")
        print(f"Übersprungen (keine Notiz-Details): {skipped_no_notes}")
        print(f"Übersprungen (LLM fand nichts Verwertbares): {skipped_no_result}")
        print(f"Fehlgeschlagen (API-/Parse-Fehler): {failed}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
