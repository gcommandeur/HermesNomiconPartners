import zipfile
from io import BytesIO

from docx import Document
from lxml import etree
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import Anrede
from cc_crm.services.profile_docx_export import (
    _WATERMARK_TEXT,
    _ZEITRAUM_AUSBILDUNG,
    _ZEITRAUM_CV,
    _header_label,
    _parse_short_profile,
    build_export_filename,
    generate_profile_docx,
)


def test_zeitraum_cv_matches_plain_master_template_format() -> None:
    match = _ZEITRAUM_CV.match("seit 04/2024 Steuerfachwirtin, Steuerberatungsgesellschaft")
    assert match is not None
    assert match.group(1) == "seit 04/2024"
    assert match.group(2) == "Steuerfachwirtin, Steuerberatungsgesellschaft"


def test_zeitraum_cv_tolerates_colon_after_zeitraum() -> None:
    """Regressionsschutz: das LLM formuliert manchmal mit Doppelpunkt nach
    dem Zeitraum ("04/2024 – heute: Rolle, ...") statt wie in den Master-
    Vorlagen ohne Doppelpunkt - ohne Toleranz fiel die Zeile komplett aus dem
    Zwei-Spalten-Layout (Zeitraum/Rolle) und landete als eine Zeile mit
    fuehrendem Leerzeichen-Tab im exportierten Word-Dokument."""
    match = _ZEITRAUM_CV.match(
        "10/2023 – 04/2024: Finance Manager, mittelständisches Unternehmen"
    )
    assert match is not None
    assert match.group(1) == "10/2023 – 04/2024"
    assert match.group(2) == "Finance Manager, mittelständisches Unternehmen"


def test_zeitraum_cv_tolerates_leading_bullet_dash() -> None:
    match = _ZEITRAUM_CV.match("- seit 03/2018 Bilanzbuchhalterin, Treuhandgesellschaft")
    assert match is not None
    assert match.group(1) == "seit 03/2018"
    assert match.group(2) == "Bilanzbuchhalterin, Treuhandgesellschaft"


def test_zeitraum_ausbildung_tolerates_colon_and_dash() -> None:
    match = _ZEITRAUM_AUSBILDUNG.match(
        "- 2026 (voraussichtlich): Certified IFRS Accountant (advanced)"
    )
    assert match is not None
    assert match.group(1) == "2026"
    assert match.group(2) == "(voraussichtlich): Certified IFRS Accountant (advanced)"


def test_zeitraum_ausbildung_matches_plain_master_template_format() -> None:
    match = _ZEITRAUM_AUSBILDUNG.match("2021 – 2023 Fortbildung zur Steuerfachwirtin")
    assert match is not None
    assert match.group(1) == "2021 – 2023"
    assert match.group(2) == "Fortbildung zur Steuerfachwirtin"


def test_zeitraum_ausbildung_no_match_without_leading_year() -> None:
    assert _ZEITRAUM_AUSBILDUNG.match("Ausbildung zum Steuerfachangestellten") is None


def test_parse_short_profile_multiple_sprachen_lines_become_separate_entries() -> None:
    """Nutzer-Vorgabe: jede Sprache eine eigene Zeile ('Sprache: Niveau'),
    nicht eine zusammengefasste 'Sprachen:'-Zeile - verifiziert, dass
    mehrere solcher Zeilen als separate weitere_infos-Eintraege ankommen."""
    text = (
        "## Kandidat:in-Nr. 42\n\n"
        "**Kurzprofil**\nText.\n\n"
        "**Weitere Infos**\n"
        "Deutsch: Muttersprache\n"
        "Englisch: Fließend\n"
        "EDV-Kenntnisse: DATEV | MS Office\n"
    )
    parsed = _parse_short_profile(text)
    assert parsed["kurzprofil"] == "Text."
    assert parsed["weitere_infos"] == {
        "Deutsch": "Muttersprache",
        "Englisch": "Fließend",
        "EDV-Kenntnisse": "DATEV | MS Office",
    }


def _make_candidate(**overrides: object) -> Candidate:
    defaults: dict[str, object] = {"first_name": "Max", "last_name": "Muster"}
    defaults.update(overrides)
    return Candidate(**defaults)


class TestHeaderLabel:
    """Nutzer-Vorgabe (per docx-Vergleich mit allen Referenzprofilen
    verifiziert): die Kopfzeile heisst AUSSCHLIESSLICH "Kandidat-Nr." oder
    "Kandidatin-Nr." - "Kandidat:in-Nr." kommt in KEINEM echten Profil vor
    und war ein Fehler des frueheren Codes bei anrede=divers/None."""

    def test_frau_gets_female_label(self) -> None:
        assert _header_label(_make_candidate(anrede=Anrede.FRAU)) == "Kandidatin-Nr."

    def test_herr_gets_male_label(self) -> None:
        assert _header_label(_make_candidate(anrede=Anrede.HERR)) == "Kandidat-Nr."

    def test_missing_anrede_follows_female_wording_in_profile_text(self) -> None:
        """Ohne gesetzte anrede richtet sich die Kopfzeile nach dem Genus,
        das das LLM im Fliesstext gewaehlt hat (es sieht den Vornamen im
        CV-Rohtext) - statt auf eine Doppelpunkt-Form auszuweichen."""
        candidate = _make_candidate(
            anrede=None,
            short_profile="## Kandidatin-Nr. 42\n\n**Kurzprofil**\nDie Kandidatin ist "
            "Steuerberaterin mit langjähriger Berufserfahrung.",
        )
        assert _header_label(candidate) == "Kandidatin-Nr."

    def test_missing_anrede_follows_male_wording_in_profile_text(self) -> None:
        candidate = _make_candidate(
            anrede=None,
            short_profile="## Kandidat-Nr. 42\n\n**Kurzprofil**\nDer Kandidat ist "
            "Steuerberater mit langjähriger Berufserfahrung.",
        )
        assert _header_label(candidate) == "Kandidat-Nr."

    def test_missing_anrede_and_no_profile_text_defaults_to_male_never_colon(self) -> None:
        label = _header_label(_make_candidate(anrede=None, short_profile=None))
        assert label == "Kandidat-Nr."
        assert ":" not in label

    def test_divers_never_produces_colon_form(self) -> None:
        label = _header_label(_make_candidate(anrede=Anrede.DIVERS, short_profile=None))
        assert ":" not in label


def test_build_export_filename_is_plain_number_only() -> None:
    """Nutzer-Vorgabe (nach Rueckmeldung): Profile heissen ausschliesslich
    'Nr. {candidate_number}.docx' - KEIN Rollen-/Qualifikations-Suffix mehr,
    unabhaengig von rollen/job_title/anrede."""
    candidate = _make_candidate(
        candidate_number="4024", anrede=Anrede.FRAU, rollen=["rechtsanwalt"]
    )
    assert build_export_filename(candidate) == "Nr. 4024.docx"


def test_build_export_filename_plain_number_regardless_of_job_title() -> None:
    candidate = _make_candidate(
        candidate_number="200", anrede=Anrede.HERR, rollen=[], job_title="Finance Manager"
    )
    assert build_export_filename(candidate) == "Nr. 200.docx"


def test_build_export_filename_never_contains_uuid_when_candidate_number_missing(
    session_factory: sessionmaker[Session],
) -> None:
    """Kernfall des Fixes: fehlt candidate_number, war der Dateiname zuvor
    die rohe UUID (unleserlich) - jetzt ein rein generischer Name, in
    keinem Fall die UUID. Braucht eine echte DB-Zeile, damit candidate.id
    tatsaechlich befuellt ist (bei einem nur konstruierten, nicht
    committeten Objekt waere id noch None und der Test wuerde trivial
    bestehen, ohne die eigentliche Regel zu pruefen)."""
    with session_factory() as session:
        candidate = Candidate(
            first_name="Max",
            last_name="Muster",
            candidate_number=None,
            anrede=Anrede.HERR,
            rollen=["steuerberater"],
        )
        session.add(candidate)
        session.commit()

        filename = build_export_filename(candidate)

        assert filename == "Profil.docx"
        assert str(candidate.id) not in filename


class TestDiagonalWatermark:
    """Punkt 1b des Wasserzeichen-Auftrags: echtes diagonales Word-
    Wasserzeichen (VML-Shape im Header-XML) statt der Fussnoten-Variante.
    Kann hier nicht in echtem Microsoft Word visuell geprueft werden (siehe
    Modul-Docstring "nobody on this team can render a .docx to check pixel
    layout") - diese Tests pruefen stattdessen, was automatisiert pruefbar
    ist: wohlgeformtes XML in JEDEM Teil des erzeugten .docx-Pakets, den
    Wasserzeichen-Text im sichtbaren (default) Header, und dass das
    Ergebnis sich klaglos ueber python-docx selbst wieder oeffnen laesst."""

    def test_generated_docx_is_a_well_formed_ooxml_package(self) -> None:
        candidate = Candidate(
            first_name="Anna",
            last_name="Muster",
            candidate_number="4456",
            short_profile=(
                "## Kandidatin-Nr. 4456\n\n**Kurzprofil**\nDie Kandidatin ist "
                "Steuerberaterin mit langjähriger Erfahrung.\n"
            ),
        )
        data = generate_profile_docx(candidate)

        with zipfile.ZipFile(BytesIO(data)) as archive:
            xml_parts = [n for n in archive.namelist() if n.endswith((".xml", ".rels"))]
            for name in xml_parts:
                etree.fromstring(archive.read(name))  # raises on malformed XML

            default_header_xml = archive.read("word/header2.xml").decode("utf-8")
            assert _WATERMARK_TEXT in default_header_xml
            assert "v:shape" in default_header_xml

        # Muss sich klaglos ueber python-docx selbst wieder oeffnen lassen -
        # ein Fehler hier waere ein starkes Warnsignal fuer eine kaputte
        # Datei, auch wenn es kein Ersatz fuer eine echte Word-Pruefung ist.
        reopened = Document(BytesIO(data))
        assert len(reopened.sections[0].header.paragraphs) > 0
