from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import Anrede
from cc_crm.services.profile_docx_export import (
    _ZEITRAUM_AUSBILDUNG,
    _ZEITRAUM_CV,
    _parse_short_profile,
    build_export_filename,
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
        "**Über die Person**\nText.\n\n"
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


def test_build_export_filename_uses_gendered_primary_role() -> None:
    candidate = _make_candidate(
        candidate_number="4024", anrede=Anrede.FRAU, rollen=["rechtsanwalt"]
    )
    assert build_export_filename(candidate) == "Nr. 4024_Rechtsanwältin.docx"


def test_build_export_filename_male_role_variant() -> None:
    candidate = _make_candidate(
        candidate_number="4009", anrede=Anrede.HERR, rollen=["rechtsanwalt"]
    )
    assert build_export_filename(candidate) == "Nr. 4009_Rechtsanwalt.docx"


def test_build_export_filename_partner_is_ungegendert() -> None:
    candidate = _make_candidate(
        candidate_number="4016", anrede=Anrede.FRAU, rollen=["partner"]
    )
    assert build_export_filename(candidate) == "Nr. 4016_Partner.docx"


def test_build_export_filename_uses_first_relevant_role_when_multiple() -> None:
    candidate = _make_candidate(
        candidate_number="100", anrede=Anrede.HERR, rollen=["steuerberater", "partner"]
    )
    assert build_export_filename(candidate) == "Nr. 100_Steuerberater.docx"


def test_build_export_filename_falls_back_to_job_title_when_rollen_empty() -> None:
    candidate = _make_candidate(
        candidate_number="200", anrede=Anrede.HERR, rollen=[], job_title="Finance Manager"
    )
    assert build_export_filename(candidate) == "Nr. 200_Finance Manager.docx"


def test_build_export_filename_falls_back_to_job_title_when_rollen_only_sonstige() -> None:
    candidate = _make_candidate(
        candidate_number="201",
        anrede=Anrede.HERR,
        rollen=["sonstige"],
        job_title="Konzern-Buchhalter",
    )
    assert build_export_filename(candidate) == "Nr. 201_Konzern-Buchhalter.docx"


def test_build_export_filename_sanitizes_unsafe_characters_in_job_title_fallback() -> None:
    candidate = _make_candidate(
        candidate_number="202", anrede=Anrede.HERR, rollen=[], job_title='Tax: Manager/Advisor'
    )
    filename = build_export_filename(candidate)
    assert filename == "Nr. 202_Tax_ Manager_Advisor.docx"


def test_build_export_filename_plain_number_when_rollen_and_job_title_empty() -> None:
    candidate = _make_candidate(
        candidate_number="300", anrede=Anrede.HERR, rollen=[], job_title=None
    )
    assert build_export_filename(candidate) == "Nr. 300.docx"


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
