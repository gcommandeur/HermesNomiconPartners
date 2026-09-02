"""Tests fuer die automatische Rollen-Ableitung bei manuellem Anlegen/
Bearbeiten (Zwischenthema "Rolle fehlt bei gefuelltem Jobtitel" - siehe
CandidateService.create()/update()/_maybe_derive_rollen und
cv_extraction.py::derive_rollen_from_text). KEIN LLM-Call."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.enums import SourcingSourceType
from cc_crm.schemas.sourcing import SourcingLeadCreate
from cc_crm.services.sourcing import SourcingService


class TestDerivationOnCreate:
    def test_derives_rollen_from_job_title_when_not_given(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/candidates",
            json={"first_name": "Anna", "last_name": "Muster", "job_title": "Steuerberater"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["rollen"] == ["steuerberater"]

    def test_derives_rollen_from_qualification_when_not_given(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/candidates",
            json={
                "first_name": "Bernd",
                "last_name": "Beispiel",
                "qualification": "Bilanzbuchhalter",
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["rollen"] == ["bilanzbuchhalter"]

    def test_does_not_overwrite_explicitly_given_rollen(self, client: TestClient) -> None:
        """Nutzer-Vorgabe: nur ergaenzen, nie ueberschreiben - eine explizit
        mitgegebene Rolle bleibt unangetastet, auch wenn job_title etwas
        anderes nahelegen wuerde."""
        response = client.post(
            "/api/v1/candidates",
            json={
                "first_name": "Carla",
                "last_name": "Muster",
                "job_title": "Tax Manager",
                "rollen": ["partner"],
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["rollen"] == ["partner"]

    def test_no_keyword_match_leaves_rollen_empty(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/candidates",
            json={"first_name": "Dirk", "last_name": "Muster", "job_title": "Tax Manager"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["rollen"] == []

    def test_no_job_title_or_qualification_leaves_rollen_empty(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/candidates", json={"first_name": "Elena", "last_name": "Beispiel"}
        )
        assert response.status_code == 201, response.text
        assert response.json()["rollen"] == []


class TestDerivationOnUpdate:
    def test_derives_rollen_when_job_title_is_set_later(self, client: TestClient) -> None:
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Finn", "last_name": "Muster"}
        ).json()
        assert candidate["rollen"] == []

        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}", json={"job_title": "Wirtschaftsprüfer"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["rollen"] == ["wirtschaftspruefer"]

    def test_does_not_overwrite_already_set_rollen(self, client: TestClient) -> None:
        candidate = client.post(
            "/api/v1/candidates",
            json={"first_name": "Greta", "last_name": "Beispiel", "rollen": ["partner"]},
        ).json()

        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}", json={"job_title": "Steuerberater"}
        )

        assert response.status_code == 200, response.text
        # rollen bleibt "partner" - wird NICHT um steuerberater ergaenzt oder
        # ersetzt, sobald schon irgendetwas gesetzt ist.
        assert response.json()["rollen"] == ["partner"]

    def test_unrelated_field_update_does_not_trigger_derivation_attempt(
        self, client: TestClient
    ) -> None:
        """job_title bleibt unveraendert und leer - ein reines Gehalts-
        Update darf keine Rolle "erraten"."""
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Hannes", "last_name": "Muster"}
        ).json()

        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}", json={"salary_expectation": "80.000 €"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["rollen"] == []

    def test_derives_from_qualification_update_too(self, client: TestClient) -> None:
        candidate = client.post(
            "/api/v1/candidates", json={"first_name": "Ina", "last_name": "Beispiel"}
        ).json()

        response = client.patch(
            f"/api/v1/candidates/{candidate['id']}",
            json={"qualification": "Steuerfachangestellte"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["rollen"] == ["steuerfachangestellte"]


class TestDerivationOnSourcingApproval:
    def test_approved_lead_gets_rollen_derived_from_job_title(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        """sourcing.py::approve_lead ruft bereits explizit derive_rollen_from_
        text (ueber den _rollen_from_text-Wrapper) auf - dieser Test deckt
        den End-to-End-Weg ab, nicht nur die reine Funktion."""
        with session_factory() as session:
            lead = SourcingService(session).create_lead(
                SourcingLeadCreate(
                    source_type=SourcingSourceType.STEUERBERATERVERZEICHNIS,
                    first_name="Jonas",
                    last_name="Sourced",
                    raw_data={"beruf": "Steuerberater(in)"},
                )
            )
            assert lead is not None
            lead_id = lead.id

        approve_response = client.post(f"/api/v1/sourcing/leads/{lead_id}/approve")
        assert approve_response.status_code == 200, approve_response.text
        candidate = client.get(
            f"/api/v1/candidates/{approve_response.json()['created_candidate_id']}"
        ).json()

        assert candidate["rollen"] == ["steuerberater"]
