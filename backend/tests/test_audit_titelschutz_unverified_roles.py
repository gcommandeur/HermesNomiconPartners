"""Tests fuer scripts/audit_titelschutz_unverified_roles.py - READ-ONLY Audit
fuer Kandidaten mit steuerberater/wirtschaftspruefer/rechtsanwalt in "rollen"
ohne erkennbaren Beleg (Schritt 1 der Titelschutz-Korrektur: Beleg-Pruefung
verbreitert auf ausbildung_titel/qualification/job_title/examensnoten/
summary/cv_extraction_raw, plus Herkunfts-Ausweisung).

Grundregel der Allowlist (zweifach nach gemeldeten Zirkelschluessen
nachgeschaerft): nur Felder, die eine Qualifikation IM WORTLAUT DES CV
wiedergeben, zaehlen als Beleg. Eine vom Modell selbst erzeugte
Kategorisierung (rollen, berufliche_stationen[].rolle) zaehlt NIE als Beleg
fuer eine andere vom selben Modell erzeugte Kategorisierung - siehe
test_does_not_treat_own_rollen_list_in_cv_extraction_raw_as_evidence und
test_station_rolle_alone_is_not_evidence."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.sourcing_lead import SourcingLead
from scripts.archive import audit_titelschutz_unverified_roles as audit_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(audit_script, "SessionLocal", session_factory)


class TestAudit:
    def test_flags_role_without_evidence_anywhere(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="1",
                first_name="Anna",
                last_name="Muster",
                rollen=["steuerberater"],
                job_title="Tax Manager",
                qualification=None,
                ausbildung_titel=None,
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert len(rows) == 1
        assert rows[0]["candidate_number"] == "1"
        assert rows[0]["geschuetzte_rolle_ohne_beleg"] == "steuerberater"
        assert rows[0]["herkunft"] == "unbekannt"

    def test_does_not_flag_role_with_explicit_evidence_in_ausbildung_titel(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="2",
                first_name="Bernd",
                last_name="Beispiel",
                rollen=["steuerberater"],
                ausbildung_titel="Steuerberaterin seit 2014",
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert rows == []

    def test_does_not_flag_role_with_evidence_only_in_job_title(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """Sourcing-Kandidaten ohne CV: ausbildung_titel/qualification sind
        leer, aber job_title traegt den Titel direkt von der Kanzlei-
        Website ("Steuerberaterin") - das ist ein belastbarer Beleg, kein
        unbelegter Fall (vorher faelschlich als unbelegt gemeldet)."""
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="3",
                first_name="Clara",
                last_name="Sourced",
                rollen=["steuerberater"],
                job_title="Steuerberaterin",
                qualification=None,
                ausbildung_titel=None,
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert rows == []

    def test_station_rolle_alone_is_not_evidence(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """Regressionsschutz gegen den ZWEITEN gemeldeten Zirkelschluss (eine
        Ebene tiefer als der erste): berufliche_stationen[].rolle ist keine
        dokumentierte Qualifikation im Wortlaut des CV, sondern dieselbe
        Modell-Klassifikation wie das uebergeordnete "rollen"-Feld, nur pro
        Station statt insgesamt - erzeugt im selben Extraktionslauf, aus
        demselben Text. Zaehlt daher NICHT als Beleg, auch wenn mehrere
        Stationen "rolle": "steuerberater" tragen (genau der gemeldete Fall
        Nr. 1723/3170: englischer Jobtitel, aber Stationen-Rollen
        "steuerberater"), egal ob auf der Kandidaten-Spalte oder innerhalb
        von cv_extraction_raw."""
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="4",
                first_name="Dana",
                last_name="Station",
                rollen=["steuerberater"],
                job_title="Global Tax Director",
                berufliche_stationen=[
                    {
                        "kanzleityp": "Grosskanzlei",
                        "kanzleigroesse": "200+",
                        "dauer_jahre": 3,
                        "rolle": "steuerberater",
                    },
                    {
                        "kanzleityp": "Mittelstand",
                        "kanzleigroesse": "10-50",
                        "dauer_jahre": 1,
                        "rolle": "steuerberater",
                    },
                ],
                cv_extraction_raw={
                    "job_title": "Global Tax Director",
                    "berufliche_stationen": [
                        {
                            "kanzleityp": "Grosskanzlei",
                            "kanzleigroesse": "200+",
                            "dauer_jahre": 3,
                            "rolle": "steuerberater",
                        },
                    ],
                },
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert len(rows) == 1
        assert rows[0]["candidate_number"] == "4"
        assert rows[0]["geschuetzte_rolle_ohne_beleg"] == "steuerberater"

    def test_does_not_flag_role_with_evidence_only_in_summary(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="5",
                first_name="Elena",
                last_name="Summary",
                rollen=["wirtschaftspruefer"],
                job_title="Audit Director",
                summary="2019 Bestellung zum Wirtschaftspruefer, seither in leitender Funktion.",
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert rows == []

    def test_does_not_flag_role_with_evidence_only_in_cv_extraction_raw(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """Beleg steht im vollstaendigen Extraktions-JSON (z.B.
        erfahrungen_zusammenfassung), kam aber nicht in die einzelnen
        Kandidaten-Spalten - Schritt 1 durchsucht auch dieses Feld."""
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="6",
                first_name="Finn",
                last_name="Raw",
                rollen=["steuerberater"],
                job_title="Tax Director",
                cv_extraction_raw={
                    "erfahrungen_zusammenfassung": (
                        "Nach dem erfolgreichen Steuerberaterexamen 2016 wechselte er in die "
                        "Industrie."
                    ),
                    "some_other_field": None,
                },
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert rows == []

    def test_does_not_flag_roles_without_titelschutz_rule(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """bilanzbuchhalter/partner/etc. haben keine Titelschutz-Regel -
        werden nie auditiert, egal was in den durchsuchten Feldern steht."""
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="7",
                first_name="Carla",
                last_name="Muster",
                rollen=["bilanzbuchhalter"],
                ausbildung_titel=None,
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert rows == []

    def test_audit_writes_nothing_to_database(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """Explizites Read-Only-Verhalten: nach dem Audit ist der Kandidat
        unveraendert in der DB - kein rollen/ausbildung_titel-Update."""
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="8",
                first_name="Dirk",
                last_name="Muster",
                rollen=["wirtschaftspruefer"],
                job_title="Auditor",
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        audit_script.audit()

        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rollen == ["wirtschaftspruefer"]
        assert refreshed.job_title == "Auditor"

    def test_does_not_treat_own_rollen_list_in_cv_extraction_raw_as_evidence(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """Regressionsschutz gegen den gemeldeten Zirkelschluss: cv_extraction_raw
        enthaelt fast immer den Schluessel "rollen" mit demselben Wert wie
        candidate.rollen - das darf NIE als eigener Beleg fuer sich selbst
        gewertet werden. Genau der gemeldete Fall: job_title traegt einen
        englischen Industrietitel ("Tax Consultant"), rollen=["steuerberater"]
        taucht aber im rohen Extraktions-JSON auf."""
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="12",
                first_name="Jonas",
                last_name="Circular",
                rollen=["steuerberater"],
                job_title="Tax Consultant M&A Consultant",
                cv_extraction_raw={
                    "rollen": ["steuerberater"],
                    "job_title": "Tax Consultant M&A Consultant",
                    "current_employer_internal": "ABC Steuerberatungsgesellschaft mbH",
                },
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert len(rows) == 1
        assert rows[0]["candidate_number"] == "12"
        assert rows[0]["geschuetzte_rolle_ohne_beleg"] == "steuerberater"

    def test_does_not_treat_employer_name_as_evidence(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """"Steuerberatungsgesellschaft" als Arbeitgebername (current_employer_
        internal bzw. kanzleityp je Station) belegt nicht, dass die Person
        SELBST Steuerberater ist."""
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="13",
                first_name="Kira",
                last_name="Employer",
                rollen=["steuerberater"],
                job_title="Senior Consultant",
                current_employer_internal="XYZ Steuerberatungsgesellschaft mbH",
                berufliche_stationen=[
                    {
                        "kanzleityp": "Steuerberatungsgesellschaft",
                        "kanzleigroesse": "50-100",
                        "dauer_jahre": 2,
                        "rolle": None,
                    }
                ],
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert len(rows) == 1
        assert rows[0]["candidate_number"] == "13"

    def test_herkunft_cv_extraktion(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="9",
                first_name="Greta",
                last_name="Extracted",
                rollen=["steuerberater"],
                job_title="Tax Consultant",
                cv_extraction_raw={"job_title": "Tax Consultant"},
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()

        assert len(rows) == 1
        assert rows[0]["herkunft"] == "cv_extraktion"

    def test_herkunft_sourcing_uebernahme(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="10",
                first_name="Hannes",
                last_name="Sourced",
                rollen=["steuerberater"],
                job_title="Tax Manager",
            )
            session.add(candidate)
            session.flush()
            lead = SourcingLead(
                source_type="kanzlei_team_page",
                first_name="Hannes",
                last_name="Sourced",
                created_candidate_id=candidate.id,
            )
            session.add(lead)
            session.commit()

        rows = audit_script.audit()

        assert len(rows) == 1
        assert rows[0]["herkunft"] == "sourcing_uebernahme"

    def test_herkunft_both_cv_extraktion_and_sourcing(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="11",
                first_name="Ina",
                last_name="Both",
                rollen=["steuerberater"],
                job_title="Tax Manager",
                cv_extraction_raw={"job_title": "Tax Manager"},
            )
            session.add(candidate)
            session.flush()
            lead = SourcingLead(
                source_type="kanzlei_team_page",
                first_name="Ina",
                last_name="Both",
                created_candidate_id=candidate.id,
            )
            session.add(lead)
            session.commit()

        rows = audit_script.audit()

        assert len(rows) == 1
        assert rows[0]["herkunft"] == "cv_extraktion+sourcing_uebernahme"
