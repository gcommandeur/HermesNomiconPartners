from scripts.audit_contact_data_quality import _reasons_for


def test_clean_name_has_no_reasons() -> None:
    assert _reasons_for("Sabine", "Müller", "sabine.mueller@example.com") == []


def test_digits_in_name_are_flagged() -> None:
    assert any("Ziffern" in reason for reason in _reasons_for("Max2", "Muster", None))


def test_smashed_camel_case_name_is_flagged() -> None:
    """Gleiches Muster wie bei den frueher bereinigten Kandidatennamen (siehe
    scripts/sync_names_20260711.py) - ein ohne Leerzeichen zusammen-
    geschriebener Doppelname."""
    reasons = _reasons_for("AlenaDracke", "Mustermann", None)
    assert any("zusammengeschrieben" in reason for reason in reasons)


def test_email_like_name_is_flagged() -> None:
    reasons = _reasons_for("info@kanzlei.de", "Team", None)
    assert any("E-Mail-Adresse" in reason for reason in reasons)


def test_company_like_name_is_flagged() -> None:
    reasons = _reasons_for("Muster", "Steuerberatung GmbH", None)
    assert any("Firmenname" in reason for reason in reasons)


def test_blank_required_field_is_flagged() -> None:
    reasons = _reasons_for("", "Muster", None)
    assert reasons == ["Vor-/Nachname leer oder nur Leerzeichen"]


def test_single_char_name_is_flagged() -> None:
    reasons = _reasons_for("A", "Muster", None)
    assert any("kurzer Vor-/Nachname" in reason for reason in reasons)


def test_invalid_email_field_is_flagged() -> None:
    reasons = _reasons_for("Max", "Muster", "not-an-email")
    assert any("E-Mail-Feld" in reason for reason in reasons)


def test_special_characters_are_flagged() -> None:
    reasons = _reasons_for("Max#", "Muster", None)
    assert any("Sonderzeichen" in reason for reason in reasons)
