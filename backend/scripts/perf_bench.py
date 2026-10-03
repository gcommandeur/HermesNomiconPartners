"""Messskript: Antwortzeiten der wichtigsten Abfragen bei realistischer Datenmenge.

Legt in einer WEGWERF-Datenbank Testdaten an (Standard: 50.000 Kandidaten,
500 Kanzleien, 5.000 Prozesse) und misst p50/p95/p99 ueber die echte FastAPI-App
(in-process, also inklusive Middleware und Serialisierung, aber ohne Netzwerk).
Schreibt optional einen Bericht nach docs/PERFORMANCE.md.

Sicherheit: arbeitet NUR mit einer Datenbank, deren Name "bench" oder "test"
enthaelt (CC_CRM_DATABASE_URL), und LEERT sie vorher - niemals gegen Produktion.

Usage (von backend/, mit aktivierter venv):

    CC_CRM_DATABASE_URL=postgresql+psycopg://user@localhost/cc_crm_bench \\
        python scripts/perf_bench.py --report ../docs/PERFORMANCE.md
"""

from __future__ import annotations

import argparse
import os
import platform
import random
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
# Keine Logzeile pro Messanfrage auf der Konsole.
os.environ.setdefault("CC_CRM_LOG_LEVEL", "WARNING")

from sqlalchemy import text  # noqa: E402

BUDGETS_MS = {
    "Kandidat oeffnen": 100,
    "Kandidatenliste (50, gefiltert)": 150,
    "Kandidatensuche (Freitext)": 200,
    "Kandidat speichern": 150,
    "Prozessliste (50)": 150,
    "Cockpit": 500,
}

FIRST = [
    "Anna",
    "Ben",
    "Clara",
    "David",
    "Eva",
    "Felix",
    "Greta",
    "Hans",
    "Ida",
    "Jonas",
    "Karla",
    "Lukas",
    "Mia",
    "Noah",
    "Olga",
    "Paul",
    "Rita",
    "Sven",
    "Tina",
    "Uwe",
]
LAST = [
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
]
CITIES = [
    ("Berlin", "10115"),
    ("Hamburg", "20095"),
    ("Muenchen", "80331"),
    ("Koeln", "50667"),
    ("Frankfurt", "60311"),
    ("Stuttgart", "70173"),
    ("Duesseldorf", "40213"),
    ("Leipzig", "04109"),
    ("Dresden", "01067"),
    ("Hannover", "30159"),
]
TITLES = [
    "Steuerberater",
    "Steuerfachangestellte",
    "Bilanzbuchhalter",
    "Wirtschaftspruefer",
    "Rechtsanwalt",
    "Fachanwalt Steuerrecht",
    "Lohnbuchhalter",
    "Finanzbuchhalter",
]


def _check_database(url: str) -> None:
    name = url.rsplit("/", 1)[-1].split("?")[0]
    if "bench" not in name and "test" not in name:
        raise SystemExit(
            f"Abbruch: Datenbank '{name}' - der Name muss 'bench' oder 'test' enthalten "
            "(das Skript leert die Datenbank)."
        )


def _percentiles(samples_ms: list[float]) -> tuple[float, float, float]:
    ordered = sorted(samples_ms)

    def pick(q: float) -> float:
        return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]

    return statistics.median(ordered), pick(0.95), pick(0.99)


def seed(candidates: int, clients: int, submissions: int) -> tuple[list[str], list[str]]:
    from cc_crm.core.security import hash_password
    from cc_crm.infrastructure.database.session import SessionLocal
    from cc_crm.models.candidate import Candidate
    from cc_crm.models.client_company import ClientCompany
    from cc_crm.models.submission import CandidateSubmission
    from cc_crm.models.user import User

    rng = random.Random(42)
    with SessionLocal() as session:
        tables = (
            ", ".join(
                row[0]
                for row in session.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                        "AND tablename <> 'alembic_version'"
                    )
                )
            )
            if session.get_bind().dialect.name == "postgresql"
            else ""
        )
        if tables:
            session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            session.commit()
        admin = User(
            email="bench@example.com", hashed_password=hash_password("bench"), role="admin"
        )
        session.add(admin)
        companies = [
            ClientCompany(name=f"Kanzlei {i:04d} {rng.choice(LAST)}") for i in range(clients)
        ]
        session.add_all(companies)
        session.commit()
        candidate_ids: list[str] = []
        for start in range(0, candidates, 5000):
            batch = []
            for i in range(start, min(start + 5000, candidates)):
                city, plz = rng.choice(CITIES)
                batch.append(
                    Candidate(
                        first_name=rng.choice(FIRST),
                        last_name=f"{rng.choice(LAST)}{i}",
                        email=f"kandidat{i}@example.com",
                        job_title=rng.choice(TITLES),
                        city=city,
                        postal_code=plz,
                        owner_user_id=admin.id,
                        summary="Erfahrene Fachkraft mit mehrjaehriger Berufserfahrung. " * 3,
                    )
                )
            session.add_all(batch)
            session.commit()
            candidate_ids.extend(str(item.id) for item in batch)
        for i in range(submissions):
            session.add(
                CandidateSubmission(
                    candidate_id=candidate_ids[i % len(candidate_ids)],
                    client_company_id=companies[i % len(companies)].id,
                    owner_user_id=admin.id,
                )
            )
        session.commit()
        return candidate_ids, [str(admin.id)]


def measure(candidate_ids: list[str], samples: int) -> dict[str, list[float]]:
    from fastapi.testclient import TestClient

    from cc_crm.infrastructure.database.session import SessionLocal
    from cc_crm.main import create_app
    from cc_crm.services.auth import AuthService

    with SessionLocal() as session:
        _, token = AuthService(session).login("bench@example.com", "bench")
    headers = {"Authorization": f"Bearer {token}"}
    rng = random.Random(7)
    results: dict[str, list[float]] = {name: [] for name in BUDGETS_MS}
    with TestClient(create_app()) as client:

        def timed(name: str, method: str, url: str, **kwargs: object) -> None:
            started = time.perf_counter()
            response = client.request(method, url, headers=headers, **kwargs)  # type: ignore[arg-type]
            elapsed = (time.perf_counter() - started) * 1000
            if response.status_code >= 400:
                raise SystemExit(f"{name}: HTTP {response.status_code} {response.text[:200]}")
            results[name].append(elapsed)

        for _ in range(3):  # Aufwaermen (Verbindungen, Caches), nicht gewertet
            client.get(f"/api/v1/candidates/{candidate_ids[0]}", headers=headers)
        for i in range(samples):
            cid = rng.choice(candidate_ids)
            city, _ = rng.choice(CITIES)
            term = f"{rng.choice(LAST)}{rng.randint(0, 9999)}"
            timed("Kandidat oeffnen", "GET", f"/api/v1/candidates/{cid}")
            timed(
                "Kandidatenliste (50, gefiltert)",
                "GET",
                "/api/v1/candidates",
                params={"region": city, "limit": 50, "sort_by": "name"},
            )
            timed(
                "Kandidatensuche (Freitext)",
                "GET",
                "/api/v1/candidates",
                params={"search": term, "limit": 50},
            )
            timed(
                "Kandidat speichern",
                "PATCH",
                f"/api/v1/candidates/{cid}",
                json={"next_step": f"Rueckruf {i}"},
            )
            timed("Prozessliste (50)", "GET", "/api/v1/submissions", params={"limit": 50})
            if i % 5 == 0:  # Cockpit ist schwer, seltener messen
                timed("Cockpit", "GET", "/api/v1/cockpit")
    return results


def report(results: dict[str, list[float]], sizes: tuple[int, int, int], dialect: str) -> str:
    lines = [
        "| Vorgang | Ziel (p95) | p50 | p95 | p99 | Messungen | Ergebnis |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, budget in BUDGETS_MS.items():
        samples = results.get(name) or []
        if not samples:
            lines.append(f"| {name} | < {budget} ms | - | - | - | 0 | **nicht gemessen** |")
            continue
        p50, p95, p99 = _percentiles(samples)
        verdict = "innerhalb" if p95 < budget else "**ueber dem Ziel**"
        lines.append(
            f"| {name} | < {budget} ms | {p50:.1f} ms | {p95:.1f} ms | {p99:.1f} ms "
            f"| {len(samples)} | {verdict} |"
        )
    candidates, clients, submissions = sizes
    return (
        "\n".join(lines) + f"\n\nDatenbestand: {candidates:,} Kandidaten, {clients:,} Kanzleien, "
        f"{submissions:,} Prozesse. Datenbank: {dialect}.\n"
        f"Gemessen am {datetime.now(UTC):%Y-%m-%d} auf {platform.system()} {platform.machine()}, "
        f"Python {platform.python_version()}, in-process "
        "(ohne Netzwerk, ohne DigitalOcean-Latenz).\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--candidates", type=int, default=50_000)
    parser.add_argument("--clients", type=int, default=500)
    parser.add_argument("--submissions", type=int, default=5_000)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--report", type=Path, help="Markdown-Bericht hierhin schreiben")
    args = parser.parse_args()

    from cc_crm.core.config import get_settings
    from cc_crm.core.migrations import ensure_database_at_head

    url = get_settings().resolved_database_url
    _check_database(url)
    ensure_database_at_head()
    print(f"Lege Testdaten an ({args.candidates:,} Kandidaten) ...", flush=True)
    candidate_ids, _ = seed(args.candidates, args.clients, args.submissions)
    print("Messe ...", flush=True)
    results = measure(candidate_ids, args.samples)
    from cc_crm.infrastructure.database.session import engine

    text_report = report(
        results, (args.candidates, args.clients, args.submissions), engine.dialect.name
    )
    print(text_report)
    if args.report:
        args.report.write_text(
            "# Leistung: Ziele und letzte Messung\n\n"
            "Erzeugt von `backend/scripts/perf_bench.py`. **Das ist eine Messung auf einem "
            "Rechner an einem Tag, kein Garantiewert.** Vorgaenge ohne Messung stehen als "
            '"nicht gemessen" da, damit ein fehlender Eintrag nicht wie ein erfuellter wirkt.\n\n'
            + text_report,
            encoding="utf-8",
        )
        print(f"Bericht: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
