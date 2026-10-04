"""Prozesse ohne Verantwortlichen (Review 2026-10-04, Punkt 4): Neuanlage ohne Owner ist nicht
mehr moeglich, Nicht-Admins sehen solche Altprozesse weiterhin nicht, Admins sehen sie in einer
eigenen Liste und koennen sie zuweisen (Audit)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.schemas.submission import CandidateSubmissionCreate
from cc_crm.services.submissions import CandidateSubmissionService
from tests.api.test_team_lead import Person, _make_user


def _candidate(client: TestClient, person: Person, last_name: str = "Altlast") -> str:
    response = client.post(
        "/api/v1/candidates",
        json={"first_name": "Erika", "last_name": last_name},
        headers=person.headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _unowned(session_factory: sessionmaker[Session], candidate_id: str) -> str:
    """Ein Prozess aus der Zeit vor dem Owner-Feld (direkt in der Datenbank)."""
    with session_factory() as session:
        submission = CandidateSubmission(candidate_id=uuid.UUID(candidate_id))
        session.add(submission)
        session.commit()
        return str(submission.id)


@pytest.fixture
def people(client: TestClient, session_factory: sessionmaker[Session]) -> dict[str, Person]:
    return {
        "admin": _make_user(session_factory, "chef@own.example", "admin", "Chefin"),
        "member": _make_user(session_factory, "m@own.example", "member", "Mitarbeiter"),
        "lead": _make_user(session_factory, "tl@own.example", "team_lead", "Teamleiter"),
    }


def _ids(client: TestClient, person: Person) -> set[str]:
    response = client.get("/api/v1/submissions", headers=person.headers)
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


def test_service_refuses_to_create_a_process_without_owner(
    client: TestClient, session_factory: sessionmaker[Session], people: dict[str, Person]
) -> None:
    candidate_id = _candidate(client, people["member"])
    with session_factory() as session, pytest.raises(BusinessRuleError):
        CandidateSubmissionService(session).create(
            CandidateSubmissionCreate(candidate_id=uuid.UUID(candidate_id))
        )


def test_api_create_without_owner_uses_the_current_user(
    client: TestClient, people: dict[str, Person]
) -> None:
    candidate_id = _candidate(client, people["member"])
    response = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate_id}, headers=people["member"].headers
    )
    assert response.status_code == 201, response.text
    assert response.json()["owner_user_id"] == people["member"].id


def test_non_admins_still_do_not_see_an_unowned_process(
    client: TestClient, session_factory: sessionmaker[Session], people: dict[str, Person]
) -> None:
    submission_id = _unowned(session_factory, _candidate(client, people["member"]))
    for role in ("member", "lead"):
        assert submission_id not in _ids(client, people[role]), role
        direct = client.get(f"/api/v1/submissions/{submission_id}", headers=people[role].headers)
        assert direct.status_code == 404, role
    assert submission_id in _ids(client, people["admin"])  # Vorbedingung: es existiert wirklich


def test_only_admin_sees_the_unowned_list_with_names(
    client: TestClient, session_factory: sessionmaker[Session], people: dict[str, Person]
) -> None:
    submission_id = _unowned(session_factory, _candidate(client, people["member"], "Waise"))
    listing = client.get("/api/v1/submissions/without-owner", headers=people["admin"].headers)
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == submission_id
    assert body["items"][0]["candidate_name"] == "Erika Waise"
    for role in ("member", "lead"):
        denied = client.get("/api/v1/submissions/without-owner", headers=people[role].headers)
        assert denied.status_code == 403, role


def test_assigning_an_owner_makes_the_process_visible_and_is_audited(
    client: TestClient, session_factory: sessionmaker[Session], people: dict[str, Person]
) -> None:
    submission_id = _unowned(session_factory, _candidate(client, people["member"]))
    assert submission_id not in _ids(client, people["member"])
    response = client.post(
        f"/api/v1/submissions/{submission_id}/assign-owner",
        json={"owner_user_id": people["member"].id},
        headers=people["admin"].headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["owner_user_id"] == people["member"].id
    assert submission_id in _ids(client, people["member"])
    empty = client.get("/api/v1/submissions/without-owner", headers=people["admin"].headers)
    assert empty.json()["total"] == 0
    with session_factory() as session:
        entry = session.scalars(
            select(AuditLog).where(
                AuditLog.entity_id == uuid.UUID(submission_id), AuditLog.action == "updated"
            )
        ).one()
    assert entry.changed_by == "chef@own.example"
    assert entry.old_values == {"owner_user_id": None}
    assert entry.new_values == {"owner_user_id": people["member"].id}


def test_assign_owner_is_admin_only_and_validates_the_target(
    client: TestClient, session_factory: sessionmaker[Session], people: dict[str, Person]
) -> None:
    submission_id = _unowned(session_factory, _candidate(client, people["member"]))
    path = f"/api/v1/submissions/{submission_id}/assign-owner"
    body = {"owner_user_id": people["member"].id}
    # Nicht-Admin: der Prozess ist fuer ihn nicht einmal sichtbar (404), nie zugewiesen.
    assert client.post(path, json=body, headers=people["member"].headers).status_code in (403, 404)
    assert client.post(path, json=body, headers=people["lead"].headers).status_code in (403, 404)
    # Unbekannter und deaktivierter Nutzer.
    unknown = client.post(
        path, json={"owner_user_id": str(uuid.uuid4())}, headers=people["admin"].headers
    )
    assert unknown.status_code == 404
    with session_factory() as session:
        member = session.get(User, uuid.UUID(people["member"].id))
        assert member is not None
        member.is_active = False
        session.commit()
    inactive = client.post(path, json=body, headers=people["admin"].headers)
    assert inactive.status_code == 404
    with session_factory() as session:
        submission = session.get(CandidateSubmission, uuid.UUID(submission_id))
        assert submission is not None and submission.owner_user_id is None  # nie zugewiesen
