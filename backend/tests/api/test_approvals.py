"""Freigabe-Inbox (Task #200 Teil 2): neue Kanzlei, Honorar-Aenderung und
"Rechnung stellen" durch Nicht-Admins warten auf Freigabe; Admins wirken
sofort. Der Standard-`client` im Test ist ein Nicht-Admin."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.recruiting import AuditLog
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService


@pytest.fixture
def admin_headers(session_factory: sessionmaker[Session]) -> dict[str, str]:
    with session_factory() as session:
        session.add(
            User(email="gf@commandeur.example", hashed_password=hash_password("x"), role="admin")
        )
        session.commit()
        _, token = AuthService(session).login("gf@commandeur.example", "x")
    return {"Authorization": f"Bearer {token}"}


def _pending(client: TestClient, admin_headers: dict[str, str]) -> list[dict]:
    response = client.get("/api/v1/approval-requests", headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()


def _audit_actions(session_factory: sessionmaker[Session], entity_id: str) -> list[str]:
    with session_factory() as session:
        return [
            log.action
            for log in session.scalars(
                select(AuditLog).where(AuditLog.entity_id == uuid.UUID(entity_id))
            ).all()
        ]


class TestNewClient:
    def test_non_admin_new_client_waits_and_approve_clears_flag(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        session_factory: sessionmaker[Session],
    ) -> None:
        company = client.post("/api/v1/clients", json={"name": "Neu StBG"}).json()
        assert company["approval_pending"] is True

        [request] = _pending(client, admin_headers)
        assert request["kind"] == "new_client"
        assert request["entity_label"] == "Neu StBG"

        response = client.post(
            f"/api/v1/approval-requests/{request['id']}/approve", headers=admin_headers
        )
        assert response.status_code == 200, response.text
        assert client.get(f"/api/v1/clients/{company['id']}").json()["approval_pending"] is False
        assert _pending(client, admin_headers) == []
        assert "approved" in _audit_actions(session_factory, company["id"])

    def test_reject_new_client_blocks_it(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        company = client.post("/api/v1/clients", json={"name": "Neu StBG"}).json()
        [request] = _pending(client, admin_headers)

        client.post(
            f"/api/v1/approval-requests/{request['id']}/reject",
            json={"decision_note": "Dublette"},
            headers=admin_headers,
        )

        after = client.get(f"/api/v1/clients/{company['id']}").json()
        assert after["approval_pending"] is False
        assert after["status"] == "blocked"

    def test_admin_new_client_needs_no_approval(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        company = client.post(
            "/api/v1/clients", json={"name": "Admin StBG"}, headers=admin_headers
        ).json()
        assert company["approval_pending"] is False
        assert _pending(client, admin_headers) == []


class TestHonorarChange:
    def _approved_client(self, client: TestClient, admin_headers: dict[str, str]) -> dict:
        return client.post(
            "/api/v1/clients", json={"name": "Bestand StBG"}, headers=admin_headers
        ).json()

    def test_non_admin_honorar_change_waits_other_fields_apply(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        session_factory: sessionmaker[Session],
    ) -> None:
        company = self._approved_client(client, admin_headers)

        updated = client.patch(
            f"/api/v1/clients/{company['id']}",
            json={"fee_percentage": "25.00", "city": "Esslingen"},
        ).json()
        assert updated["fee_percentage"] == "27.00"
        assert updated["city"] == "Esslingen"

        pending_for = client.get(
            f"/api/v1/approval-requests/for/client_company/{company['id']}"
        ).json()
        assert [item["kind"] for item in pending_for] == ["honorar_change"]
        assert pending_for[0]["old_values"] == {"fee_percentage": "27.00"}
        assert pending_for[0]["proposed_values"] == {"fee_percentage": "25.00"}

        client.post(
            f"/api/v1/approval-requests/{pending_for[0]['id']}/approve", headers=admin_headers
        )
        assert client.get(f"/api/v1/clients/{company['id']}").json()["fee_percentage"] == "25.00"
        assert "approved" in _audit_actions(session_factory, company["id"])

    def test_second_change_before_approval_updates_same_request(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        company = self._approved_client(client, admin_headers)
        client.patch(f"/api/v1/clients/{company['id']}", json={"fee_percentage": "25.00"})
        client.patch(
            f"/api/v1/clients/{company['id']}",
            json={"fee_percentage": "24.00", "payment_terms_days": 30},
        )

        [request] = _pending(client, admin_headers)
        assert request["old_values"] == {"fee_percentage": "27.00", "payment_terms_days": 14}
        assert request["proposed_values"] == {"fee_percentage": "24.00", "payment_terms_days": 30}

    def test_reject_keeps_old_honorar(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        company = self._approved_client(client, admin_headers)
        client.patch(f"/api/v1/clients/{company['id']}", json={"fee_percentage": "20.00"})
        [request] = _pending(client, admin_headers)

        client.post(
            f"/api/v1/approval-requests/{request['id']}/reject", json={}, headers=admin_headers
        )

        assert client.get(f"/api/v1/clients/{company['id']}").json()["fee_percentage"] == "27.00"

    def test_admin_honorar_change_applies_immediately(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        company = self._approved_client(client, admin_headers)
        updated = client.patch(
            f"/api/v1/clients/{company['id']}",
            json={"fee_percentage": "25.00"},
            headers=admin_headers,
        ).json()
        assert updated["fee_percentage"] == "25.00"
        assert _pending(client, admin_headers) == []


def _placement_fee(client: TestClient, admin_headers: dict[str, str]) -> dict:
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Max", "last_name": "Muster"}
    ).json()
    company = client.post(
        "/api/v1/clients", json={"name": "Kanzlei Alpha"}, headers=admin_headers
    ).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for status in ("cv_in", "cv_out", "interview", "offer", "placement"):
        client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": status}
        )
    placement = client.post(
        f"/api/v1/submissions/{submission['id']}/placement",
        json={"start_date": "2026-10-01", "final_salary": "70000.00", "fee_percentage": "27.00"},
    ).json()
    response = client.post(
        f"/api/v1/placements/{placement['id']}/fees", json={"amount_net": "18900.00"}
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestInvoiceIssue:
    def test_non_admin_issue_waits_then_approve_issues(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        session_factory: sessionmaker[Session],
    ) -> None:
        fee = _placement_fee(client, admin_headers)
        assert fee["invoice_status"] == "draft"

        result = client.post(
            f"/api/v1/fees/{fee['id']}/invoice-status", json={"invoice_status": "issued"}
        ).json()
        assert result["fee"]["invoice_status"] == "draft"
        assert result["approval_request"]["kind"] == "invoice_issue"
        assert "Max Muster" in result["approval_request"]["entity_label"]

        client.post(
            f"/api/v1/approval-requests/{result['approval_request']['id']}/approve",
            headers=admin_headers,
        )
        [issued] = client.get(f"/api/v1/placements/{fee['placement_id']}/fees").json()
        assert issued["invoice_status"] == "issued"
        assert issued["invoice_date"] is not None
        assert "approved" in _audit_actions(session_factory, fee["id"])

    def test_later_steps_apply_immediately_for_non_admin(
        self,
        client: TestClient,
        admin_headers: dict[str, str],
        session_factory: sessionmaker[Session],
    ) -> None:
        fee = _placement_fee(client, admin_headers)
        client.post(
            f"/api/v1/fees/{fee['id']}/invoice-status",
            json={"invoice_status": "issued"},
            headers=admin_headers,
        )

        paid = client.post(
            f"/api/v1/fees/{fee['id']}/invoice-status", json={"invoice_status": "paid"}
        ).json()
        assert paid["approval_request"] is None
        assert paid["fee"]["invoice_status"] == "paid"
        assert paid["fee"]["paid_at"] is not None
        assert "invoice_status_changed" in _audit_actions(session_factory, fee["id"])

    def test_invalid_transition_is_rejected(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        fee = _placement_fee(client, admin_headers)
        response = client.post(
            f"/api/v1/fees/{fee['id']}/invoice-status",
            json={"invoice_status": "paid"},
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_non_admin_cannot_create_fee_already_issued(
        self, client: TestClient, admin_headers: dict[str, str]
    ) -> None:
        fee = _placement_fee(client, admin_headers)
        response = client.post(
            f"/api/v1/placements/{fee['placement_id']}/fees",
            json={"amount_net": "100.00", "invoice_status": "issued"},
        )
        assert response.status_code == 422


def test_inbox_and_decisions_are_admin_only(client: TestClient) -> None:
    assert client.get("/api/v1/approval-requests").status_code == 403
    random_id = uuid.uuid4()
    assert client.post(f"/api/v1/approval-requests/{random_id}/approve").status_code == 403
    assert (
        client.post(f"/api/v1/approval-requests/{random_id}/reject", json={}).status_code == 403
    )
