from fastapi.testclient import TestClient


def test_candidate_crud(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/candidates",
        json={
            "first_name": "Erika",
            "last_name": "Muster",
            "email": "erika.muster@example.com",
            "job_title": "Steuerberaterin",
            "postal_code": "10115",
        },
    )
    assert create_response.status_code == 201
    candidate = create_response.json()
    assert candidate["first_name"] == "Erika"
    assert candidate["status"] == "active"

    candidate_id = candidate["id"]
    detail_response = client.get(f"/api/v1/candidates/{candidate_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["last_name"] == "Muster"

    update_response = client.patch(
        f"/api/v1/candidates/{candidate_id}",
        json={"city": "Berlin"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["city"] == "Berlin"

    list_response = client.get("/api/v1/candidates")
    assert list_response.status_code == 200
    assert list_response.json()["total_count"] == 1
    assert len(list_response.json()["items"]) == 1


def test_candidate_referred_by_roundtrip(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/candidates",
        json={"first_name": "Referral", "last_name": "Case", "referred_by": "Max Mustermann"},
    )
    assert create_response.status_code == 201
    candidate = create_response.json()
    assert candidate["referred_by"] == "Max Mustermann"

    detail = client.get(f"/api/v1/candidates/{candidate['id']}")
    assert detail.json()["referred_by"] == "Max Mustermann"

    updated = client.patch(
        f"/api/v1/candidates/{candidate['id']}",
        json={"referred_by": "Erika Musterfrau"},
    )
    assert updated.json()["referred_by"] == "Erika Musterfrau"


def test_candidate_has_ghosting_history_flag(client: TestClient) -> None:
    candidate = client.post(
        "/api/v1/candidates",
        json={"first_name": "Ghost", "last_name": "Case"},
    ).json()
    assert candidate["has_ghosting_history"] is False

    company = client.post("/api/v1/clients", json={"name": "Kanzlei Ghost"}).json()
    submission = client.post(
        "/api/v1/submissions",
        json={"candidate_id": candidate["id"], "client_company_id": company["id"]},
    ).json()
    client.patch(
        f"/api/v1/submissions/{submission['id']}/transition",
        json={"status": "cancelled", "cancellation_reason": "candidate_ghosting"},
    )

    detail = client.get(f"/api/v1/candidates/{candidate['id']}")
    assert detail.json()["has_ghosting_history"] is True

    list_response = client.get("/api/v1/candidates")
    listed = next(item for item in list_response.json()["items"] if item["id"] == candidate["id"])
    assert listed["has_ghosting_history"] is True


def test_reactivation_list_returns_only_stale_contacts(client: TestClient) -> None:
    stale = client.post(
        "/api/v1/candidates",
        json={"first_name": "Stale", "last_name": "Contact", "last_contact_at": "2020-01-01"},
    ).json()
    client.post(
        "/api/v1/candidates",
        json={"first_name": "Fresh", "last_name": "Contact", "last_contact_at": "2026-07-01"},
    )
    client.post("/api/v1/candidates", json={"first_name": "NoContact", "last_name": "AtAll"})

    response = client.get("/api/v1/candidates/reactivation-list")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert stale["id"] in ids
    assert len(ids) == 1

    narrow = client.get("/api/v1/candidates/reactivation-list?threshold_months=200")
    assert narrow.json() == []


class TestRollenFilter:
    """GET /candidates?rollen=... - Filter auf die normalisierte
    Candidate.rollen-Taxonomie (nicht zu verwechseln mit `role`, das auf
    job_title/Freitext filtert)."""

    def _create(self, client: TestClient, name: str, rollen: list[str]) -> dict:
        response = client.post(
            "/api/v1/candidates",
            json={"first_name": name, "last_name": "Test", "rollen": rollen},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def test_filters_to_candidates_with_the_given_rolle(self, client: TestClient) -> None:
        steuerberater = self._create(client, "Anna", ["steuerberater"])
        self._create(client, "Bernd", ["rechtsanwalt"])

        response = client.get("/api/v1/candidates?rollen=steuerberater")

        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert ids == [steuerberater["id"]]

    def test_multiple_rollen_are_or_combined(self, client: TestClient) -> None:
        steuerberater = self._create(client, "Anna", ["steuerberater"])
        anwalt = self._create(client, "Bernd", ["rechtsanwalt"])
        self._create(client, "Clara", ["partner"])

        response = client.get("/api/v1/candidates?rollen=steuerberater&rollen=rechtsanwalt")

        ids = {item["id"] for item in response.json()["items"]}
        assert ids == {steuerberater["id"], anwalt["id"]}

    def test_candidate_with_multiple_rollen_matches_any_of_them(self, client: TestClient) -> None:
        """Ein Kandidat kann mehrere gleichzeitig gueltige Rollen tragen
        (z.B. Steuerberater UND Partner) - ein Filter auf nur eine davon
        muss ihn trotzdem finden."""
        both = self._create(client, "Anna", ["steuerberater", "partner"])

        response = client.get("/api/v1/candidates?rollen=partner")

        ids = [item["id"] for item in response.json()["items"]]
        assert ids == [both["id"]]

    def test_does_not_false_positive_on_substring_overlap(self, client: TestClient) -> None:
        """'steuerfachwirt' darf NICHT auf einen Kandidaten mit nur
        'steuerfachangestellte' matchen, obwohl beide mit 'steuerfach'
        beginnen - der Substring-Match ist auf den quotierten Vollwert
        begrenzt."""
        self._create(client, "Anna", ["steuerfachangestellte"])

        response = client.get("/api/v1/candidates?rollen=steuerfachwirt")

        assert response.json()["items"] == []

    def test_combines_with_free_text_search(self, client: TestClient) -> None:
        """rollen-Filter und search sollen UND-verknuepft nutzbar sein, nicht
        sich gegenseitig ausschliessen."""
        match = self._create(client, "Anna", ["steuerberater"])
        self._create(client, "Anna", ["rechtsanwalt"])  # gleicher Vorname, andere Rolle

        response = client.get("/api/v1/candidates?rollen=steuerberater&search=Anna")

        ids = [item["id"] for item in response.json()["items"]]
        assert ids == [match["id"]]

    def test_unset_rollen_filter_returns_everyone(self, client: TestClient) -> None:
        self._create(client, "Anna", ["steuerberater"])
        self._create(client, "Bernd", [])

        response = client.get("/api/v1/candidates")

        assert response.json()["total_count"] == 2


class TestRadiusFilter:
    """GET /candidates?plz_ort=...&radius_km=... - echter Umkreis-Filter
    (repositories/candidates.py bleibt unberuehrt, siehe services/
    candidates.py::_list_filtered_by_radius)."""

    def _create(self, client: TestClient, name: str, *, city: str, **overrides: object) -> dict:
        payload = {"first_name": name, "last_name": "Test", "city": city}
        payload.update(overrides)
        response = client.post("/api/v1/candidates", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    def test_only_candidates_within_radius_are_returned(self, client: TestClient) -> None:
        nearby = self._create(client, "Anna", city="München")
        far_away = self._create(client, "Bernd", city="Berlin")

        response = client.get("/api/v1/candidates?plz_ort=München&radius_km=50")

        assert response.status_code == 200
        ids = [item["id"] for item in response.json()["items"]]
        assert ids == [nearby["id"]]
        assert far_away["id"] not in ids

    def test_wide_radius_includes_the_far_candidate_too(self, client: TestClient) -> None:
        nearby = self._create(client, "Anna", city="München")
        # ~456km von München (haversine_km) - passt in einen weiten, aber
        # innerhalb des API-Limits (max 500km) bleibenden Radius.
        far_away = self._create(client, "Bernd", city="Köln")

        response = client.get("/api/v1/candidates?plz_ort=München&radius_km=480")

        ids = {item["id"] for item in response.json()["items"]}
        assert ids == {nearby["id"], far_away["id"]}

    def test_candidate_without_resolvable_location_is_excluded(self, client: TestClient) -> None:
        """Kandidaten ohne aufloesbare Koordinaten fallen bei einem AKTIVEN
        Radius-Filter raus - sonst wirkt der Filter kaputt (Nutzer-Vorgabe)."""
        self._create(client, "Anna", city="Nirgendwostadt")

        response = client.get("/api/v1/candidates?plz_ort=München&radius_km=500")

        assert response.json()["items"] == []
        assert response.json()["total_count"] == 0

    def test_unresolvable_center_returns_zero_results_not_everyone(
        self, client: TestClient
    ) -> None:
        self._create(client, "Anna", city="München")

        response = client.get("/api/v1/candidates?plz_ort=Nirgendwostadt&radius_km=50")

        assert response.json()["items"] == []
        assert response.json()["total_count"] == 0

    def test_combines_with_rollen_and_search(self, client: TestClient) -> None:
        match = self._create(
            client, "Anna", city="München", rollen=["steuerberater"]
        )
        self._create(client, "Anna", city="München", rollen=["rechtsanwalt"])
        self._create(client, "Anna", city="Berlin", rollen=["steuerberater"])

        response = client.get(
            "/api/v1/candidates?plz_ort=München&radius_km=50&rollen=steuerberater&search=Anna"
        )

        ids = [item["id"] for item in response.json()["items"]]
        assert ids == [match["id"]]

    def test_region_substring_filter_still_works_unchanged(self, client: TestClient) -> None:
        """Der bestehende `region`-Parameter (reiner Substring-Match) bleibt
        unveraendert bestehen, unabhaengig vom neuen echten Umkreis-Filter."""
        match = self._create(client, "Anna", city="München")
        self._create(client, "Bernd", city="Berlin")

        response = client.get("/api/v1/candidates?region=münch")

        ids = [item["id"] for item in response.json()["items"]]
        assert ids == [match["id"]]

    def test_missing_radius_km_does_not_trigger_radius_filtering(
        self, client: TestClient
    ) -> None:
        """plz_ort allein (ohne radius_km) darf NICHT als aktiver Umkreis-
        Filter gelten - sonst gaebe es kein Radius zum Vergleichen."""
        self._create(client, "Anna", city="München")
        self._create(client, "Bernd", city="Berlin")

        response = client.get("/api/v1/candidates?plz_ort=München")

        assert response.json()["total_count"] == 2
