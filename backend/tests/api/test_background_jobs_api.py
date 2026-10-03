"""Admin-Ansicht der Hintergrundjobs und die Umstellung der Aufrufer auf die Warteschlange."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.background_job import BackgroundJob
from cc_crm.services.job_queue import enqueue, process_one
from tests.api.test_team_lead import Person, _make_user


def _admin(session_factory: sessionmaker[Session]) -> Person:
    return _make_user(session_factory, "admin@jobs.example", "admin", "Admin")


def test_only_admin_sees_and_retries_jobs(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin = _admin(session_factory)
    with session_factory() as session:
        job = enqueue(session, "gibt.es.nicht", {"geheim": "x"}, max_attempts=1)
        job_id = str(job.id)
    process_one(session_factory)

    assert client.get("/api/v1/background-jobs").status_code == 403
    assert client.post(f"/api/v1/background-jobs/{job_id}/retry").status_code == 403

    listing = client.get("/api/v1/background-jobs?status=failed", headers=admin.headers)
    assert listing.status_code == 200
    rows = listing.json()
    assert [row["id"] for row in rows] == [job_id]
    assert "payload" not in rows[0]  # keine Nutzdaten in der Ansicht

    retried = client.post(f"/api/v1/background-jobs/{job_id}/retry", headers=admin.headers)
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    # Ein wartender Job ist nicht "fehlgeschlagen" -> kein erneutes Anstossen.
    again = client.post(f"/api/v1/background-jobs/{job_id}/retry", headers=admin.headers)
    assert again.status_code >= 400


def test_sourcing_scan_all_is_enqueued_not_run_inline(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    company = client.post("/api/v1/clients", json={"name": "Kanzlei X", "website": "https://x.de"})
    assert company.status_code == 201, company.text
    response = client.post(
        "/api/v1/sourcing/run",
        json={"source_type": "kanzlei_team_page", "scan_all_companies": True},
    )
    assert response.status_code == 200, response.text
    with session_factory() as session:
        jobs = session.scalars(select(BackgroundJob)).all()
    assert [job.kind for job in jobs] == ["sourcing.team_pages"]
    assert jobs[0].max_attempts == 1
    assert jobs[0].payload["run_id"] == str(response.json()["run_id"])
