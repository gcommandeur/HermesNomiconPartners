"""Tests fuer die LinkedIn-Erkennung/-Extraktion (services/mail_classifier.py).

Die Beispieltexte sind der vom Nutzer beschriebenen Struktur echter
LinkedIn-Benachrichtigungen nachgebildet. Sobald echte Mails aus
info@commandeurconsulting.de vorliegen, sollten hier zusaetzlich 1-2
woertliche Originale (anonymisiert) als Regressionsfaelle landen - die
Footer-Marker sind bis dahin nicht endgueltig verifiziert.
"""

from cc_crm.services.mail_classifier import (
    extract_candidate_name,
    extract_linkedin_content,
    extract_role_title,
    is_linkedin_message,
    strip_linkedin_boilerplate,
)


class TestIsLinkedInMessage:
    def test_detects_by_sender_domain(self) -> None:
        assert is_linkedin_message(
            from_address="hit-reply@linkedin.com", from_name="John Paul Fürus", subject="Hallo"
        )

    def test_detects_by_sender_name(self) -> None:
        assert is_linkedin_message(
            from_address="noreply@example.com", from_name="LinkedIn Recruiter", subject="Hallo"
        )

    def test_detects_by_subject_prefix(self) -> None:
        assert is_linkedin_message(
            from_address="noreply@example.com",
            from_name="Irgendwer",
            subject="Message replied: Steuerberater (m/w/d) gesucht",
        )

    def test_subject_prefix_is_case_insensitive(self) -> None:
        assert is_linkedin_message(
            from_address=None, from_name=None, subject="MESSAGE ACCEPTED: Rolle"
        )

    def test_normal_mail_is_not_linkedin(self) -> None:
        assert not is_linkedin_message(
            from_address="bewerbung@kanzlei-mueller.de",
            from_name="Anna Müller",
            subject="Rückfrage zu Ihrer Anfrage",
        )

    def test_all_fields_missing_is_not_linkedin(self) -> None:
        assert not is_linkedin_message(from_address=None, from_name=None, subject=None)

    def test_sender_domain_wins_even_without_subject(self) -> None:
        """Regressionsschutz: die drei Signale sind bewusst ODER-verknuepft,
        damit eine Aenderung an LinkedIns Betreff-Format die Erkennung nicht
        komplett ausfallen laesst."""
        assert is_linkedin_message(
            from_address="messages-noreply@linkedin.com", from_name=None, subject=None
        )


class TestExtractCandidateName:
    def test_plain_name(self) -> None:
        assert extract_candidate_name("John Paul Fürus") == "John Paul Fürus"

    def test_strips_quotes_and_via_linkedin_suffix(self) -> None:
        assert extract_candidate_name('"Anna Müller via LinkedIn"') == "Anna Müller"

    def test_collapses_whitespace(self) -> None:
        assert extract_candidate_name("  Max    Mustermann  ") == "Max Mustermann"

    def test_generic_linkedin_sender_is_not_a_person(self) -> None:
        """Wichtig: bei 'LinkedIn Recruiter' darf spaeter KEIN
        Namensabgleich laufen - sonst wuerde gegen einen Platzhalternamen
        gematcht."""
        assert extract_candidate_name("LinkedIn Recruiter") is None

    def test_email_address_as_display_name_is_not_a_person(self) -> None:
        assert extract_candidate_name("hit-reply@linkedin.com") is None

    def test_empty_input(self) -> None:
        assert extract_candidate_name(None) is None
        assert extract_candidate_name("   ") is None


class TestExtractRoleTitle:
    def test_extracts_from_message_replied_prefix(self) -> None:
        assert (
            extract_role_title("Message replied: Steuerberater (m/w/d) gesucht")
            == "Steuerberater (m/w/d) gesucht"
        )

    def test_extracts_from_message_accepted_prefix(self) -> None:
        assert extract_role_title("Message accepted: Bilanzbuchhalter") == "Bilanzbuchhalter"

    def test_returns_none_without_known_prefix(self) -> None:
        """Ohne Praefix gibt es keinen separaten Rollentitel - der Betreff
        selbst wird dann unveraendert als Activity-Betreff genutzt."""
        assert extract_role_title("Rückfrage zu Ihrer Anfrage") is None

    def test_returns_none_when_nothing_follows_prefix(self) -> None:
        assert extract_role_title("Message replied:") is None

    def test_empty_input(self) -> None:
        assert extract_role_title(None) is None


class TestStripLinkedInBoilerplate:
    def test_cuts_everything_from_first_footer_marker(self) -> None:
        body = (
            "Hallo Herr Commandeur,\n"
            "\n"
            "vielen Dank für Ihre Nachricht. Ich bin grundsätzlich offen für\n"
            "ein Gespräch.\n"
            "\n"
            "Viele Grüße\n"
            "John Paul Fürus\n"
            "\n"
            "This email was intended for Gege Commandeur.\n"
            "Learn why we included this.\n"
            "Unsubscribe\n"
            "© 2026 LinkedIn Corporation, 1000 W Maude Avenue\n"
        )
        result = strip_linkedin_boilerplate(body)
        assert result.startswith("Hallo Herr Commandeur,")
        assert result.endswith("John Paul Fürus")
        assert "This email was intended for" not in result
        assert "LinkedIn Corporation" not in result

    def test_removes_logo_alt_text_lines(self) -> None:
        body = "[LinkedIn]\n\nHallo,\n\ngerne telefonieren.\n"
        result = strip_linkedin_boilerplate(body)
        assert result == "Hallo,\n\ngerne telefonieren."

    def test_keeps_text_unchanged_when_no_footer_present(self) -> None:
        """Kein Marker gefunden -> lieber Rest-Boilerplate stehen lassen als
        echten Kandidatentext abschneiden."""
        body = "Hallo,\n\nich melde mich nächste Woche.\n\nViele Grüße\nAnna"
        assert strip_linkedin_boilerplate(body) == body

    def test_collapses_excess_blank_lines(self) -> None:
        assert strip_linkedin_boilerplate("Zeile 1\n\n\n\n\nZeile 2") == "Zeile 1\n\nZeile 2"

    def test_handles_crlf_line_endings(self) -> None:
        body = "Hallo,\r\n\r\ngerne.\r\nUnsubscribe\r\n"
        assert strip_linkedin_boilerplate(body) == "Hallo,\n\ngerne."

    def test_empty_input_returns_empty_string(self) -> None:
        assert strip_linkedin_boilerplate(None) == ""
        assert strip_linkedin_boilerplate("") == ""


class TestExtractLinkedInContent:
    def test_full_extraction_of_a_candidate_reply(self) -> None:
        content = extract_linkedin_content(
            from_name="John Paul Fürus",
            subject="Message replied: Steuerberater (m/w/d) gesucht",
            body_text=(
                "Guten Tag,\n\nklingt interessant - wann passt es Ihnen für ein\n"
                "kurzes Telefonat?\n\nBeste Grüße\n"
                "\nThis email was intended for Gege Commandeur.\n"
            ),
        )
        assert content.candidate_name == "John Paul Fürus"
        assert content.role_title == "Steuerberater (m/w/d) gesucht"
        assert content.message_text.startswith("Guten Tag,")
        assert "wann passt es Ihnen" in content.message_text
        assert "intended for" not in content.message_text

    def test_generic_sender_yields_no_name_but_still_keeps_text(self) -> None:
        content = extract_linkedin_content(
            from_name="LinkedIn Recruiter",
            subject="Message accepted: Rechtsanwalt",
            body_text="Ihre Nachricht wurde angenommen.",
        )
        assert content.candidate_name is None
        assert content.role_title == "Rechtsanwalt"
        assert content.message_text == "Ihre Nachricht wurde angenommen."
