import json

import pytest

from cc_crm.services import cv_extraction
from cc_crm.services.cv_extraction import extract_text_from_bytes


def _fake_generate_text(payload: dict[str, object]):
    def fake(
        *, system_prompt: str, user_message: str, max_tokens: int = 1000, timeout: float = 45.0
    ) -> str:
        return json.dumps(payload)

    return fake


class TestNormalizeRollen:
    def test_keeps_only_known_enum_values(self) -> None:
        result = cv_extraction._normalize_rollen(
            ["steuerberater", "partner", "erfundene_rolle", "STEUERBERATER"]
        )
        assert result == ["steuerberater", "partner"]

    def test_non_list_input_returns_empty_list(self) -> None:
        assert cv_extraction._normalize_rollen(None) == []
        assert cv_extraction._normalize_rollen("steuerberater") == []

    def test_deduplicates(self) -> None:
        assert cv_extraction._normalize_rollen(["steuerberater", "steuerberater"]) == [
            "steuerberater"
        ]

    def test_multiple_simultaneous_roles_are_all_kept(self) -> None:
        result = cv_extraction._normalize_rollen(["rechtsanwalt", "steuerberater", "partner"])
        assert set(result) == {"rechtsanwalt", "steuerberater", "partner"}


class TestNormalizeBeruflicheStationen:
    def test_drops_station_missing_kanzleityp_or_kanzleigroesse(self) -> None:
        raw = [
            {"kanzleityp": "Steuerkanzlei", "kanzleigroesse": "", "dauer_jahre": 3},
            {"kanzleityp": "", "kanzleigroesse": "Big4", "dauer_jahre": 3},
            {"kanzleigroesse": "Big4", "dauer_jahre": 3},
        ]
        assert cv_extraction._normalize_berufliche_stationen(raw) == []

    def test_keeps_well_formed_station_with_normalized_rolle(self) -> None:
        raw = [
            {
                "rolle": "STEUERBERATER",
                "kanzleityp": "Steuerkanzlei",
                "kanzleigroesse": "10-20 Mitarbeitende",
                "dauer_jahre": 4,
            }
        ]
        result = cv_extraction._normalize_berufliche_stationen(raw)
        assert result == [
            {
                "kanzleityp": "Steuerkanzlei",
                "kanzleigroesse": "10-20 Mitarbeitende",
                "dauer_jahre": 4.0,
                "rolle": "steuerberater",
            }
        ]

    def test_invalid_rolle_becomes_none_not_dropped(self) -> None:
        raw = [
            {
                "rolle": "erfundene_rolle",
                "kanzleityp": "Steuerkanzlei",
                "kanzleigroesse": "klein",
                "dauer_jahre": 2,
            }
        ]
        result = cv_extraction._normalize_berufliche_stationen(raw)
        assert result[0]["rolle"] is None

    def test_missing_dauer_jahre_defaults_to_zero(self) -> None:
        raw = [{"kanzleityp": "Steuerkanzlei", "kanzleigroesse": "klein"}]
        result = cv_extraction._normalize_berufliche_stationen(raw)
        assert result[0]["dauer_jahre"] == 0.0

    def test_non_list_input_returns_empty_list(self) -> None:
        assert cv_extraction._normalize_berufliche_stationen(None) == []
        assert cv_extraction._normalize_berufliche_stationen({"kanzleityp": "x"}) == []


def test_extract_candidate_fields_normalizes_rollen_and_stationen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text(
            {
                "first_name": "Jana",
                "last_name": "Beispiel",
                "rollen": ["steuerberater", "partner", "unbekannt"],
                "current_employer_internal": "Muster Steuerkanzlei GmbH",
                "berufliche_stationen": [
                    {
                        "rolle": "steuerberater",
                        "kanzleityp": "Steuerkanzlei",
                        "kanzleigroesse": "20 Mitarbeitende",
                        "dauer_jahre": 5,
                    },
                    {"kanzleityp": "", "kanzleigroesse": "", "dauer_jahre": 1},
                ],
                "fachliche_schwerpunkte": ["Umsatzsteuer"],
            }
        ),
    )

    result = cv_extraction.extract_candidate_fields("irrelevanter CV-Text")

    assert result["rollen"] == ["steuerberater", "partner"]
    assert result["current_employer_internal"] == "Muster Steuerkanzlei GmbH"
    # Die zweite Station (leerer kanzleityp/kanzleigroesse) wurde verworfen.
    assert result["berufliche_stationen"] == [
        {
            "kanzleityp": "Steuerkanzlei",
            "kanzleigroesse": "20 Mitarbeitende",
            "dauer_jahre": 5.0,
            "rolle": "steuerberater",
        }
    ]


def test_extract_candidate_fields_defaults_missing_rollen_and_stationen_to_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text({"first_name": "Jana"}),
    )

    result = cv_extraction.extract_candidate_fields("irrelevanter CV-Text")

    assert result["rollen"] == []
    assert result["berufliche_stationen"] == []


def test_extract_candidate_fields_keeps_generic_employer_description_for_agency_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bei einem anonymisierten Commandeur-Bewerberprofil ist ein etwaiger
    'Arbeitgeber' im Text bereits generisch/anonymisiert (siehe Prompt-Regel)
    - anders als first_name/email/etc. wird current_employer_internal hier
    NICHT hart auf None gesetzt, sondern der (bereits ungefaehrliche) Wert
    des Modells uebernommen."""
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text(
            {
                "first_name": "Jana",
                "current_employer_internal": "mittelständische Steuerkanzlei in NRW",
            }
        ),
    )

    letterhead_text = "Commandeur Consulting GmbH, Talstraße 112, 41199 Mönchengladbach"
    result = cv_extraction.extract_candidate_fields(letterhead_text)

    assert result["first_name"] is None
    assert result["current_employer_internal"] == "mittelständische Steuerkanzlei in NRW"


def test_cv_structured_fields_includes_new_fields() -> None:
    assert "rollen" in cv_extraction.CV_STRUCTURED_FIELDS
    assert "current_employer_internal" in cv_extraction.CV_STRUCTURED_FIELDS
    assert "berufliche_stationen" in cv_extraction.CV_STRUCTURED_FIELDS


class TestNebentaetigkeitExclusion:
    """Regressionsschutz fuer den bestaetigten Bug an Kandidat #2359 (Sedighi):
    eine spaeter liegende, im CV explizit unter 'Praktika und
    Nebentaetigkeiten' gefuehrte Position (Lieferdienst) wurde faelschlich als
    zeitlich letzte Station fuer rollen/current_employer_internal herangezogen
    - obwohl davor eine reguläre Berufserfahrung (Wirtschaftspruefungsassistent,
    4,5 Jahre unter 'BERUFSERFAHRUNG') klar erkennbar war. Ergebnis vor dem Fix:
    rollen=["sonstige"], current_employer_internal="yourdelivery GmbH".

    Da die eigentliche Ableitung ausschliesslich im LLM-Prompt steckt (keine
    eigene Nachbearbeitungslogik im Code), kann ein Unit-Test nur pruefen,
    dass (a) die neue Ausschluss-Regel im Prompt-Text vorhanden ist und (b)
    die Normalisierung eine PROMPT-KONFORME Antwort korrekt durchreicht, ohne
    sie zu verfaelschen. Ob das Modell der Regel tatsaechlich folgt, wird
    weiterhin per echtem Testlauf gegen Kandidat #2359 verifiziert (siehe
    Backfill-Skript-Stichprobe), nicht durch diesen Test."""

    def test_prompt_contains_nebentaetigkeit_exclusion_rule(self) -> None:
        prompt = cv_extraction._FIELD_EXTRACTION_SYSTEM_PROMPT
        assert "Nebentätigkeiten" in prompt
        assert "Praktika" in prompt
        assert "Aushilfstätigkeit" in prompt

    def test_normalization_preserves_correct_rolle_for_sedighi_like_case(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simuliert eine PROMPT-KONFORME Modellantwort fuer den Sedighi-Fall
        (regulaere Berufserfahrung als Pruefungsassistent, gefolgt von einer
        spaeteren, als Nebentaetigkeit gekennzeichneten Lieferdienst-Station)
        und prueft, dass extract_candidate_fields() dieses Ergebnis
        unveraendert durchreicht statt es bei der Normalisierung zu
        verfaelschen."""
        monkeypatch.setattr(
            cv_extraction,
            "generate_text",
            _fake_generate_text(
                {
                    "first_name": "Amirnader",
                    "last_name": "Sedighi",
                    "rollen": ["pruefungsassistent"],
                    "current_employer_internal": "Wirtschaftsprüfungsgesellschaft, "
                    "Faranegarhesab khobre",
                    "berufliche_stationen": [
                        {
                            "rolle": None,
                            "kanzleityp": "Sonstiges (Lieferdienst)",
                            "kanzleigroesse": "unbekannt",
                            "dauer_jahre": 2,
                        },
                        {
                            "rolle": "pruefungsassistent",
                            "kanzleityp": "Wirtschaftsprüfungsgesellschaft",
                            "kanzleigroesse": "unbekannt",
                            "dauer_jahre": 4.5,
                        },
                    ],
                    "fachliche_schwerpunkte": ["Jahresabschlussprüfung"],
                }
            ),
        )

        result = cv_extraction.extract_candidate_fields("irrelevanter CV-Text")

        assert result["rollen"] == ["pruefungsassistent"]
        assert result["current_employer_internal"] == (
            "Wirtschaftsprüfungsgesellschaft, Faranegarhesab khobre"
        )
        # Die Nebentaetigkeit bleibt Teil der vollstaendigen Historie, ist aber
        # NICHT die Quelle von rollen/current_employer_internal.
        assert len(result["berufliche_stationen"]) == 2
        assert result["berufliche_stationen"][0]["rolle"] is None


class TestRegexFallback:
    """Regressionsschutz fuer den Notfall-Fallback bei leerem API-Guthaben/
    Netzwerk-Timeout - live beobachtet: das Kandidat-anlegen-Formular
    scheiterte komplett (504), wenn der LLM-Call fehlschlug. Statt die
    Extraktion (und damit das Formular) mit einem Fehler abzubrechen, muss
    jetzt eine regelbasierte Notfall-Extraktion der Kontaktfelder greifen."""

    def test_falls_back_to_regex_when_llm_raises_ai_provider_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_ai_provider_error(**kwargs: object) -> str:
            raise cv_extraction.AIProviderError("Guthaben zu niedrig")

        monkeypatch.setattr(cv_extraction, "generate_text", raise_ai_provider_error)

        cv_text = (
            "Lebenslauf\nMax Mustermann\nmax.mustermann@example.com\n"
            "Telefon: 0170 1234567\n49191 Belm\n"
        )
        result = cv_extraction.extract_candidate_fields(cv_text)

        assert result["email"] == "max.mustermann@example.com"
        assert result["phone"] == "0170 1234567"
        assert result["postal_code"] == "49191"
        assert result["city"] == "Belm"
        # Name wird NICHT geraten - braucht Sprachverstaendnis, nicht per
        # Regex zuverlaessig erkennbar.
        assert result["first_name"] is None
        assert result["last_name"] is None
        # Smarte Felder bleiben leer statt zu crashen.
        assert result["rollen"] == []
        assert result["fachliche_schwerpunkte"] == []
        assert result["berufliche_stationen"] == []

    def test_falls_back_to_regex_when_llm_returns_broken_json(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_broken_json(**kwargs: object) -> str:
            return "das ist kein JSON"

        monkeypatch.setattr(cv_extraction, "generate_text", fake_broken_json)

        result = cv_extraction.extract_candidate_fields("Kontakt: test@example.com")

        assert result["email"] == "test@example.com"

    def test_regex_fallback_never_raises_on_empty_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Kernfall aus der Praxis: ein gescanntes PDF ohne Textebene liefert
        leeren cv_text - der Fallback muss trotzdem ein valides, leeres
        Ergebnis liefern statt zu crashen (live reproduziert mit einer
        echten leeren Kandidaten-CV)."""

        def raise_ai_provider_error(**kwargs: object) -> str:
            raise cv_extraction.AIProviderError("Guthaben zu niedrig")

        monkeypatch.setattr(cv_extraction, "generate_text", raise_ai_provider_error)

        result = cv_extraction.extract_candidate_fields("")

        assert result == dict(cv_extraction._EMPTY_STRUCTURED_FIELDS)

    def test_regex_fallback_suppresses_agency_address_like_llm_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Derselbe Schutz wie im LLM-Pfad: ein faelschlich als CV
        hochgeladenes, von Commandeur selbst erzeugtes anonymes Profil darf
        auch im Fallback nie die eigene Kanzlei-Adresse als Kandidatendaten
        liefern."""

        def raise_ai_provider_error(**kwargs: object) -> str:
            raise cv_extraction.AIProviderError("Guthaben zu niedrig")

        monkeypatch.setattr(cv_extraction, "generate_text", raise_ai_provider_error)

        letterhead_text = (
            "Commandeur Consulting GmbH, Talstraße 112, 41199 Mönchengladbach\n"
            "kontakt@commandeur-consulting.de, Tel. 02161 1234567"
        )
        result = cv_extraction.extract_candidate_fields(letterhead_text)

        assert result["email"] is None
        assert result["phone"] is None
        assert result["postal_code"] is None
        assert result["city"] is None


class TestExtractTextFromBytesPdfLayoutFallback:
    """Regressionsschutz fuer einen bestaetigten pypdf-Bug: bei Seiten mit
    rotierten Text-Elementen (z.B. quer gedrehte Seitenrand-Vermerke) liefert
    extraction_mode='layout' fuer die GANZE Seite einen leeren String, obwohl
    derselbe Text im Default-Modus problemlos gefunden wird - live bestaetigt
    an 28 von 44 CVs, die per Layout-Modus faelschlich als 'leer/gescannt'
    klassifiziert wurden (siehe diagnose_arbeitszeugnis_statt_cv.py)."""

    class _FakePage:
        def __init__(self, layout_text: str, default_text: str) -> None:
            self._layout_text = layout_text
            self._default_text = default_text

        def extract_text(self, extraction_mode: str | None = None) -> str:
            if extraction_mode == "layout":
                return self._layout_text
            return self._default_text

    class _FakeReader:
        def __init__(
            self, pages: list["TestExtractTextFromBytesPdfLayoutFallback._FakePage"]
        ) -> None:
            self.pages = pages

    def test_falls_back_to_default_mode_when_layout_mode_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        page = self._FakePage(layout_text="", default_text="Jana Gußer\nSteuerberaterin seit 2019")
        monkeypatch.setattr(
            cv_extraction, "PdfReader", lambda _bytesio: self._FakeReader([page])
        )

        result = extract_text_from_bytes("cv.pdf", b"%PDF-fake-bytes")

        assert result == "Jana Gußer\nSteuerberaterin seit 2019"

    def test_prefers_layout_mode_when_it_returns_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Der Normalfall bleibt unveraendert: liefert der Layout-Modus Text,
        wird der (i.d.R. besser lesbare) Layout-Text verwendet, nicht der
        Default-Text."""
        page = self._FakePage(layout_text="Jana Gußer (layout)", default_text="J a n a  G u ß e r")
        monkeypatch.setattr(
            cv_extraction, "PdfReader", lambda _bytesio: self._FakeReader([page])
        )

        result = extract_text_from_bytes("cv.pdf", b"%PDF-fake-bytes")

        assert result == "Jana Gußer (layout)"

    def test_falls_back_per_page_independently(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ein mehrseitiges CV, bei dem nur EINE Seite vom Bug betroffen ist -
        die anderen Seiten sollen weiterhin ihren (besseren) Layout-Text
        behalten statt pauschal auf den Default-Modus umzuschalten."""
        page1 = self._FakePage(layout_text="Seite 1 layout", default_text="Seite1default")
        page2 = self._FakePage(layout_text="", default_text="Seite 2 nur im Default lesbar")
        monkeypatch.setattr(
            cv_extraction, "PdfReader", lambda _bytesio: self._FakeReader([page1, page2])
        )

        result = extract_text_from_bytes("cv.pdf", b"%PDF-fake-bytes")

        assert result == "Seite 1 layout\nSeite 2 nur im Default lesbar"
