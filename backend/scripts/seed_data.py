"""Repeatable seed/reset tool for CC CRM test data.

Generates realistic-looking Kanzleien, Kontakte, Kandidaten, Vakanzen und
Prozesse (CandidateSubmissions) for eine Recruiting-Firma im Steuer-,
Wirtschaftspruefungs- und Rechtsberatungsfeld. Volumes are fully
parameterizable so the same tool can add or remove any amount of data.

Usage (from backend/, with the venv active):

    python scripts/seed_data.py seed --clients 12 --candidates 40
    python scripts/seed_data.py seed --clients 100 --candidates 500  # larger volume
    python scripts/seed_data.py seed --candidates 60 --staffing 8   # NOMICON: mit Ueberlassung
    python scripts/seed_data.py clear
    python scripts/seed_data.py stats
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.core.security import hash_password  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models import Base  # noqa: E402
from cc_crm.models.enums import (  # noqa: E402
    ClientStatus,
    JobStatus,
    SubmissionCancellationReason,
    SubmissionStatus,
    TaskPriority,
)
from cc_crm.models.user import User  # noqa: E402
from cc_crm.schemas.candidate import CandidateCreate  # noqa: E402
from cc_crm.schemas.client_company import ClientCompanyCreate  # noqa: E402
from cc_crm.schemas.contact_person import ContactPersonCreate  # noqa: E402
from cc_crm.schemas.job_mandate import JobMandateCreate  # noqa: E402
from cc_crm.schemas.recruiting import (  # noqa: E402
    FeeCreate,
    InterviewCreate,
    OfferCreate,
    PlacementCreate,
)
from cc_crm.schemas.submission import (  # noqa: E402
    CandidateSubmissionCreate,
    CandidateSubmissionTransition,
)
from cc_crm.services.candidates import CandidateService  # noqa: E402
from cc_crm.services.clients import ClientCompanyService  # noqa: E402
from cc_crm.services.contacts import ContactPersonService  # noqa: E402
from cc_crm.services.jobs import JobMandateService  # noqa: E402
from cc_crm.services.recruiting import RecruitingProcessService  # noqa: E402
from cc_crm.services.submissions import CandidateSubmissionService  # noqa: E402

FIRST_NAMES = [
    "Anna",
    "Lukas",
    "Mia",
    "Jonas",
    "Laura",
    "Felix",
    "Sarah",
    "Tim",
    "Julia",
    "Maximilian",
    "Lea",
    "Paul",
    "Sophie",
    "David",
    "Hannah",
    "Niklas",
    "Emma",
    "Fabian",
    "Marie",
    "Simon",
    "Lena",
    "Jan",
    "Nina",
    "Moritz",
    "Clara",
    "Sebastian",
    "Johanna",
    "Philipp",
    "Katharina",
    "Daniel",
    "Isabel",
    "Tobias",
    "Franziska",
    "Christian",
    "Vanessa",
    "Alexander",
    "Melanie",
    "Florian",
    "Sandra",
]
LAST_NAMES = [
    "Mueller",
    "Schmidt",
    "Schneider",
    "Fischer",
    "Weber",
    "Meyer",
    "Wagner",
    "Becker",
    "Schulz",
    "Hoffmann",
    "Koch",
    "Richter",
    "Klein",
    "Wolf",
    "Neumann",
    "Schwarz",
    "Zimmermann",
    "Braun",
    "Kruger",
    "Hofmann",
    "Lange",
    "Schmitt",
    "Werner",
    "Schmitz",
    "Krause",
    "Meier",
    "Lehmann",
    "Huber",
    "Mayer",
    "Herrmann",
]
CITIES = [
    ("Muenchen", "80331"),
    ("Frankfurt am Main", "60311"),
    ("Duesseldorf", "40213"),
    ("Hamburg", "20095"),
    ("Koeln", "50667"),
    ("Stuttgart", "70173"),
    ("Berlin", "10117"),
    ("Mannheim", "68159"),
    ("Nuernberg", "90402"),
    ("Essen", "45127"),
    ("Leipzig", "04109"),
    ("Hannover", "30159"),
]

QUALIFICATION_TRACKS = {
    "tax": {
        "titles": [
            "Steuerberater/in",
            "Steuerfachangestellte/r",
            "Tax Manager",
            "Tax Senior Associate",
            "Bilanzbuchhalter/in",
            "Steuerassistent/in",
        ],
        "qualifications": [
            "Steuerberaterexamen",
            "Bilanzbuchhalter IHK",
            "Fachassistent Lohn und Gehalt",
            "Diplom-Finanzwirt",
            "Master of Taxation",
        ],
        "firm_kind": "Steuerberatung",
        "firm_names": [
            "Steuerkanzlei {city}",
            "{last} Steuerberatung",
            "{last} & Partner Steuerberater",
            "TaxPoint {city}",
            "{last} Steuerberatungsgesellschaft",
        ],
    },
    "audit": {
        "titles": [
            "Wirtschaftspruefer/in",
            "Audit Manager",
            "Audit Senior Associate",
            "Pruefungsassistent/in",
            "Head of Audit",
            "WP-Assistent/in",
        ],
        "qualifications": [
            "Wirtschaftspruefer-Examen",
            "CPA",
            "ACCA",
            "Diplom-Kaufmann Audit",
            "Master Accounting and Auditing",
        ],
        "firm_kind": "Wirtschaftspruefung",
        "firm_names": [
            "{last} Wirtschaftspruefung",
            "Audit Partners {city}",
            "{last} & Kollegen WP",
            "Pruefungsgesellschaft {city}",
            "{last} Revision GmbH",
        ],
    },
    "legal": {
        "titles": [
            "Rechtsanwalt/Rechtsanwaeltin",
            "Associate",
            "Senior Associate",
            "Counsel",
            "Legal Counsel",
            "Fachanwalt/Fachanwaeltin fuer Steuerrecht",
        ],
        "qualifications": [
            "2. Staatsexamen",
            "Fachanwalt Steuerrecht",
            "LL.M.",
            "Fachanwalt Arbeitsrecht",
            "Zulassung als Rechtsanwalt",
        ],
        "firm_kind": "Rechtsberatung",
        "firm_names": [
            "Kanzlei {last}",
            "{last} Rechtsanwaelte",
            "{last} & Partner Rechtsanwaelte",
            "Legal Partners {city}",
            "{last} Law Office",
        ],
    },
}

STREET_NAMES = ["Bahnhofstrasse", "Hauptstrasse", "Kaiserallee", "Marktplatz"]
CANDIDATE_TRAITS = [
    "mandantenorientiert",
    "analytisch stark",
    "teamorientiert",
    "mit internationaler Erfahrung",
]

CLIENT_STATUS_WEIGHTS = [
    (ClientStatus.ACTIVE, 5),
    (ClientStatus.ACQUISITION, 3),
    (ClientStatus.BLOCKED, 1),
    (ClientStatus.ARCHIVED, 1),
]

SUBMISSION_STATUS_FLOW = [
    SubmissionStatus.QUALIFICATION_CALL,
    SubmissionStatus.CV_IN,
    SubmissionStatus.CV_OUT,
    SubmissionStatus.INTERVIEW,
    SubmissionStatus.OFFER,
    SubmissionStatus.PLACEMENT,
    SubmissionStatus.CANCELLED,
]

CANCELLATION_REASONS = [
    SubmissionCancellationReason.CANDIDATE_REJECTED,
    SubmissionCancellationReason.CLIENT_REJECTED,
    SubmissionCancellationReason.CANDIDATE_GHOSTING,
]

JOB_PRIORITY_WEIGHTS = [
    (TaskPriority.LOW, 2),
    (TaskPriority.NORMAL, 5),
    (TaskPriority.HIGH, 3),
    (TaskPriority.URGENT, 1),
]


def weighted_choice(pairs: list[tuple]) -> object:
    population, weights = zip(*pairs, strict=True)
    return random.choices(population, weights=weights, k=1)[0]


def make_email(first: str, last: str, domain: str) -> str:
    return f"{first.lower()}.{last.lower()}@{domain}"


def seed_clients(session, count: int) -> list:
    service = ClientCompanyService(session)
    contact_service = ContactPersonService(session)
    job_service = JobMandateService(session)
    clients = []
    tracks = list(QUALIFICATION_TRACKS.keys())
    used_names: set[str] = set()

    for i in range(count):
        track_key = tracks[i % len(tracks)]
        track = QUALIFICATION_TRACKS[track_key]
        last = random.choice(LAST_NAMES)
        city, postal = random.choice(CITIES)
        name_template = random.choice(track["firm_names"])
        name = name_template.format(last=last, city=city)
        if name in used_names:
            name = f"{name} {i}"
        used_names.add(name)
        status = weighted_choice(CLIENT_STATUS_WEIGHTS)
        domain_stub = name.lower().replace(" ", "").replace("&", "").replace("/", "")[:20]
        domain = f"{domain_stub}{i}.example.com"

        client = service.create(
            ClientCompanyCreate(
                name=name,
                status=status,
                website=f"https://www.{domain}",
                email=f"kontakt@{domain}",
                phone=f"+49 {random.randint(30, 911)} {random.randint(1000000, 9999999)}",
                street=(f"{random.choice(STREET_NAMES)} {random.randint(1, 90)}"),
                postal_code=postal,
                city=city,
                region=track["firm_kind"],
                company_size=random.choice(["10-50", "50-200", "200-500", "500+"]),
                focus=track["firm_kind"],
                fee_percentage=random.choice(["25.00", "27.00", "30.00"]),
                terms_status=random.choice(["not_sent", "sent", "signed"]),
            )
        )
        clients.append((client, track_key))

        primary_first = random.choice(FIRST_NAMES)
        contact_service.create(
            ContactPersonCreate(
                client_company_id=client.id,
                first_name=primary_first,
                last_name=last,
                role_title=random.choice(
                    ["Partner/in", "Personalleitung", "Geschaeftsfuehrung", "HR Manager"]
                ),
                email=make_email(primary_first, last, domain),
                phone=f"+49 {random.randint(150, 179)} {random.randint(1000000, 9999999)}",
                is_primary=True,
            )
        )
        if random.random() < 0.4:
            second_first = random.choice(FIRST_NAMES)
            second_last = random.choice(LAST_NAMES)
            contact_service.create(
                ContactPersonCreate(
                    client_company_id=client.id,
                    first_name=second_first,
                    last_name=second_last,
                    role_title=random.choice(
                        ["Recruiting", "Office Management", "Associate Partner"]
                    ),
                    email=make_email(second_first, second_last, domain),
                    is_primary=False,
                )
            )

        if random.random() < 0.7:
            salary_min = random.choice([55000, 65000, 80000])
            salary_max = salary_min + random.choice([15000, 25000, 40000])
            job_service.create(
                JobMandateCreate(
                    client_company_id=client.id,
                    title=random.choice(track["titles"]),
                    status=random.choice(
                        [JobStatus.OPEN, JobStatus.OPEN, JobStatus.DRAFT, JobStatus.ON_HOLD]
                    ),
                    priority=weighted_choice(JOB_PRIORITY_WEIGHTS),
                    location=city,
                    search_radius_km=random.choice([20, 30, 50]),
                    work_model=random.choice(["Hybrid", "Remote", "Vor Ort"]),
                    qualifications=random.choice(track["qualifications"]),
                    experience=random.choice(["1-3 Jahre", "3-5 Jahre", "5+ Jahre"]),
                    description=(
                        f"Suchprofil fuer {track['firm_kind']} bei {client.name}, "
                        f"Schwerpunkt {random.choice(track['qualifications'])}."
                    ),
                    must_have=random.sample(track["qualifications"], k=2),
                    nice_to_have=random.sample(track["titles"], k=2),
                    salary_min=salary_min,
                    salary_max=salary_max,
                )
            )

    return clients


def seed_candidates(session, count: int) -> list:
    service = CandidateService(session)
    candidates = []
    tracks = list(QUALIFICATION_TRACKS.keys())

    for i in range(count):
        track_key = tracks[i % len(tracks)]
        track = QUALIFICATION_TRACKS[track_key]
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        city, postal = random.choice(CITIES)
        candidate = service.create(
            CandidateCreate(
                candidate_number=f"CAND-{1000 + i}",
                first_name=first,
                last_name=last,
                email=make_email(f"{first}{i}", last, "example.com"),
                phone=f"+49 {random.randint(150, 179)} {random.randint(1000000, 9999999)}",
                job_title=random.choice(track["titles"]),
                qualification=random.choice(track["qualifications"]),
                postal_code=postal,
                city=city,
                salary_expectation=f"{random.randint(55, 140)}.000 EUR",
                notice_period=random.choice(
                    ["sofort verfuegbar", "1 Monat", "3 Monate", "6 Monate"]
                ),
                cv_available=random.random() < 0.75,
                consent_received=True,
                summary=(
                    f"{random.choice(track['titles'])} mit Schwerpunkt "
                    f"{track['firm_kind']}, {random.choice(CANDIDATE_TRAITS)}."
                ),
            )
        )
        candidates.append((candidate, track_key))

    return candidates


def _seed_user(session) -> User:
    """Interviews werden ueber die API immer von einem eingeloggten Nutzer
    angelegt (der auch der Owner des automatisch erzeugten Kalendertermins
    wird, siehe services/recruiting.py::create_interview) - dieses Skript
    laeuft ausserhalb eines HTTP-Requests und hat daher keinen echten Nutzer.
    Ersten vorhandenen Nutzer wiederverwenden, sonst einen Platzhalter
    anlegen (nur fuer Seed-Zwecke, kein echter Login gedacht)."""
    user = session.scalar(select(User))
    if user is not None:
        return user
    user = User(email="seed-script@cc-crm.local", hashed_password=hash_password("not-a-real-login"))
    session.add(user)
    session.flush()
    return user


def seed_submissions(session, clients: list, candidates: list, count: int) -> None:
    service = CandidateSubmissionService(session)
    recruiting = RecruitingProcessService(session)
    seed_user = _seed_user(session)
    now = datetime.now(UTC)
    used_pairs: set[tuple] = set()
    created = 0
    attempts = 0
    max_attempts = count * 10

    while created < count and attempts < max_attempts:
        attempts += 1
        candidate, track_key = random.choice(candidates)
        same_track_clients = [c for c, key in clients if key == track_key and c.status != "blocked"]
        pool = same_track_clients or [c for c, _ in clients]
        client = random.choice(pool)
        # Early-stage processes (quali call/cv-in/cv-out) may not have a Kanzlei
        # yet - only from the interview stage on is a client mandatory. The
        # dedup key always uses client.id (not None) because the client gets
        # attached to the submission at the latest once it reaches interview.
        has_client_from_start = random.random() < 0.6
        pair = (candidate.id, client.id)
        if pair in used_pairs:
            continue
        used_pairs.add(pair)
        target = random.choice(SUBMISSION_STATUS_FLOW)

        try:
            submission = service.create(
                CandidateSubmissionCreate(
                    candidate_id=candidate.id,
                    client_company_id=client.id if has_client_from_start else None,
                    salary_at_submission=candidate.salary_expectation,
                    next_step=random.choice(
                        [
                            "Quali Call vereinbaren",
                            "CV anfordern",
                            "Kanzlei auswaehlen",
                            "Interview vereinbaren",
                        ]
                    ),
                    follow_up_at=now + timedelta(days=random.randint(1, 10)),
                    owner=random.choice(["Team Recruiting", "M. Weber", "S. Klein"]),
                    owner_user_id=seed_user.id,  # NOMICON: Seed-Prozesse haben einen Verantwortlichen
                )
            )
        except Exception:
            continue
        created += 1

        try:
            if target == SubmissionStatus.QUALIFICATION_CALL:
                continue
            if target == SubmissionStatus.CANCELLED:
                steps = random.randint(0, 2)
                for next_status in (SubmissionStatus.CV_IN, SubmissionStatus.CV_OUT)[:steps]:
                    service.transition(
                        submission.id, CandidateSubmissionTransition(status=next_status)
                    )
                service.transition(
                    submission.id,
                    CandidateSubmissionTransition(
                        status=SubmissionStatus.CANCELLED,
                        cancellation_reason=random.choice(CANCELLATION_REASONS),
                    ),
                )
                continue

            service.transition(
                submission.id, CandidateSubmissionTransition(status=SubmissionStatus.CV_IN)
            )
            if target == SubmissionStatus.CV_IN:
                continue

            service.transition(
                submission.id, CandidateSubmissionTransition(status=SubmissionStatus.CV_OUT)
            )
            if target == SubmissionStatus.CV_OUT:
                continue

            # From here on, a Kanzlei is mandatory - assign it now if not set yet.
            service.transition(
                submission.id,
                CandidateSubmissionTransition(
                    status=SubmissionStatus.INTERVIEW,
                    client_company_id=None if has_client_from_start else client.id,
                ),
            )
            recruiting.create_interview(
                submission.id,
                InterviewCreate(
                    scheduled_at=now + timedelta(days=random.randint(2, 14)),
                    interview_type=random.choice(
                        ["Erstgespraech", "Fachgespraech", "Partnerrunde"]
                    ),
                    location_or_link=random.choice(["vor Ort", "MS Teams", "Zoom"]),
                    participants=[f"{candidate.first_name} {candidate.last_name}"],
                ),
                seed_user,
            )
            if target == SubmissionStatus.INTERVIEW:
                continue

            service.transition(
                submission.id, CandidateSubmissionTransition(status=SubmissionStatus.OFFER)
            )
            offered_salary = random.randint(60, 140) * 1000
            recruiting.create_offer(
                submission.id,
                OfferCreate(
                    offered_salary=offered_salary,
                    variable_compensation=random.choice([0, 5000, 10000]),
                    start_date=(now + timedelta(days=60)).date(),
                ),
            )
            if target == SubmissionStatus.OFFER:
                continue

            service.transition(
                submission.id, CandidateSubmissionTransition(status=SubmissionStatus.PLACEMENT)
            )
            placement = recruiting.create_placement(
                submission.id,
                PlacementCreate(
                    start_date=(now + timedelta(days=45)).date(),
                    final_salary=offered_salary,
                    fee_percentage=client.fee_percentage,
                    guarantee_period_months=client.guarantee_period_months,
                ),
            )
            recruiting.create_fee(
                placement.id,
                FeeCreate(
                    amount_net=placement.calculated_fee,
                    invoice_status=random.choice(["draft", "issued", "due", "paid"]),
                ),
            )
        except Exception:
            # Statusautomat/Geschaeftsregeln lehnen seltene Zufallspfade ab -
            # Submission bleibt im letzten gueltigen Status.
            pass


def cmd_seed(args: argparse.Namespace) -> None:
    random.seed(args.random_seed)
    with SessionLocal() as session:
        clients = seed_clients(session, args.clients)
        candidates = seed_candidates(session, args.candidates)
        seed_submissions(session, clients, candidates, args.submissions)
        if args.staffing:  # NOMICON: Dummy-Daten der Arbeitnehmerueberlassung
            from seed_staffing import seed_staffing

            staffing = seed_staffing(session, args.staffing, random.Random(args.random_seed))
            print(
                f"Ueberlassung: {staffing.workers} Leiharbeitnehmer, "
                f"{staffing.contracts} Vertraege, {staffing.assignments} Einsaetze."
            )
    print(
        f"Seed abgeschlossen: {args.clients} Kanzleien, "
        f"{args.candidates} Kandidaten, {args.submissions} Prozesse."
    )


AUTH_TABLES = {"users", "auth_sessions"}


def cmd_clear(_args: argparse.Namespace) -> None:
    with SessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in AUTH_TABLES:
                continue
            session.execute(table.delete())
        session.commit()
    print("Alle Geschaeftsdaten wurden entfernt (Logins bleiben erhalten).")


def cmd_stats(_args: argparse.Namespace) -> None:
    from sqlalchemy import func, select

    with SessionLocal() as session:
        for table in Base.metadata.sorted_tables:
            result = session.execute(select(func.count()).select_from(table)).scalar_one()
            print(f"{table.name}: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CC CRM Testdaten-Werkzeug")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Testdaten hinzufuegen (beliebige Menge)")
    seed_parser.add_argument("--clients", type=int, default=12)
    seed_parser.add_argument("--candidates", type=int, default=40)
    seed_parser.add_argument("--submissions", type=int, default=25)
    seed_parser.add_argument("--random-seed", type=int, default=None)
    # NOMICON: Anzahl Leiharbeitnehmer (Arbeitnehmerueberlassung), 0 = keine
    seed_parser.add_argument("--staffing", type=int, default=0)
    seed_parser.set_defaults(func=cmd_seed)

    clear_parser = subparsers.add_parser("clear", help="Alle Geschaeftsdaten entfernen")
    clear_parser.set_defaults(func=cmd_clear)

    stats_parser = subparsers.add_parser("stats", help="Zeilenzahl je Tabelle anzeigen")
    stats_parser.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
