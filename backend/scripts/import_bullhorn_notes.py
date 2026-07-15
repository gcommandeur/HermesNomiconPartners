"""One-time data migration: replace the synthetic seed/test data with real
candidates reconstructed from a Bullhorn "Notes" export.

Run manually, once, with the backend stopped (avoids concurrent writes to the
same SQLite file):

    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\import_bullhorn_notes.py

What this does:
1. Wipes every row in every business-data table (candidates, client
   companies, submissions, notes, activities, tasks, job mandates, contacts,
   interviews/offers/placements/fees, documents, audit logs - everything
   except the users/auth tables) - all of it is synthetic seed data from
   initial project setup (example.com emails, a literal "Zzverify Kanzlei"
   test entry, etc.), not real business data. If anything real has been
   entered into the CRM since (e.g. real short_profile text saved on a test
   candidate during Phase 2 testing), it is lost - double check before
   running this if that matters.
2. Reads backend/data/imports/bullhorn_notes.csv (Bullhorn "Notes" export:
   328 activity entries across 308 unique candidate names, from 2025-02-28
   onward - source file was the user's original .XLS, converted to CSV).
3. Groups notes by normalised candidate name (case/whitespace-insensitive).
4. Creates one Candidate row per unique name. Name split is a simple "last
   word = last name" heuristic; ALL-CAPS source names are title-cased.
   Status is inferred from that candidate's MOST RECENT note's Bullhorn
   "Status" column ("DNU" -> blocked, everything else -> active) - a
   reasonable default, correct manually in the CRM where it's wrong.
5. Creates one Activity row per original note entry (drives the "Timeline"
   tab on the candidate detail page), linked to the matching candidate,
   preserving the original date/action/status/body text.

IMPORTANT LIMITATIONS - this is a best-effort reconstruction, not a full
candidate profile import:
- No email, phone, salary, notice period, or fachliche_schwerpunkte fields
  could be reliably extracted from this notes-only export. Those stay empty;
  Note Body text sometimes contains this info in free text (visible in the
  Timeline), but it was NOT auto-extracted into structured fields.
- Client/Kanzlei ("Verträge") data is NOT covered at all - the export
  contains zero client-company rows.
- anrede (Frau/Herr/divers, used for gendered profile texts) is left unset
  for every imported candidate - not derivable from a bare first name
  reliably enough to guess automatically.
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models import Activity, Base, Candidate  # noqa: E402
from cc_crm.models.enums import CandidateStatus, ClientStatus, JobStatus  # noqa: E402
from cc_crm.schemas.candidate import CandidateCreate  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.schemas.job_mandate import JobMandateCreate  # noqa: E402
from cc_crm.services.candidates import CandidateService  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402
from cc_crm.services.jobs import JobMandateService  # noqa: E402

# Importing cc_crm.models (above) runs models/__init__.py, which imports every
# model class in the app - that's what registers ALL tables (job mandates,
# contacts, interviews, tasks, etc., not just the four used directly below)
# on Base.metadata, which wipe_test_data() below relies on.

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "imports" / "bullhorn_notes.csv"
EXPECTED_HEADER = [
    "Department",
    "Note Author",
    "Date Note Added",
    "Type",
    "Note Action",
    "About",
    "Status",
    "Note Body",
]

# Auth infrastructure - not business/test data, must survive the wipe.
PRESERVED_TABLES = {"users", "auth_sessions", "api_keys"}


def wipe_test_data(session) -> None:
    """Deletes every row from every business-data table (all synthetic seed
    data from initial project setup), preserving only auth tables.

    Uses Base.metadata.sorted_tables (topologically sorted by FK dependency)
    in REVERSE so children are always deleted before their parents - correct
    regardless of how many models exist or get added later, and independent
    of whether SQLite foreign-key enforcement happens to be on.
    """
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in PRESERVED_TABLES:
            continue
        session.execute(table.delete())
    session.commit()


def normalise_name(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip())


def split_name(full_name: str) -> tuple[str, str]:
    parts = normalise_name(full_name).split(" ")
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return (parts[0].title() if parts else "Unbekannt"), "-"
    return " ".join(parts[:-1]).title(), parts[-1].title()


def parse_date(raw: str) -> datetime:
    return datetime.strptime(raw.strip(), "%m/%d/%Y")


def clean_body(raw: str) -> str:
    return raw.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n").strip()


def load_rows() -> list[list[str]]:
    with open(CSV_PATH, encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header_index = next(i for i, row in enumerate(rows) if row[:1] == ["Department"])
    if rows[header_index] != EXPECTED_HEADER:
        raise SystemExit(
            f"CSV header changed unexpectedly: {rows[header_index]!r} - "
            f"expected {EXPECTED_HEADER!r}. Aborting rather than importing "
            "possibly-misaligned columns."
        )
    return [row for row in rows[header_index + 1 :] if len(row) >= 8]


def main() -> None:
    data_rows = load_rows()

    session = SessionLocal()
    try:
        wipe_test_data(session)

        candidate_service = CandidateService(session)
        candidates_by_key: dict[str, Candidate] = {}

        latest_status_by_key: dict[str, tuple[datetime, str]] = {}
        for row in data_rows:
            _, _, date_raw, _type, _action, about, note_status, _body = row
            key = normalise_name(about).casefold()
            occurred = parse_date(date_raw)
            if key not in latest_status_by_key or occurred > latest_status_by_key[key][0]:
                latest_status_by_key[key] = (occurred, note_status.strip())

        activities_created = 0
        for row in data_rows:
            _, _author, date_raw, _type, action, about, note_status, body = row
            key = normalise_name(about).casefold()

            if key not in candidates_by_key:
                first_name, last_name = split_name(about)
                is_dnu = latest_status_by_key[key][1].upper() == "DNU"
                candidate = candidate_service.create(
                    CandidateCreate(
                        first_name=first_name,
                        last_name=last_name,
                        status=CandidateStatus.BLOCKED if is_dnu else CandidateStatus.ACTIVE,
                    )
                )
                candidates_by_key[key] = candidate

            candidate = candidates_by_key[key]
            action_label = action.strip() or "Note"
            subject = (
                f"{action_label} ({note_status.strip()})" if note_status.strip() else action_label
            )
            session.add(
                Activity(
                    candidate_id=candidate.id,
                    activity_type=action_label,
                    subject=subject[:240],
                    details=clean_body(body) or None,
                    occurred_at=parse_date(date_raw),
                )
            )
            activities_created += 1

        session.commit()
        print(f"Kandidaten angelegt: {len(candidates_by_key)}")
        print(f"Aktivitäten (Timeline-Einträge) importiert: {activities_created}")

        # Kein echter Kanzlei-Datensatz existiert noch (kommt separat) - eine
        # klar als TEST markierte Kanzlei + Teststelle, damit Matching gegen
        # die neuen echten Kandidaten schon jetzt ausprobiert werden kann.
        client_service = ClientCompanyService(session)
        test_client = client_service.create(
            ClientCompanyCreate(
                name="TEST - Steuerkanzlei München",
                status=ClientStatus.ACQUISITION,
                city="München",
                focus="Steuerberatung",
                notes=(
                    "Platzhalter-Testeintrag, KEINE echte Kanzlei - angelegt, um "
                    "Matching gegen die neu importierten echten Kandidaten zu "
                    "testen. Bitte löschen/ersetzen, sobald echte Kanzlei-Daten "
                    "vorliegen."
                ),
            )
        )
        job_service = JobMandateService(session)
        job_service.create(
            JobMandateCreate(
                client_company_id=test_client.id,
                title="Steuerberater (m/w/d) München - TESTSTELLE",
                status=JobStatus.OPEN,
                location="München",
                qualifications="Steuerberater/in",
                description=(
                    "Platzhalter-Teststelle, KEIN echtes Mandat - nur zum "
                    "Testen von Matching/Suche gegen die neu importierten "
                    "echten Kandidaten."
                ),
            )
        )
        print(f"Test-Kanzlei angelegt: {test_client.name} ({test_client.id})")
        print("Teststelle 'Steuerberater (m/w/d) München' angelegt.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
