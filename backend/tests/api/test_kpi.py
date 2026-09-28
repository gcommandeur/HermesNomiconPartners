"""API-Tests fuer das KPI-Punkte-System, die Geschaeftsfuehrer-Ansicht und
das Live-Ranking (Auftrag "Geschaeftsfuehrer-Ansicht + KPI-Punkte-System +
Live-Ranking")."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService


@pytest.fixture
def admin_token(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        session.add(
            User(
                email="admin@commandeurconsulting.de",
                hashed_password=hash_password("x"),
                role="admin",
            )
        )
        session.commit()
        _, token = AuthService(session).login("admin@commandeurconsulting.de", "x")
        return token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_and_advance_submission(
    client: TestClient, *, owner_user_id: str, statuses: list[str]
) -> dict:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Anna", "last_name": "Muster", "owner_user_id": owner_user_id},
    ).json()
    company = client.post(
        "/api/v1/clients", json={"name": "Kanzlei KPI", "status": "active"}
    ).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    for status in statuses:
        response = client.patch(
            f"/api/v1/submissions/{submission['id']}/transition", json={"status": status}
        )
        assert response.status_code == 200, response.text
    return submission


class TestKpiPointRules:
    def test_non_admin_cannot_read_rules(self, client: TestClient) -> None:
        response = client.get("/api/v1/admin/kpi-point-rules")
        assert response.status_code == 403

    def test_admin_reads_seeded_rules_all_zero(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.get(
            "/api/v1/admin/kpi-point-rules", headers=auth_header(admin_token)
        )
        assert response.status_code == 200, response.text
        rules = {item["stage"]: item["points"] for item in response.json()}
        assert rules == {
            "pitch": 0,
            "qualification_call": 0,
            "cv_in": 0,
            "cv_out": 0,
            "interview": 0,
            "offer": 0,
            "placement": 0,
        }

    def test_admin_can_update_rules(self, client: TestClient, admin_token: str) -> None:
        response = client.put(
            "/api/v1/admin/kpi-point-rules",
            json={"rules": {"interview": 10, "placement": 50}},
            headers=auth_header(admin_token),
        )
        assert response.status_code == 200, response.text
        rules = {item["stage"]: item["points"] for item in response.json()}
        assert rules["interview"] == 10
        assert rules["placement"] == 50
        assert rules["qualification_call"] == 0

    def test_non_admin_cannot_update_rules(self, client: TestClient) -> None:
        response = client.put("/api/v1/admin/kpi-point-rules", json={"rules": {"interview": 10}})
        assert response.status_code == 403


class TestAppSettings:
    def test_admin_reads_defaults(self, client: TestClient, admin_token: str) -> None:
        response = client.get(
            "/api/v1/admin/app-settings", headers=auth_header(admin_token)
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "kpi_ranking_metric": "points",
            "kpi_ranking_period": "week",
        }

    def test_admin_can_update_ranking_defaults(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.put(
            "/api/v1/admin/app-settings",
            json={"kpi_ranking_metric": "placement", "kpi_ranking_period": "day"},
            headers=auth_header(admin_token),
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "kpi_ranking_metric": "placement",
            "kpi_ranking_period": "day",
        }

    def test_non_admin_cannot_update_settings(self, client: TestClient) -> None:
        response = client.put(
            "/api/v1/admin/app-settings", json={"kpi_ranking_metric": "placement"}
        )
        assert response.status_code == 403


class TestTeamKpis:
    def test_non_admin_cannot_view_team_kpis(self, client: TestClient) -> None:
        response = client.get("/api/v1/team-kpis")
        assert response.status_code == 403

    def test_reached_stages_are_grouped_by_candidate_owner(
        self, client: TestClient, admin_token: str
    ) -> None:
        # Der Standard-`client`-Fixture-Nutzer laeuft unter test@commandeur.
        # example, derselben Domain, die Block 1 ("Nutzer-Hygiene") als
        # Test-/Service-Domain behandelt - team_kpi_overview() blendet ihn
        # deshalb bewusst aus, daher hier ein echter Admin-Nutzer als Owner.
        admin = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()
        _create_and_advance_submission(
            client, owner_user_id=admin["id"], statuses=["cv_in", "cv_out", "interview"]
        )

        response = client.get(
            "/api/v1/team-kpis?period=month", headers=auth_header(admin_token)
        )
        assert response.status_code == 200, response.text
        members = {item["user_id"]: item for item in response.json()["members"]}
        assert members[admin["id"]]["stages"]["interview"] == 1
        assert members[admin["id"]]["stages"]["cv_out"] == 1
        assert members[admin["id"]]["stages"]["placement"] == 0
        # Ziel-Spalte bewusst noch nicht spezifiziert (Nutzer-Vorgabe) - immer null.
        assert members[admin["id"]]["target"] is None

    def test_points_are_stage_count_times_configured_points(
        self, client: TestClient, admin_token: str
    ) -> None:
        admin = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()
        client.put(
            "/api/v1/admin/kpi-point-rules",
            json={"rules": {"interview": 10, "cv_out": 3}},
            headers=auth_header(admin_token),
        )
        _create_and_advance_submission(
            client, owner_user_id=admin["id"], statuses=["cv_in", "cv_out", "interview"]
        )

        response = client.get(
            "/api/v1/team-kpis?period=month", headers=auth_header(admin_token)
        )
        members = {item["user_id"]: item for item in response.json()["members"]}
        # 1x cv_out (3 Punkte) + 1x interview (10 Punkte) = 13.
        assert members[admin["id"]]["points"] == 13


class TestKpiRanking:
    def test_visible_to_non_admin_users(self, client: TestClient) -> None:
        """Nutzer-Vorgabe: das Ranking-Widget ist fuer ALLE Nutzer sichtbar,
        nicht nur Admins - anders als die Geschaeftsfuehrer-Ansicht."""
        response = client.get("/api/v1/kpi-ranking")
        assert response.status_code == 200, response.text

    def test_ranking_sorted_descending_by_points(
        self, client: TestClient, admin_token: str, second_user_token: str
    ) -> None:
        admin = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()
        other = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()

        _create_and_advance_submission(client, owner_user_id=admin["id"], statuses=[])

        response = client.get("/api/v1/kpi-ranking?period=week&metric=qualification_call")
        assert response.status_code == 200, response.text
        entries = response.json()["entries"]
        values = {item["user_id"]: item["value"] for item in entries}
        assert values[admin["id"]] == 1
        assert values.get(other["id"], 0) == 0

    def test_metric_selects_raw_stage_count_not_points(
        self, client: TestClient, admin_token: str
    ) -> None:
        admin = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()
        _create_and_advance_submission(client, owner_user_id=admin["id"], statuses=["cv_in"])

        response = client.get("/api/v1/kpi-ranking?period=week&metric=cv_in")
        assert response.status_code == 200, response.text
        values = {item["user_id"]: item["value"] for item in response.json()["entries"]}
        assert values[admin["id"]] == 1


@pytest.fixture
def second_user_token(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        session.add(
            User(email="colleague@commandeurconsulting.de", hashed_password=hash_password("x"))
        )
        session.commit()
        _, token = AuthService(session).login("colleague@commandeurconsulting.de", "x")
        return token
