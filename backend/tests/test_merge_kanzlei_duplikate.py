"""Tests fuer scripts/merge_kanzlei_duplikate.py - Zusammenfuehren doppelter
ClientCompany-Datensaetze.

Schwerpunkt ist die kritische Nutzer-Vorgabe: eine bestehende Prozess-
Verknuepfung (CandidateSubmission.client_company_id) darf durch den Merge
NIEMALS verloren gehen oder ins Leere zeigen. Ohne das Umhaengen wuerde das
Loeschen des Losers je nach FK-Regel entweder blockieren (RESTRICT), Zeilen
still mitloeschen (CASCADE bei activities/contact_persons/notes/tasks) oder
sie verwaisen lassen (SET NULL) - deshalb wird hier jede dieser Kategorien
einzeln geprueft, inklusive der beiden weichen Referenzen ohne FK
(Document.owner_id mit owner_type="client" und MailingGroup.recipients)."""

import uuid

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.models.enums import ClientStatus
from cc_crm.models.mailing_group import MailingGroup
from cc_crm.models.note import Note
from cc_crm.models.operational import Document
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.task import Task
from scripts import merge_kanzlei_duplikate as script


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path):
    monkeypatch.setattr(script, "SessionLocal", session_factory)
    monkeypatch.setattr(script, "OUTPUT_PATH", tmp_path / "merge_kanzlei_duplikate_review.csv")
    # Die im Skript fest hinterlegten Produktivdaten sollen die Tests nicht
    # beeinflussen - jeder Test setzt sich seine eigenen Faelle auf.
    monkeypatch.setattr(script, "EXPLICIT_PAIRS", [])
    monkeypatch.setattr(script, "DOMAIN_ONLY_FIXES", [])


def _client(session: Session, name: str, **kwargs) -> ClientCompany:
    client = ClientCompany(name=name, **kwargs)
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


def _candidate(session: Session, last_name: str = "Muster") -> Candidate:
    candidate = Candidate(first_name="Anna", last_name=last_name)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


class TestKeeperAuswahl:
    def test_platzhaltername_verliert_gegen_echten_firmennamen(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Bei Gleichstand (0:0 Submissions) bleibt der echte Firmenname -
        der aus der Domain abgeleitete Platzhalter ("Alt Partner") wird
        per EXAKTEM Vergleich gegen derive_name_from_domain erkannt."""
        with session_factory() as session:
            _client(session, "Alt Partner", website="https://alt-partner.de")
            _client(session, "PKF Issing GmbH & Co. KG", website="https://alt-partner.de")

        script.run(apply=True)

        with session_factory() as session:
            names = [c.name for c in session.query(ClientCompany).all()]
        assert names == ["PKF Issing GmbH & Co. KG"]

    def test_meiste_submissions_gewinnt_auch_gegen_echten_namen(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Regel 1 (meiste Submissions) schlaegt Regel 2 (echter Name) -
        so geht garantiert die groesste Menge an Prozess-Historie nicht
        durch einen Umhaenge-Vorgang."""
        with session_factory() as session:
            platzhalter = _client(session, "Alt Partner", website="https://alt-partner.de")
            _client(session, "PKF Issing GmbH & Co. KG", website="https://alt-partner.de")
            candidate = _candidate(session)
            session.add(
                CandidateSubmission(
                    candidate_id=candidate.id, client_company_id=platzhalter.id
                )
            )
            session.commit()

        script.run(apply=True)

        with session_factory() as session:
            names = [c.name for c in session.query(ClientCompany).all()]
        assert names == ["Alt Partner"]


class TestKeineVerknuepfungGehtVerloren:
    def test_submission_zeigt_nach_merge_auf_keeper(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """DIE zentrale Zusicherung: der Prozess ueberlebt den Merge und
        haengt danach an der bleibenden Kanzlei.

        Der Keeper bekommt hier bewusst MEHR Submissions als der Loser,
        damit die Keeper-Wahl eindeutig ist (Regel 1) und trotzdem eine
        echte Submission umgehaengt werden muss."""
        with session_factory() as session:
            loser = _client(session, "Alt Partner", website="https://alt-partner.de")
            keeper = _client(
                session, "PKF Issing GmbH & Co. KG", website="https://alt-partner.de"
            )
            candidate = _candidate(session)
            session.add_all(
                [
                    CandidateSubmission(candidate_id=candidate.id, client_company_id=keeper.id),
                    CandidateSubmission(candidate_id=candidate.id, client_company_id=keeper.id),
                    CandidateSubmission(candidate_id=candidate.id, client_company_id=loser.id),
                ]
            )
            session.commit()
            loser_submission_id = (
                session.query(CandidateSubmission)
                .filter(CandidateSubmission.client_company_id == loser.id)
                .one()
                .id
            )

        script.run(apply=True)

        with session_factory() as session:
            keeper = session.query(ClientCompany).one()
            assert keeper.name == "PKF Issing GmbH & Co. KG"
            submissions = session.query(CandidateSubmission).all()
            assert len(submissions) == 3, "Kein Prozess darf verloren gehen"
            assert all(s.client_company_id == keeper.id for s in submissions)
            moved = session.get(CandidateSubmission, loser_submission_id)
            assert moved is not None, "Der Prozess des Losers muss erhalten bleiben"
            assert moved.client_company_id == keeper.id

    def test_cascade_tabellen_werden_umgehaengt_statt_mitgeloescht(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """activities/notes/tasks haengen per ON DELETE CASCADE am Loser -
        ohne Umhaengen waeren sie nach dem Loeschen still weg."""
        with session_factory() as session:
            loser = _client(session, "Alt Partner", website="https://alt-partner.de")
            _client(session, "PKF Issing GmbH & Co. KG", website="https://alt-partner.de")
            session.add(
                Activity(client_company_id=loser.id, activity_type="note", subject="Notiz")
            )
            session.add(Note(client_company_id=loser.id, body="wichtig"))
            session.add(Task(client_company_id=loser.id, title="nachfassen"))
            session.commit()

        script.run(apply=True)

        with session_factory() as session:
            keeper = session.query(ClientCompany).one()
            assert session.query(Activity).one().client_company_id == keeper.id
            assert session.query(Note).one().client_company_id == keeper.id
            assert session.query(Task).one().client_company_id == keeper.id

    def test_dokumente_werden_umgehaengt_obwohl_kein_fk_existiert(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Document.owner_id ist eine polymorphe Referenz OHNE FK - ein
        naiver Merge haette die Kanzlei-Dokumente (u.a. Vermittlungs-
        vertraege) unbemerkt ins Leere zeigen lassen."""
        with session_factory() as session:
            loser = _client(session, "Alt Partner", website="https://alt-partner.de")
            _client(session, "PKF Issing GmbH & Co. KG", website="https://alt-partner.de")
            session.add(
                Document(
                    owner_type="client",
                    owner_id=loser.id,
                    document_type="contract",
                    filename="Vermittlungsvertrag.pdf",
                    storage_key="client/x.pdf",
                )
            )
            session.commit()

        script.run(apply=True)

        with session_factory() as session:
            keeper = session.query(ClientCompany).one()
            assert session.query(Document).one().owner_id == keeper.id

    def test_mailing_group_json_referenz_wird_umgehaengt(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """MailingGroup.recipients ist eine JSON-Liste ohne FK."""
        with session_factory() as session:
            loser = _client(session, "Alt Partner", website="https://alt-partner.de")
            _client(session, "PKF Issing GmbH & Co. KG", website="https://alt-partner.de")
            session.add(
                MailingGroup(
                    name="Kampagne",
                    recipients=[
                        {"kind": "client", "id": str(loser.id), "name": "Alt Partner"},
                        {"kind": "candidate", "id": str(uuid.uuid4()), "name": "Anna"},
                    ],
                )
            )
            session.commit()

        script.run(apply=True)

        with session_factory() as session:
            keeper = session.query(ClientCompany).one()
            recipients = session.query(MailingGroup).one().recipients
            client_entries = [r for r in recipients if r["kind"] == "client"]
            assert client_entries[0]["id"] == str(keeper.id)
            assert len(recipients) == 2, "Andere Empfaenger bleiben unangetastet"


class TestKontakte:
    def test_kontakte_werden_umgehaengt_und_dubletten_verworfen(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            loser = _client(session, "Alt Partner", website="https://alt-partner.de")
            keeper = _client(
                session, "PKF Issing GmbH & Co. KG", website="https://alt-partner.de"
            )
            session.add(
                ContactPerson(
                    client_company_id=keeper.id,
                    first_name="Eva",
                    last_name="Keeper",
                    email="Info@alt-partner.de",
                )
            )
            session.add(
                ContactPerson(
                    client_company_id=loser.id,
                    first_name="Eva",
                    last_name="Dublette",
                    # Gleiche Adresse, andere Schreibweise -> muss als
                    # Dublette erkannt und verworfen werden.
                    email="info@alt-partner.de",
                )
            )
            session.add(
                ContactPerson(
                    client_company_id=loser.id,
                    first_name="Neu",
                    last_name="Person",
                    email="neu@alt-partner.de",
                )
            )
            session.commit()

        script.run(apply=True)

        with session_factory() as session:
            keeper = session.query(ClientCompany).one()
            contacts = session.query(ContactPerson).all()
            assert all(c.client_company_id == keeper.id for c in contacts)
            emails = sorted((c.email or "").lower() for c in contacts)
            assert emails == ["info@alt-partner.de", "neu@alt-partner.de"]


class TestFeldUebernahme:
    def test_leere_keeper_felder_werden_befuellt(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            _client(
                session,
                "Alt Partner",
                website="https://alt-partner.de",
                city="Heilbronn",
                phone="0711 123",
            )
            _client(session, "PKF Issing GmbH & Co. KG", email="karriere@alt-partner.de")

        script.run(apply=True)

        with session_factory() as session:
            keeper = session.query(ClientCompany).one()
            assert keeper.name == "PKF Issing GmbH & Co. KG"
            assert keeper.city == "Heilbronn"
            assert keeper.phone == "0711 123"
            assert keeper.website == "https://alt-partner.de"

    def test_nicht_leere_keeper_felder_werden_nie_ueberschrieben(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            _client(
                session,
                "Alt Partner",
                website="https://alt-partner.de",
                city="FALSCH",
                status=ClientStatus.PROSPECT,
            )
            _client(
                session,
                "PKF Issing GmbH & Co. KG",
                website="https://alt-partner.de",
                city="Heilbronn",
                status=ClientStatus.ACTIVE,
            )

        script.run(apply=True)

        with session_factory() as session:
            keeper = session.query(ClientCompany).one()
            assert keeper.city == "Heilbronn", "Nicht-leeres Feld darf nicht ueberschrieben werden"
            assert keeper.status == ClientStatus.ACTIVE
            assert keeper.website == "https://alt-partner.de"


class TestDryRun:
    def test_dry_run_schreibt_nichts(self, session_factory: sessionmaker[Session]) -> None:
        with session_factory() as session:
            loser = _client(session, "Alt Partner", website="https://alt-partner.de")
            keeper = _client(
                session, "PKF Issing GmbH & Co. KG", website="https://alt-partner.de"
            )
            candidate = _candidate(session)
            session.add_all(
                [
                    CandidateSubmission(candidate_id=candidate.id, client_company_id=keeper.id),
                    CandidateSubmission(candidate_id=candidate.id, client_company_id=keeper.id),
                    CandidateSubmission(candidate_id=candidate.id, client_company_id=loser.id),
                ]
            )
            session.commit()
            loser_id = loser.id

        stats, rows = script.run(apply=False)

        assert stats["pairs_domain"] == 1
        assert rows[0]["aktion"] == "WUERDE MERGEN"
        assert rows[0]["submissions_umgehaengt"] == 1
        with session_factory() as session:
            assert session.query(ClientCompany).count() == 2
            assert session.get(ClientCompany, loser_id) is not None
            still_at_loser = (
                session.query(CandidateSubmission)
                .filter(CandidateSubmission.client_company_id == loser_id)
                .count()
            )
            assert still_at_loser == 1, "Dry-Run darf nichts umhaengen"


class TestExplizitePaareUndDomainFix:
    def test_explizites_paar_wird_ueber_exakten_namen_gemergt(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        monkeypatch.setattr(script, "EXPLICIT_PAIRS", [("Echte Kanzlei mbB", "Platzhalter", None)])
        with session_factory() as session:
            _client(session, "Echte Kanzlei mbB")
            _client(session, "Platzhalter")

        stats, _ = script.run(apply=True)

        assert stats["pairs_explicit"] == 1
        with session_factory() as session:
            assert [c.name for c in session.query(ClientCompany).all()] == ["Echte Kanzlei mbB"]

    def test_explizites_paar_ohne_treffer_wird_uebersprungen(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """Exakter String-Vergleich, keine Aehnlichkeitsschwelle - ein nur
        aehnlicher Name darf NICHT gemergt werden."""
        monkeypatch.setattr(script, "EXPLICIT_PAIRS", [("Echte Kanzlei mbB", "Platzhalter", None)])
        with session_factory() as session:
            _client(session, "Echte Kanzlei mbB")
            _client(session, "Platzhalter GmbH")  # nur aehnlich, nicht identisch

        stats, rows = script.run(apply=True)

        assert stats["pairs_explicit"] == 0
        assert stats["skipped"] == 1
        assert "nicht gefunden" in str(rows[0]["aktion"])
        with session_factory() as session:
            assert session.query(ClientCompany).count() == 2

    def test_website_override_ueberschreibt_nicht_leere_keeper_website(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """Ausnahme von der generellen 'nie nicht-leere Felder
        ueberschreiben'-Regel: fuer die zwei am 30.07.2026 explizit
        bestaetigten Paare (Andreas Deubert, CMS Hasche Sigle) muss die
        bereits gesetzte, aber falsche Keeper-website zwangsweise durch die
        bestaetigte Domain ersetzt werden - auch wenn der Keeper schon eine
        andere, nicht-leere website hatte."""
        monkeypatch.setattr(
            script,
            "EXPLICIT_PAIRS",
            [("Echte Kanzlei mbB", "Platzhalter", "bestaetigte-domain.de")],
        )
        with session_factory() as session:
            _client(session, "Echte Kanzlei mbB", website="https://falsche-domain.de")
            _client(session, "Platzhalter", website="https://platzhalter-domain.de")

        stats, rows = script.run(apply=True)

        assert stats["pairs_explicit"] == 1
        assert rows[0]["aktion"] == "GEMERGT"
        assert "website" in str(rows[0]["felder_befuellt"])
        assert "falsche-domain.de" in str(rows[0]["felder_befuellt"])
        assert "bestaetigte-domain.de" in str(rows[0]["felder_befuellt"])
        with session_factory() as session:
            keeper = session.query(ClientCompany).one()
            assert keeper.name == "Echte Kanzlei mbB"
            assert keeper.website == "https://bestaetigte-domain.de"

    def test_website_override_dry_run_zeigt_geplante_aenderung_ohne_zu_schreiben(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        monkeypatch.setattr(
            script,
            "EXPLICIT_PAIRS",
            [("Echte Kanzlei mbB", "Platzhalter", "bestaetigte-domain.de")],
        )
        with session_factory() as session:
            _client(session, "Echte Kanzlei mbB", website="https://falsche-domain.de")
            _client(session, "Platzhalter")

        stats, rows = script.run(apply=False)

        assert stats["pairs_explicit"] == 1
        assert rows[0]["aktion"] == "WUERDE MERGEN"
        assert "bestaetigte-domain.de" in str(rows[0]["felder_befuellt"])
        with session_factory() as session:
            keeper = session.query(ClientCompany).filter_by(name="Echte Kanzlei mbB").one()
            assert keeper.website == "https://falsche-domain.de", "Dry-Run darf nichts schreiben"

    def test_domain_kollision_ueberschreibt_website_nie_auch_bei_abweichung(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Gegenprobe: bei der GENERISCHEN Domain-Kollision-Erkennung
        (Weg 1) gilt weiterhin die normale Regel - eine nicht-leere
        Keeper-website wird NIE ueberschrieben, website_override ist dort
        immer None."""
        with session_factory() as session:
            keeper = _client(
                session,
                "PKF Issing GmbH & Co. KG",
                website="https://alt-partner.de",
                email="info@alt-partner.de",
            )
            _client(
                session,
                "Alt Partner",
                website="https://alt-partner.de",
                email="andere-adresse@sonstwo.de",
            )
            original_website = keeper.website

        script.run(apply=True)

        with session_factory() as session:
            keeper = session.query(ClientCompany).one()
            assert keeper.website == original_website

    def test_domain_fix_ergaenzt_nur_leere_website(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        monkeypatch.setattr(script, "DOMAIN_ONLY_FIXES", [("Goetz & Partner mbB", "goetz.de")])
        with session_factory() as session:
            _client(session, "Goetz & Partner mbB")

        stats, _ = script.run(apply=True)

        assert stats["domain_only_fixed"] == 1
        with session_factory() as session:
            assert session.query(ClientCompany).one().website == "https://goetz.de"

    def test_domain_fix_ueberspringt_gesetzte_website(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        monkeypatch.setattr(script, "DOMAIN_ONLY_FIXES", [("Goetz & Partner mbB", "goetz.de")])
        with session_factory() as session:
            _client(session, "Goetz & Partner mbB", website="https://bereits-da.de")

        stats, rows = script.run(apply=True)

        assert stats["domain_only_fixed"] == 0
        assert "bereits gesetzt" in str(rows[0]["aktion"])
        with session_factory() as session:
            assert session.query(ClientCompany).one().website == "https://bereits-da.de"
