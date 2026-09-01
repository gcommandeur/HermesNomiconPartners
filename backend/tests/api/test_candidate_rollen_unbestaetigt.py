"""Tests fuer Candidate.rollen_unbestaetigt (Konsolidierter Auftrag
"Titelschutz-Korrektur ohne Datenverlust + Rollen-Herkunft + Rechtsgebiete",
Schritt 2: Markieren statt Aendern) - POST /confirm-rollen, automatisches
Loeschen bei tatsaechlicher Rollen-Korrektur ueber PATCH, der eigene Filter,
und dass beides einen AuditLog-Eintrag hinterlaesst."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from tests.conftest import TEST_USER_EMAIL


def _create_candidate(client: TestClient, **overrides: object) -> dict:
    payload = {"first_name": "Anna", "last_name": "Muster", "rollen": ["steuerberater"]}
    payload.update(overrides)
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _flag_unbestaetigt(session_factory: sessionmaker[Session], candidate_id: str) -> None:
    """Setzt rollen_unbestaetigt direkt in der DB - dieses Feld ist bewusst
    NICHT ueber CandidateCreate/CandidateUpdate steuerbar (system-gesetzt,
    siehe models/candidate.py), der Testaufbau muss es deshalb direkt
    setzen, genau wie es scripts/audit_titelschutz_unverified_roles.py in
    Produktion taete."""
    with session_factory() as session:
        candidate = session.get(Candidate, uuid.UUID(candidate_id))
        assert candidate is not None
        candidate.rollen_unbestaetigt = True
        session.commit()


class TestRollenUnbestaetigtDefaultsAndSchema:
    def test_new_candidate_defaults_to_false(self, client: TestClient) -> None:
        candidate = _create_candidate(client)
        assert candidate["rollen_unbestaetigt"] is False

    def test_cannot_be_set_via_create_payload(self, client: TestClient) -> None:
        """rollen_unbestaetigt ist system-gesetzt - selbst wenn ein Client es
        im Payload mitschickt, hat CandidateCreate dieses Feld gar nicht,
        Pydantic ignoriert unbekannte Felder also einfach."""
        candidate = _create_candidate(client, rollen_unbestaetigt=True)
        assert candidate["rollen_unbestaetigt"] is False

    def test_cannot_be_set_via_update_payload(self, client: TestClient) -> None:
        candidate = _create_candidate(client)
        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}", json={"rollen_unbestaetigt": True}
        )
        assert response.status_code == 200, response.text
        assert response.json()["rollen_unbestaetigt"] is False


class TestConfirmRollen:
    def test_confirm_clears_flag_and_keeps_rollen_unchanged(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        candidate = _create_candidate(client, rollen=["steuerberater"])
        _flag_unbestaetigt(session_factory, candidate["id"])

        response = client.post(f"/api/v1/candidates/{candidate['id']}/confirm-rollen")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rollen_unbestaetigt"] is False
        assert body["rollen"] == ["steuerberater"]

    def test_confirm_writes_audit_log_entry(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        candidate = _create_candidate(client)
        _flag_unbestaetigt(session_factory, candidate["id"])

        client.post(f"/api/v1/candidates/{candidate['id']}/confirm-rollen")

        history = client.get(f"/api/v1/candidates/{candidate['id']}/history").json()
        entry = next(e for e in history if e["action"] == "rollen_bestaetigt")
        assert entry["entity_type"] == "candidate"
        assert entry["changed_by"] == TEST_USER_EMAIL
        assert entry["old_values"]["rollen_unbestaetigt"] is True
        assert entry["new_values"]["rollen_unbestaetigt"] is False

    def test_confirm_is_a_noop_when_flag_already_unset(self, client: TestClient) -> None:
        candidate = _create_candidate(client)

        response = client.post(f"/api/v1/candidates/{candidate['id']}/confirm-rollen")

        assert response.status_code == 200, response.text
        assert response.json()["rollen_unbestaetigt"] is False
        history = client.get(f"/api/v1/candidates/{candidate['id']}/history").json()
        assert not any(e["action"] == "rollen_bestaetigt" for e in history)

    def test_confirm_returns_404_for_unknown_candidate(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/candidates/00000000-0000-0000-0000-000000000000/confirm-rollen"
        )
        assert response.status_code == 404


class TestAutomaticFlagClearOnCorrection:
    def test_changing_rollen_clears_the_flag(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        candidate = _create_candidate(client, rollen=["steuerberater"])
        _flag_unbestaetigt(session_factory, candidate["id"])

        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}", json={"rollen": ["bilanzbuchhalter"]}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rollen"] == ["bilanzbuchhalter"]
        assert body["rollen_unbestaetigt"] is False

    def test_changing_rollen_writes_audit_log_entry(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        candidate = _create_candidate(client, rollen=["steuerberater"])
        _flag_unbestaetigt(session_factory, candidate["id"])

        client.patch(
            f"/api/v1/candidates/{candidate['id']}", json={"rollen": ["bilanzbuchhalter"]}
        )

        history = client.get(f"/api/v1/candidates/{candidate['id']}/history").json()
        entry = next(e for e in history if e["action"] == "rollen_korrigiert")
        assert entry["changed_by"] == TEST_USER_EMAIL
        assert entry["old_values"]["rollen"] == ["steuerberater"]
        assert entry["new_values"]["rollen"] == ["bilanzbuchhalter"]

    def test_resubmitting_the_same_rollen_value_does_not_clear_the_flag(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        """Das Bearbeiten-Formular schickt rollen bei JEDER Aenderung mit
        (auch bei einer voellig unrelated Aenderung) - nur ein echter
        Wertewechsel darf das Flag loeschen, sonst wuerde z.B. das Aendern
        des Gehalts das Flag unbemerkt entfernen."""
        candidate = _create_candidate(client, rollen=["steuerberater"])
        _flag_unbestaetigt(session_factory, candidate["id"])

        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}",
            json={"rollen": ["steuerberater"], "salary_expectation": "80.000 €"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["rollen_unbestaetigt"] is True

    def test_changing_an_unrelated_field_without_rollen_in_payload_does_not_clear_the_flag(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        candidate = _create_candidate(client, rollen=["steuerberater"])
        _flag_unbestaetigt(session_factory, candidate["id"])

        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}", json={"salary_expectation": "90.000 €"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["rollen_unbestaetigt"] is True

    def test_flag_stays_unset_when_correcting_rollen_on_an_unflagged_candidate(
        self, client: TestClient
    ) -> None:
        """Kein Flag gesetzt -> keine automatische Bearbeitung/kein
        Audit-Log-Rauschen fuer die normale, alltaegliche Rollen-Pflege."""
        candidate = _create_candidate(client, rollen=["steuerberater"])

        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}", json={"rollen": ["partner"]}
        )

        assert response.status_code == 200, response.text
        assert response.json()["rollen_unbestaetigt"] is False
        history = client.get(f"/api/v1/candidates/{candidate['id']}/history").json()
        assert not any(e["action"] == "rollen_korrigiert" for e in history)


class TestRollenUnbestaetigtFilter:
    def test_filters_to_only_flagged_candidates(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        flagged = _create_candidate(client, first_name="Flagged")
        _create_candidate(client, first_name="Normal")
        _flag_unbestaetigt(session_factory, flagged["id"])

        response = client.get("/api/v1/candidates?rollen_unbestaetigt=true")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total_count"] == 1
        assert body["items"][0]["id"] == flagged["id"]

    def test_false_filters_to_only_unflagged_candidates(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        flagged = _create_candidate(client, first_name="Flagged")
        _create_candidate(client, first_name="Normal")
        _flag_unbestaetigt(session_factory, flagged["id"])

        response = client.get("/api/v1/candidates?rollen_unbestaetigt=false")

        assert response.status_code == 200, response.text
        body = response.json()
        assert all(item["id"] != flagged["id"] for item in body["items"])

    def test_omitting_the_filter_returns_all_candidates(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        flagged = _create_candidate(client, first_name="Flagged")
        _create_candidate(client, first_name="Normal")
        _flag_unbestaetigt(session_factory, flagged["id"])

        response = client.get("/api/v1/candidates")

        assert response.status_code == 200, response.text
        assert response.json()["total_count"] == 2
