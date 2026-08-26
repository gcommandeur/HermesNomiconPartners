"""Tests fuer die erweiterte Kandidaten-Freitextsuche (GET /candidates?
search=...) - Konsolidierter Auftrag "Kandidaten-Freitextsuche auf alle
inhaltlichen Felder ausweiten und sprach-/schreibweisen-tolerant machen".

Deckt ab:
1. Suchfelder-Erweiterung: fachliche_schwerpunkte, edv_kenntnisse,
   ausbildung_titel, qualification, berufliche_stationen,
   current_employer_internal, summary sind jetzt durchsuchbar.
2. Synonyme (services/synonyms.py::search_expansion_terms) greifen ueber die
   Suche - Singular/Plural, Deutsch/Englisch, Ober-/Unterbegriffe.
3. Normalisierter Substring-Match (Umlaute/Bindestriche) findet Teilworte
   auch ohne Synonym-Eintrag.
4. Mehrere Suchworte sind UND-verknuepft.
5. Keine Fehlalarme (z.B. "steuerfachwirt" trifft NICHT
   "steuerfachangestellte" - gleiche Absicherung wie beim rollen-Filter).
6. Kombinierbarkeit mit den bestehenden Filtern (rollen/status/...).
"""

from fastapi.testclient import TestClient


def _create(client: TestClient, name: str, **overrides: object) -> dict:
    payload: dict[str, object] = {"first_name": name, "last_name": "Test"}
    payload.update(overrides)
    response = client.post("/api/v1/candidates", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _search(client: TestClient, query: str, **extra_params: str) -> list[dict]:
    params = "&".join([f"search={query}", *(f"{k}={v}" for k, v in extra_params.items())])
    response = client.get(f"/api/v1/candidates?{params}")
    assert response.status_code == 200, response.text
    return response.json()["items"]


class TestSearchFieldExpansion:
    """search durchsucht jetzt auch die CV-extrahierten Inhaltsfelder, nicht
    mehr nur Name/E-Mail/job_title/candidate_number."""

    def test_finds_by_fachliche_schwerpunkte(self, client: TestClient) -> None:
        match = _create(client, "Anna", fachliche_schwerpunkte=["Umsatzsteuer"])
        _create(client, "Bernd", fachliche_schwerpunkte=["Erbrecht"])

        items = _search(client, "Umsatzsteuer")

        assert [i["id"] for i in items] == [match["id"]]

    def test_finds_by_edv_kenntnisse(self, client: TestClient) -> None:
        match = _create(client, "Anna", edv_kenntnisse=["Lexware"])
        _create(client, "Bernd", edv_kenntnisse=["Addison"])

        items = _search(client, "Lexware")

        assert [i["id"] for i in items] == [match["id"]]

    def test_finds_by_ausbildung_titel(self, client: TestClient) -> None:
        match = _create(client, "Anna", ausbildung_titel="Steuerberaterin")

        items = _search(client, "Steuerberaterin")

        assert match["id"] in [i["id"] for i in items]

    def test_finds_by_qualification(self, client: TestClient) -> None:
        match = _create(client, "Anna", qualification="Fachanwalt für Steuerrecht")

        items = _search(client, "Fachanwalt")

        assert match["id"] in [i["id"] for i in items]

    def test_finds_by_current_employer_internal(self, client: TestClient) -> None:
        match = _create(client, "Anna", current_employer_internal="Muster & Partner GmbH")

        items = _search(client, "Muster")

        assert match["id"] in [i["id"] for i in items]

    def test_finds_by_summary(self, client: TestClient) -> None:
        match = _create(client, "Anna", summary="Langjährige Erfahrung in der Restrukturierung.")

        items = _search(client, "Restrukturierung")

        assert match["id"] in [i["id"] for i in items]

    def test_finds_by_berufliche_stationen(self, client: TestClient) -> None:
        match = _create(
            client,
            "Anna",
            berufliche_stationen=[
                {"kanzleityp": "Big4", "kanzleigroesse": "Big4", "dauer_jahre": 3}
            ],
        )
        _create(
            client,
            "Bernd",
            berufliche_stationen=[
                {"kanzleityp": "Einzelkanzlei", "kanzleigroesse": "klein", "dauer_jahre": 2}
            ],
        )

        items = _search(client, "Big4")

        assert match["id"] in [i["id"] for i in items]


class TestSearchSynonymExpansion:
    def test_plural_singular_via_synonym_group(self, client: TestClient) -> None:
        """'Jahresabschluss' muss auch einen Kandidaten mit der im CV
        extrahierten Pluralform 'Jahresabschlüsse' finden."""
        match = _create(client, "Anna", fachliche_schwerpunkte=["Jahresabschlüsse"])

        items = _search(client, "Jahresabschluss")

        assert match["id"] in [i["id"] for i in items]

    def test_german_query_finds_english_cv_content(self, client: TestClient) -> None:
        match = _create(client, "Anna", fachliche_schwerpunkte=["Tax Law"])

        items = _search(client, "Steuerrecht")

        assert match["id"] in [i["id"] for i in items]

    def test_payroll_finds_german_lohnbuchhaltung(self, client: TestClient) -> None:
        """'Payroll' (Suchbegriff) muss deutsche Lohnbuchhalter finden -
        auch wenn das CV nur 'Gehaltsabrechnung' oder 'Lohnbuchhaltung'
        nennt (unterschiedliche Wortstaemme, siehe HYPERNYMS)."""
        via_lohnbuchhaltung = _create(client, "Anna", fachliche_schwerpunkte=["Lohnbuchhaltung"])
        via_gehaltsabrechnung = _create(
            client, "Bernd", fachliche_schwerpunkte=["Gehaltsabrechnung"]
        )
        unrelated = _create(client, "Clara", fachliche_schwerpunkte=["Erbrecht"])

        items = _search(client, "Payroll")

        ids = {i["id"] for i in items}
        assert via_lohnbuchhaltung["id"] in ids
        assert via_gehaltsabrechnung["id"] in ids
        assert unrelated["id"] not in ids

    def test_lohn_hypernym_finds_payroll_entry(self, client: TestClient) -> None:
        match = _create(client, "Anna", fachliche_schwerpunkte=["Payroll"])

        items = _search(client, "Lohn")

        assert match["id"] in [i["id"] for i in items]

    def test_buchhaltung_finds_finanzbuchhaltung_via_substring_not_synonym(
        self, client: TestClient
    ) -> None:
        """Kompositum-Fall: 'Buchhaltung' findet 'Finanzbuchhaltung' und
        'Anlagenbuchhaltung' bereits ueber den normalisierten Substring-
        Match (deutsche Komposita enthalten den Grundbegriff woertlich) -
        kein eigener HYPERNYMS-Eintrag noetig."""
        finanz = _create(client, "Anna", fachliche_schwerpunkte=["Finanzbuchhaltung"])
        anlagen = _create(client, "Bernd", fachliche_schwerpunkte=["Anlagenbuchhaltung"])

        items = _search(client, "Buchhaltung")

        ids = {i["id"] for i in items}
        assert finanz["id"] in ids
        assert anlagen["id"] in ids

    def test_software_spelling_variants_via_synonyms(self, client: TestClient) -> None:
        match = _create(client, "Anna", edv_kenntnisse=["Microsoft Office"])

        items = _search(client, "MS Office")

        assert match["id"] in [i["id"] for i in items]


class TestSearchNormalizedSubstringTolerance:
    def test_case_insensitive_software_spelling(self, client: TestClient) -> None:
        """'DATEV' muss unabhaengig von der im CV verwendeten Schreibweise
        treffen (Gross-/Kleinschreibung)."""
        match = _create(client, "Anna", edv_kenntnisse=["Datev"])

        items = _search(client, "DATEV")

        assert match["id"] in [i["id"] for i in items]

    def test_umlaut_insensitive_query_finds_umlaut_content(self, client: TestClient) -> None:
        """Ein per ASCII-Transkription eingegebener Suchbegriff ('Rueck-
        stellungen' statt 'Rückstellungen') muss einen Kandidaten mit dem
        echten Umlaut im gespeicherten Wert finden, ohne die Daten selbst
        anzufassen. Bewusst NICHT ueber die vorhandene Rückstellungen-
        Synonymgruppe (die kennt "Rueckstellungen" bereits explizit) -
        stattdessen ueber current_employer_internal (Skalarfeld, kein
        JSON-Escaping) mit einem Wort, das in KEINER Synonymgruppe steht."""
        match = _create(
            client, "Anna", current_employer_internal="Müller Wirtschaftsprüfung GmbH"
        )

        items = _search(client, "Mueller")

        assert match["id"] in [i["id"] for i in items]

    def test_umlaut_insensitive_query_finds_umlaut_content_in_json_field(
        self, client: TestClient
    ) -> None:
        """Gleiche Toleranz auch fuer JSON-Listenfelder (fachliche_
        schwerpunkte) - dort liegt der Umlaut in der DB als \\uXXXX-Escape-
        Sequenz vor (SQLAlchemy-JSON-Default), nicht als rohes Unicode-
        Zeichen; die Normalisierung muss beide Formen falten."""
        match = _create(client, "Anna", fachliche_schwerpunkte=["Rückstellungen"])

        items = _search(client, "Rueckstellungen")

        assert match["id"] in [i["id"] for i in items]

    def test_hyphen_insensitive_query(self, client: TestClient) -> None:
        match = _create(client, "Anna", edv_kenntnisse=["MS-Office"])

        items = _search(client, "MS Office")

        assert match["id"] in [i["id"] for i in items]


class TestSearchNoFalsePositives:
    def test_steuerfachwirt_does_not_match_steuerfachangestellte(
        self, client: TestClient
    ) -> None:
        """Gleiche Absicherung wie beim bestehenden rollen-Filter: ein
        Suchbegriff darf nicht auf einen bloss aehnlich klingenden, aber
        anderen Begriff matchen."""
        _create(client, "Anna", job_title="Steuerfachangestellte")

        items = _search(client, "steuerfachwirt")

        assert items == []


class TestSearchMultipleTerms:
    def test_multiple_terms_are_and_combined(self, client: TestClient) -> None:
        both = _create(
            client,
            "Anna",
            edv_kenntnisse=["DATEV"],
            fachliche_schwerpunkte=["Lohnbuchhaltung"],
        )
        only_datev = _create(client, "Bernd", edv_kenntnisse=["DATEV"])
        only_lohn = _create(client, "Clara", fachliche_schwerpunkte=["Lohnbuchhaltung"])

        items = _search(client, "DATEV Lohnbuchhaltung")

        ids = {i["id"] for i in items}
        assert ids == {both["id"]}
        assert only_datev["id"] not in ids
        assert only_lohn["id"] not in ids


class TestSearchMatchReasons:
    """Punkt 5 des Auftrags: search_match_fields/search_matched_values
    machen im Frontend nachvollziehbar, WARUM ein Treffer gefunden wurde."""

    def test_match_fields_names_the_matching_column(self, client: TestClient) -> None:
        _create(client, "Anna", fachliche_schwerpunkte=["Umsatzsteuer"])

        items = _search(client, "Umsatzsteuer")

        assert items[0]["search_match_fields"] == ["fachliche_schwerpunkte"]

    def test_matched_values_names_the_concrete_list_entry(self, client: TestClient) -> None:
        _create(
            client,
            "Anna",
            fachliche_schwerpunkte=["Umsatzsteuer", "Erbrecht"],
        )

        items = _search(client, "Umsatzsteuer")

        assert items[0]["search_matched_values"] == ["Umsatzsteuer"]
        # Der NICHT gematchte Eintrag "Erbrecht" taucht nicht auf.
        assert "Erbrecht" not in items[0]["search_matched_values"]

    def test_multiple_matching_fields_are_all_listed(self, client: TestClient) -> None:
        _create(
            client,
            "Anna",
            job_title="Steuerberaterin",
            qualification="Steuerberaterin",
        )

        items = _search(client, "Steuerberaterin")

        assert set(items[0]["search_match_fields"]) == {"job_title", "qualification"}

    def test_match_fields_is_none_without_active_search(self, client: TestClient) -> None:
        _create(client, "Anna", fachliche_schwerpunkte=["Umsatzsteuer"])

        response = client.get("/api/v1/candidates")

        assert response.json()["items"][0]["search_match_fields"] is None

    def test_match_fields_is_none_on_single_candidate_get(self, client: TestClient) -> None:
        candidate = _create(client, "Anna", fachliche_schwerpunkte=["Umsatzsteuer"])

        response = client.get(f"/api/v1/candidates/{candidate['id']}")

        assert response.json()["search_match_fields"] is None


class TestSearchCombinesWithExistingFilters:
    def test_combines_with_rollen_filter(self, client: TestClient) -> None:
        match = _create(
            client,
            "Anna",
            rollen=["steuerberater"],
            fachliche_schwerpunkte=["Jahresabschluss"],
        )
        _create(
            client,
            "Bernd",
            rollen=["rechtsanwalt"],
            fachliche_schwerpunkte=["Jahresabschluss"],
        )

        params = "search=Jahresabschluss&rollen=steuerberater"
        response = client.get(f"/api/v1/candidates?{params}")

        ids = [item["id"] for item in response.json()["items"]]
        assert ids == [match["id"]]

    def test_combines_with_status_filter(self, client: TestClient) -> None:
        match = _create(
            client, "Anna", status="active", fachliche_schwerpunkte=["Erbrecht"]
        )
        _create(client, "Bernd", status="archived", fachliche_schwerpunkte=["Erbrecht"])

        items = _search(client, "Erbrecht", status="active")
        assert [i["id"] for i in items] == [match["id"]]

    def test_combines_with_abschluesse_filter(self, client: TestClient) -> None:
        match = _create(
            client,
            "Anna",
            abschluesse=["berufsexamen_stb"],
            fachliche_schwerpunkte=["Jahresabschluss"],
        )
        _create(
            client,
            "Bernd",
            abschluesse=["ausbildung"],
            fachliche_schwerpunkte=["Jahresabschluss"],
        )

        params = "search=Jahresabschluss&abschluesse=berufsexamen_stb"
        response = client.get(f"/api/v1/candidates?{params}")

        assert [item["id"] for item in response.json()["items"]] == [match["id"]]

    def test_combines_with_radius_filter(self, client: TestClient) -> None:
        """Der Radius-Filter laeuft ueber einen eigenen Codepfad
        (_list_filtered_by_radius, Python-seitige Nachfilterung) - search
        muss auch dort greifen, inkl. der search_match_fields-Berechnung."""
        match = _create(
            client, "Anna", city="München", fachliche_schwerpunkte=["Erbrecht"]
        )
        _create(client, "Bernd", city="München", fachliche_schwerpunkte=["Insolvenzrecht"])
        _create(client, "Clara", city="Berlin", fachliche_schwerpunkte=["Erbrecht"])

        response = client.get(
            "/api/v1/candidates?search=Erbrecht&plz_ort=München&radius_km=50"
        )

        items = response.json()["items"]
        assert [i["id"] for i in items] == [match["id"]]
        assert items[0]["search_match_fields"] == ["fachliche_schwerpunkte"]
