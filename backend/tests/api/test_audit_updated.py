"""AuditLog "updated": normale Feld-Edits an Kandidat, Kanzlei und Prozess
werden mit alt/neu NUR der tatsaechlich geaenderten Felder protokolliert;
Speichern ohne echte Aenderung erzeugt keinen Eintrag."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.recruiting import AuditLog


def _updated_logs(
    session_factory: sessionmaker[Session], entity_id: str
) -> list[AuditLog]:
    with session_factory() as session:
        return list(
            session.scalars(
                select(AuditLog).where(
                    AuditLog.entity_id == uuid.UUID(entity_id), AuditLog.action == "updated"
                )
            ).all()
        )


def test_candidate_edit_logs_only_changed_fields(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Erika", "last_name": "Beispiel", "phone": "0711 1"},
    ).json()

    response = client.patch(
        f"/api/v1/candidates/{candidate['id']}",
        json={"phone": "0711 2", "first_name": "Erika"},
    )
    assert response.status_code == 200

    logs = _updated_logs(session_factory, candidate["id"])
    assert len(logs) == 1
    assert logs[0].entity_type == "candidate"
    assert logs[0].old_values == {"phone": "0711 1"}
    assert logs[0].new_values == {"phone": "0711 2"}
    assert logs[0].changed_by is not None


def test_candidate_save_without_change_logs_nothing(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Erika", "last_name": "Beispiel", "phone": "0711 1"},
    ).json()

    client.patch(
        f"/api/v1/candidates/{candidate['id']}",
        json={"phone": "0711 1", "first_name": "Erika", "last_name": "Beispiel"},
    )

    assert _updated_logs(session_factory, candidate["id"]) == []


def test_client_company_edit_logs_changed_fields_decimal_equal_is_no_change(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    company = client.post(
        "/api/v1/clients", json={"name": "Muster StBG", "city": "Stuttgart"}
    ).json()

    client.patch(
        f"/api/v1/clients/{company['id']}",
        # 27 == 27.00 (Default) -> keine Aenderung; nur city aendert sich.
        json={"city": "Esslingen", "fee_percentage": "27"},
    )

    logs = _updated_logs(session_factory, company["id"])
    assert len(logs) == 1
    assert logs[0].entity_type == "client_company"
    assert logs[0].old_values == {"city": "Stuttgart"}
    assert logs[0].new_values == {"city": "Esslingen"}


def test_submission_edit_logs_changed_fields(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Erika", "last_name": "Beispiel"}
    ).json()
    submission = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    ).json()

    client.patch(f"/api/v1/submissions/{submission['id']}", json={"next_step": "Anrufen"})
    client.patch(f"/api/v1/submissions/{submission['id']}", json={"next_step": "Anrufen"})

    logs = _updated_logs(session_factory, submission["id"])
    assert len(logs) == 1
    assert logs[0].entity_type == "candidate_submission"
    assert logs[0].new_values == {"next_step": "Anrufen"}
