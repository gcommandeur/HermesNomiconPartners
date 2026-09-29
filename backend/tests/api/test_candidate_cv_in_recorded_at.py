"""Tests fuer cv_in_recorded_at (Analytics-Kennzahl "CV In") - Bugfix
"frisch angelegte Kandidaten mit CV werden nicht mitgezaehlt" (konkreter
Fall: Lorenz Hafner). CandidateService.update() stempelte das Feld schon
laenger beim False->True-Uebergang; ein Kandidat, der direkt MIT
cv_available=True angelegt wird, durchlaeuft diesen Uebergang nie - siehe
CandidateService.create()."""

from fastapi.testclient import TestClient


def test_creating_with_cv_available_true_stamps_cv_in_recorded_at_immediately(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/candidates",
        json={"first_name": "Lorenz", "last_name": "Hafner", "cv_available": True},
    )
    assert response.status_code == 201, response.text
    assert response.json()["cv_in_recorded_at"] is not None


def test_creating_with_cv_available_false_leaves_cv_in_recorded_at_null(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/candidates",
        json={"first_name": "Anna", "last_name": "Muster", "cv_available": False},
    )
    assert response.status_code == 201, response.text
    assert response.json()["cv_in_recorded_at"] is None


def test_creating_without_cv_available_leaves_cv_in_recorded_at_null(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/candidates", json={"first_name": "Bernd", "last_name": "Beispiel"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["cv_in_recorded_at"] is None


def test_update_transition_from_false_to_true_still_stamps_cv_in_recorded_at(
    client: TestClient,
) -> None:
    """Regressionstest fuer die bestehende update()-Logik - darf durch die
    neue create()-Ueberschreibung nicht kaputtgehen."""
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Clara", "last_name": "Test", "cv_available": False},
    ).json()
    assert candidate["cv_in_recorded_at"] is None

    response = client.patch(
        f"/api/v1/candidates/{candidate['id']}", json={"cv_available": True}
    )
    assert response.status_code == 200, response.text
    assert response.json()["cv_in_recorded_at"] is not None


def test_update_does_not_overwrite_an_already_recorded_timestamp(
    client: TestClient,
) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Dirk", "last_name": "Test", "cv_available": True},
    ).json()
    first_recorded_at = candidate["cv_in_recorded_at"]
    assert first_recorded_at is not None

    response = client.patch(
        f"/api/v1/candidates/{candidate['id']}",
        json={"cv_available": False},
    )
    assert response.status_code == 200, response.text
    # cv_available darf wieder auf False gehen (reines Anzeige-Flag), aber
    # der einmal gesetzte Stichtag-Zeitstempel bleibt stehen (Docstring:
    # "einmalig, nie erneut ueberschrieben"). Vergleich auf Sekunden-
    # Praezision statt exaktem String-Gleichheit - ein "Z"-Suffix-
    # Formatierungsunterschied zwischen den beiden Serialisierungspfaden
    # ist kein inhaltlicher Unterschied.
    assert response.json()["cv_in_recorded_at"][:19] == first_recorded_at[:19]
