"""Tests fuer services/sourcing.py::_rollen_from_text (Konsolidierter
Auftrag "Titelschutz-Korrektur ohne Datenverlust + Rollen-Herkunft +
Rechtsgebiete", Schritt 3a).

Hintergrund: das Titelschutz-Audit fand fuer "partner" einen
Fehlklassifikations-Fall (Nr. 4450: job_title "Ansprechpartner" -> faelschlich
Rolle "partner" durch reinen Substring-Match). Fix: fuer "partner" allein
Wortgrenzen-Matching + explizite Kompositum-Allowlist statt reinem
Substring - die uebrigen Keywords bleiben bewusst Substring-Matches (siehe
Modul-Kommentar in sourcing.py, z.B. muss "steuerberater" weiterhin in
"Steuerberaterin" treffen).

Die eigentliche Ursache der 18 Titelschutz-Faelle war NICHT dieses Mapping
(0 Faelle stammten aus Sourcing) - trotzdem Regressionstests, dass die
geschuetzten Rollen (steuerberater/wirtschaftspruefer/rechtsanwalt) hier
weiterhin NICHT aus englischen Industriebezeichnungen ausgeloest werden."""

from cc_crm.services.sourcing import _rollen_from_text


class TestPartnerFalsePositiveFix:
    def test_ansprechpartner_does_not_trigger_partner(self) -> None:
        """Der genaue gemeldete Fall (Nr. 4450)."""
        assert "partner" not in _rollen_from_text("Ansprechpartner")

    def test_ansprechpartner_within_longer_title_does_not_trigger_partner(self) -> None:
        assert "partner" not in _rollen_from_text("Ihr Ansprechpartner für Steuerfragen")

    def test_equity_partner_still_triggers(self) -> None:
        assert "partner" in _rollen_from_text("Equity Partner")

    def test_seniorpartner_still_triggers(self) -> None:
        assert "partner" in _rollen_from_text("Seniorpartner")

    def test_juniorpartner_still_triggers(self) -> None:
        assert "partner" in _rollen_from_text("Juniorpartner")

    def test_sozius_still_triggers(self) -> None:
        assert "partner" in _rollen_from_text("Sozius")

    def test_sozia_still_triggers(self) -> None:
        assert "partner" in _rollen_from_text("Sozia")

    def test_standalone_partner_still_triggers(self) -> None:
        assert "partner" in _rollen_from_text("Partner")

    def test_partner_with_comma_separated_title_still_triggers(self) -> None:
        assert "partner" in _rollen_from_text("Partner, Wirtschaftsprüfer")


class TestSteuerberaterFeminineFormStillMatches:
    """Regressionsschutz: die Wortgrenzen-Korrektur betrifft NUR "partner" -
    "steuerberater" bleibt bewusst ein reiner Substring-Match, sonst wuerde
    die weibliche Form nicht mehr gefunden (siehe Modul-Kommentar in
    sourcing.py)."""

    def test_steuerberaterin_still_matches(self) -> None:
        assert "steuerberater" in _rollen_from_text("Steuerberaterin")

    def test_rechtsanwaeltin_still_matches(self) -> None:
        assert "rechtsanwalt" in _rollen_from_text("Rechtsanwältin")


class TestProtectedRolesIgnoreEnglishIndustryTitles:
    """Genau die englischen Industriebezeichnungen aus den 18 gemeldeten
    Titelschutz-Faellen - duerfen steuerberater/wirtschaftspruefer/
    rechtsanwalt NICHT ausloesen (Nutzer-Vorgabe explizit genannt)."""

    def test_tax_consultant_does_not_trigger_steuerberater(self) -> None:
        result = _rollen_from_text("Tax Consultant")
        assert "steuerberater" not in result

    def test_tax_manager_does_not_trigger_steuerberater(self) -> None:
        result = _rollen_from_text("Tax Manager")
        assert "steuerberater" not in result

    def test_tax_director_does_not_trigger_steuerberater(self) -> None:
        result = _rollen_from_text("Global Tax Director")
        assert "steuerberater" not in result

    def test_senior_associate_does_not_trigger_rechtsanwalt(self) -> None:
        result = _rollen_from_text("Senior Associate Tax and M&A Law")
        assert "rechtsanwalt" not in result

    def test_auditor_does_not_trigger_wirtschaftspruefer(self) -> None:
        result = _rollen_from_text("Tax Auditor/Consultant")
        assert "wirtschaftspruefer" not in result
