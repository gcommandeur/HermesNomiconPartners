from cc_crm.services.profile_docx_export import _ZEITRAUM_AUSBILDUNG, _ZEITRAUM_CV


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
