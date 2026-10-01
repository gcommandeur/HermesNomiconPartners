import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.user import User
from cc_crm.services.auth import AuthService


@pytest.fixture
def second_user_token(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        session.add(User(email="colleague@commandeur.example", hashed_password=hash_password("x")))
        session.commit()
        _, token = AuthService(session).login("colleague@commandeur.example", "x")
        return token


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_candidate_owner_defaults_to_current_user(client: TestClient) -> None:
    me = client.get("/api/v1/auth/me").json()
    created = client.post(
        "/api/v1/candidates", json={"first_name": "Owner", "last_name": "Default"}
    )
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == me["id"]


def test_candidate_owner_explicitly_settable_and_changeable(
    client: TestClient, second_user_token: str
) -> None:
    """Default ist der eingeloggte Nutzer, aber im Formular aenderbar - ein
    explizit gesetzter owner_user_id (z.B. ein Kollege) darf NICHT vom
    Default-Mechanismus ueberschrieben werden."""
    colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()

    created = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Explicit",
            "last_name": "Owner",
            "owner_user_id": colleague["id"],
        },
    )
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == colleague["id"]


def test_candidate_owner_filter_is_convenience_not_visibility(
    client: TestClient, second_user_token: str
) -> None:
    """owner_user_id-Filter darf NUR die Trefferliste einschraenken, wenn
    explizit gesetzt - ohne ihn muss jeder Nutzer weiterhin ALLE Kandidaten
    sehen (kein Kalender-artiges Sichtbarkeits-Verhalten)."""
    me = client.get("/api/v1/auth/me").json()
    colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()

    client.post("/api/v1/candidates", json={"first_name": "Mine", "last_name": "A"})
    client.post(
        "/api/v1/candidates",
        json={"first_name": "Colleague", "last_name": "B"},
        headers=auth_header(second_user_token),
    )

    # Ohne Filter: beide Nutzer sehen BEIDE Kandidaten.
    all_as_me = client.get("/api/v1/candidates").json()
    assert all_as_me["total_count"] == 2
    all_as_colleague = client.get(
        "/api/v1/candidates", headers=auth_header(second_user_token)
    ).json()
    assert all_as_colleague["total_count"] == 2

    # Mit Filter: nur der jeweils eigene Kandidat.
    mine_only = client.get(f"/api/v1/candidates?owner_user_id={me['id']}").json()
    assert mine_only["total_count"] == 1
    assert mine_only["items"][0]["first_name"] == "Mine"

    colleagues_only = client.get(f"/api/v1/candidates?owner_user_id={colleague['id']}").json()
    assert colleagues_only["total_count"] == 1
    assert colleagues_only["items"][0]["first_name"] == "Colleague"


def test_client_owner_filter(client: TestClient, second_user_token: str) -> None:
    me = client.get("/api/v1/auth/me").json()
    client.post("/api/v1/clients", json={"name": "Kanzlei A"})
    client.post(
        "/api/v1/clients", json={"name": "Kanzlei B"}, headers=auth_header(second_user_token)
    )

    all_clients = client.get("/api/v1/clients").json()
    assert all_clients["total_count"] == 2

    mine_only = client.get(f"/api/v1/clients?owner_user_id={me['id']}").json()
    assert mine_only["total_count"] == 1
    assert mine_only["items"][0]["name"] == "Kanzlei A"


def test_submission_owner_filter(client: TestClient, second_user_token: str) -> None:
    me = client.get("/api/v1/auth/me").json()
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "Sub", "last_name": "Owner"}
    ).json()

    created = client.post(
        "/api/v1/submissions", json={"candidate_id": candidate["id"]}
    )
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == me["id"]

    submissions = client.get("/api/v1/submissions").json()
    assert submissions["total_count"] == 1

    mine_only = client.get(f"/api/v1/submissions?owner_user_id={me['id']}").json()
    assert mine_only["total_count"] == 1

    # Sichtbarkeitsgrenze: ein Nicht-Admin kann per fremdem owner_user_id NICHT
    # in Kollegen-Prozesse schauen - der Parameter wird auf ihn selbst gesetzt.
    colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()
    others_only = client.get(f"/api/v1/submissions?owner_user_id={colleague['id']}").json()
    assert [item["owner_user_id"] for item in others_only["items"]] == [me["id"]]


@pytest.fixture
def admin_token(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        session.add(
            User(email="gf@commandeur.example", hashed_password=hash_password("x"), role="admin")
        )
        session.commit()
        _, token = AuthService(session).login("gf@commandeur.example", "x")
        return token


def _full_process(client: TestClient, headers: dict[str, str], last_name: str) -> dict:
    """Prozess bis Placement samt Interview, Offer, Feedback und Fee - alles
    im Namen des Nutzers aus `headers`."""
    candidate = client.post(
        "/api/v1/candidates", json={"first_name": "P", "last_name": last_name}, headers=headers
    ).json()
    company = client.post(
        "/api/v1/clients", json={"name": f"Kanzlei {last_name}"}, headers=headers
    ).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
        headers=headers,
    ).json()
    sid = submission["id"]

    def move(status: str) -> None:
        response = client.patch(
            f"/api/v1/submissions/{sid}/transition", json={"status": status}, headers=headers
        )
        assert response.status_code == 200, response.text

    for status in ("cv_in", "cv_out", "interview"):
        move(status)
    client.post(
        f"/api/v1/submissions/{sid}/interviews",
        json={"scheduled_at": "2026-10-10T10:00:00", "interview_type": "Erstgespraech"},
        headers=headers,
    )
    client.post(
        f"/api/v1/submissions/{sid}/feedback",
        json={
            "feedback_type": "internal",
            "feedback_text": "ok",
            "received_at": "2026-10-01T09:00:00",
        },
        headers=headers,
    )
    move("offer")
    offer = client.post(
        f"/api/v1/submissions/{sid}/offers", json={"offered_salary": "70000"}, headers=headers
    )
    assert offer.status_code == 201, offer.text
    move("placement")
    placement = client.post(
        f"/api/v1/submissions/{sid}/placement",
        json={"start_date": "2026-10-01", "final_salary": "70000", "fee_percentage": "27"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/placements/{placement['id']}/fees", json={"amount_net": "18900"}, headers=headers
    )
    return submission


class TestProcessVisibility:
    """Laufende Prozesse und alles daran Haengende sind fuer Nicht-Admins auf
    die eigenen beschraenkt (serverseitig, nicht nur im Browser gefiltert);
    Admins sehen alles."""

    ENDPOINTS = (
        "/api/v1/interviews",
        "/api/v1/offers",
        "/api/v1/placements",
        "/api/v1/placements/active-warranties",
        "/api/v1/feedback",
        "/api/v1/fees",
        "/api/v1/submissions/priority-view",
    )

    def test_non_admin_sees_only_own_processes_and_children(
        self, client: TestClient, second_user_token: str, admin_token: str
    ) -> None:
        mine = _full_process(client, {}, "Mein")
        _full_process(client, auth_header(second_user_token), "Fremd")

        submissions = client.get("/api/v1/submissions").json()
        assert [item["id"] for item in submissions["items"]] == [mine["id"]]

        for endpoint in self.ENDPOINTS:
            if endpoint.endswith("priority-view"):
                continue  # braucht einen Closing-Score, siehe eigener Test
            mine_rows = client.get(endpoint).json()
            all_rows = client.get(endpoint, headers=auth_header(admin_token)).json()
            assert len(mine_rows) == 1, endpoint
            assert len(all_rows) == 2, endpoint

    def test_admin_sees_all_submissions_and_filter_still_works(
        self, client: TestClient, second_user_token: str, admin_token: str
    ) -> None:
        me = client.get("/api/v1/auth/me").json()
        _full_process(client, {}, "Mein")
        _full_process(client, auth_header(second_user_token), "Fremd")

        admin = auth_header(admin_token)
        assert client.get("/api/v1/submissions", headers=admin).json()["total_count"] == 2
        filtered = client.get(f"/api/v1/submissions?owner_user_id={me['id']}", headers=admin)
        assert filtered.json()["total_count"] == 1

    def test_priority_view_is_scoped(
        self, client: TestClient, second_user_token: str, admin_token: str
    ) -> None:
        for headers, name in (({}, "Mein"), (auth_header(second_user_token), "Fremd")):
            submission = _full_process(client, headers, name)
            client.patch(
                f"/api/v1/submissions/{submission['id']}/closing-score",
                json={"closing_status": "hot"},
                headers=headers,
            )
        mine = client.get("/api/v1/submissions/priority-view").json()
        everyone = client.get(
            "/api/v1/submissions/priority-view", headers=auth_header(admin_token)
        ).json()
        assert len(mine) <= 1
        assert len(everyone) >= len(mine)
        me = client.get("/api/v1/auth/me").json()
        assert all(item["owner_user_id"] == me["id"] for item in mine)

    def test_bulk_submit_and_quick_log_processes_belong_to_creator(
        self, client: TestClient, admin_token: str
    ) -> None:
        me = client.get("/api/v1/auth/me").json()
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Q", "last_name": "Log"}
        ).json()
        company = client.post(
            "/api/v1/clients", json={"name": "Bulk StBG"}, headers=auth_header(admin_token)
        ).json()

        client.post(
            f"/api/v1/candidates/{candidate['id']}/bulk-submit",
            json={"client_company_ids": [company["id"]], "target_status": "cv_in"},
        )
        client.post(
            f"/api/v1/candidates/{candidate['id']}/quick-log",
            json={
                "stage": "qualification_call",
                "feedback_type": "internal",
                "feedback_text": "Quali-Call",
                "received_at": "2026-10-01T09:00:00",
            },
        )

        own = client.get("/api/v1/submissions").json()["items"]
        assert len(own) == 2
        assert all(item["owner_user_id"] == me["id"] for item in own)

    def test_quick_log_on_colleague_open_process_still_succeeds(
        self, client: TestClient, second_user_token: str
    ) -> None:
        """Pro Kandidat ist nur ein offener Prozess ohne Kanzlei erlaubt -
        ein Quick-Log auf einen Kandidaten mit offenem Kollegen-Prozess fuehrt
        diesen weiter statt mit 409 zu scheitern (bekannter Grenzfall: der
        Prozess bleibt beim Kollegen)."""
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Geteilter", "last_name": "Kandidat"}
        ).json()
        quick_log = {
            "stage": "qualification_call",
            "feedback_type": "internal",
            "feedback_text": "Quali-Call",
            "received_at": "2026-10-01T09:00:00",
        }
        client.post(
            f"/api/v1/candidates/{candidate['id']}/quick-log",
            json=quick_log,
            headers=auth_header(second_user_token),
        )

        response = client.post(f"/api/v1/candidates/{candidate['id']}/quick-log", json=quick_log)

        assert response.status_code == 200, response.text
        colleague_view = client.get(
            "/api/v1/submissions", headers=auth_header(second_user_token)
        ).json()
        assert colleague_view["total_count"] == 1


def test_task_owner_filter(client: TestClient, second_user_token: str) -> None:
    me = client.get("/api/v1/auth/me").json()
    created = client.post("/api/v1/tasks", json={"title": "Nachfassen"})
    assert created.status_code == 201
    assert created.json()["owner_user_id"] == me["id"]

    colleague = client.get("/api/v1/auth/me", headers=auth_header(second_user_token)).json()
    client.post(
        "/api/v1/tasks", json={"title": "Andere Aufgabe"}, headers=auth_header(second_user_token)
    )

    all_tasks = client.get("/api/v1/tasks").json()
    assert len(all_tasks) == 2

    mine_only = client.get(f"/api/v1/tasks?owner_user_id={me['id']}").json()
    assert len(mine_only) == 1
    assert mine_only[0]["title"] == "Nachfassen"

    colleagues_only = client.get(f"/api/v1/tasks?owner_user_id={colleague['id']}").json()
    assert len(colleagues_only) == 1
    assert colleagues_only[0]["title"] == "Andere Aufgabe"
