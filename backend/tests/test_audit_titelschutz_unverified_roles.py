"""Tests fuer scripts/audit_titelschutz_unverified_roles.py - READ-ONLY Audit
fuer Kandidaten mit steuerberater/wirtschaftspruefer/rechtsanwalt in "rollen"
ohne erkennbaren Beleg in ausbildung_titel/qualification (Punkt 8c)."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from scripts import audit_titelschutz_unverified_roles as audit_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(audit_script, "SessionLocal", session_factory)


class TestAudit:
    def test_flags_role_without_evidence(
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

    def test_does_not_flag_role_with_explicit_evidence(
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

    def test_does_not_flag_roles_without_titelschutz_rule(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """bilanzbuchhalter/partner/etc. haben keine Titelschutz-Regel -
        werden nie auditiert, egal was in ausbildung_titel steht."""
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="3",
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
                candidate_number="4",
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
