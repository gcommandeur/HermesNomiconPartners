"""Generates anonymised candidate short-profiles for outbound CV-Outs.

The prompt and rules here are the Commandeur Consulting house style for
candidate profiles sent to Kanzleien - see docs/ for the original spec.

IMPORTANT: `wechselgrund` and `no_gos` are internal-only fields (visible in
the CRM, editable by the consultant) and must NEVER be included in the data
sent to the LLM or in any generated/outgoing document. This is enforced in
`_build_quali_call_payload` below, not just by prompt instruction.
"""

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from cc_crm.integrations.ai.anthropic_client import generate_text
from cc_crm.models.candidate import Candidate
from cc_crm.services.candidates import CandidateService

SYSTEM_PROMPT = """Du bist Recruiting-Assistent für eine auf Steuern, Wirtschaftsprüfung und
Rechtskanzleien spezialisierte Personalberatung. Du erstellst aus strukturierten
Quali-Call-Daten ein anonymisiertes Kurzprofil für den Versand an Kanzleien.

REGELN:
- Vollständige Anonymität: keine Namen, keine Arbeitgeber-Klarnamen, keine
  Ausbildungsstätten mit Klarnamen sofern sie identifizierend wirken könnten.
  Beschreibe Stationen funktional ("mittelständische Kanzlei in NRW,
  ca. 40 Mitarbeitende" statt Firmenname).
- Das Profil muss trotzdem stark und konkret genug sein, dass eine Kanzlei
  darauf reagiert – vage Formulierungen vermeiden.
- Ton: professionell, sachlich, wie eine Kurzvorstellung — kein Marketing-Sprech.
- Nutze ausschließlich Informationen aus den gelieferten Daten. Erfinde
  nichts hinzu, auch keine plausibel klingenden Details.
- Wenn ein Feld leer ist, lasse den entsprechenden Punkt im Profil weg,
  statt Platzhalter zu erzeugen.
- wechselgrund und noGos NIEMALS in die Ausgabe übernehmen — nur interne Felder.
- Korrekte deutsche Groß-/Kleinschreibung und Grammatik sind Pflicht (Substantive
  großschreiben, korrekte Kommasetzung) — dieser Text geht direkt an Kanzleien,
  Fehler wirken unprofessionell.
- Gendern nach dem Feld "anrede":
  - "frau" → Kopfzeile "Kandidatin-Nr.", im Fließtext "Die Kandidatin", "sie", "ihre"
  - "herr" → Kopfzeile "Kandidat-Nr.", im Fließtext "Der Kandidat", "er", "seine"
  - "divers" oder nicht gesetzt → Kopfzeile "Kandidat:in-Nr.", im Fließtext
    neutral formulieren (z.B. "Die Person", "diese Fachkraft") statt zu raten

AUSGABEFORMAT (exakt dieses Format — 1:1 aus den bestehenden Commandeur-
Consulting-Kandidatenprofilen übernommen, NICHT davon abweichen):

## [Kandidatin-Nr. / Kandidat-Nr. / Kandidat:in-Nr., je nach anrede] [Kandidatennummer]

**Überblick**
Wohnort: [zielregion, nur Region z.B. "Raum Reutlingen", keine genaue Adresse]
Ausbildung/Weiterbildung: [ausbildungTitel]
Berufserfahrung: [berufserfahrungJahre, gerundet z.B. "15+ Jahre"]
Gehaltsvorstellung: [gehaltswunsch, gerundet z.B. "ca. 70.000 € p.a."]
Verfügbarkeit / Kündigungsfrist: [kuendigungsfrist]

**Kurzprofil**
[3-4 Sätze Fließtext: Wer ist diese Person beruflich, was macht sie interessant
für eine Kanzlei? Aus freitextNotizen und Kernfeldern destilliert.]

**Fachliche Qualifikationen**
[Bullet-Liste aus fachlicheSchwerpunkte, 4-8 Punkte]

**Lebenslauf (Auszug)**
[Zeitraum] [Rolle], [anonymisierter Arbeitgeber-Typ — NIEMALS Firmenname, nur
generische Beschreibung wie "Steuerkanzlei", "Steuerberatungsgesellschaft",
"internationale Wirtschaftskanzlei", "mittelständisches Unternehmen",
"öffentliche Institution" — aus aktuellesUmfeld/beruflicheStationen ableiten]
[eine Zeile pro Station, neueste zuerst]

**Ausbildung & Weiterbildung**
[aus ausbildungTitel, ggf. mit Zeiträumen falls in den Daten vorhanden]

**Weitere Infos**
Sprachen: [falls vorhanden, sonst weglassen]
EDV/Tools: [falls vorhanden, sonst weglassen]

Gib ausschließlich das fertige Profil zurück, keine Erklärungen davor oder danach."""


def _total_experience_years(stations: list[dict[str, Any]]) -> float | None:
    if not stations:
        return None
    total = 0.0
    for station in stations:
        try:
            total += float(station.get("dauer_jahre") or 0)
        except (TypeError, ValueError):
            continue
    return total or None


def _build_quali_call_payload(candidate: Candidate) -> dict[str, Any]:
    # wechselgrund and no_gos are intentionally NOT included here - internal
    # only, must never reach the LLM or an outgoing document.
    return {
        "anrede": candidate.anrede.value if candidate.anrede else None,
        "rolle": candidate.job_title,
        "gehaltswunsch": candidate.salary_expectation,
        "kuendigungsfrist": candidate.notice_period,
        "region": candidate.city or candidate.postal_code,
        "profil": candidate.summary,
        "fachlicheSchwerpunkte": candidate.fachliche_schwerpunkte or [],
        "ausbildungTitel": candidate.ausbildung_titel,
        "berufserfahrungJahre": _total_experience_years(candidate.berufliche_stationen or []),
        "beruflicheStationen": candidate.berufliche_stationen or [],
        "aktuellesUmfeld": {
            "kanzleityp": candidate.aktuelles_umfeld_kanzleityp,
            "kanzleigroesse": candidate.aktuelles_umfeld_kanzleigroesse,
        },
        "freitextNotizen": candidate.freitext_notizen,
    }


class ProfileGeneratorService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.candidates = CandidateService(session)

    def generate_anonymous_profile(self, candidate_id: uuid.UUID) -> str:
        candidate = self.candidates.get(candidate_id)
        quali_call_data = _build_quali_call_payload(candidate)
        user_message = (
            f"Kandidatennummer: {candidate.candidate_number or candidate.id}\n\n"
            f"Quali-Call-Daten:\n{json.dumps(quali_call_data, ensure_ascii=False, indent=2)}"
        )
        return generate_text(system_prompt=SYSTEM_PROMPT, user_message=user_message)
