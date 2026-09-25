"""Tests fuer scripts/backfill_sourcing_candidates_structured_fields.py -
rueckwirkender Nachtrag fuer Kandidaten, die vor dem approve_lead()-Fix aus
einem SourcingLead uebernommen wurden."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import SourcingLeadStatus, SourcingSourceType
from cc_crm.models.sourcing_lead import SourcingLead
from scripts.archive import backfill_sourcing_candidates_structured_fields as backfill_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(backfill_script, "SessionLocal", session_factory)


def _use_tmp_output_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        backfill_script,
        "OUTPUT_PATH",
        tmp_path / "sourcing_candidates_structured_backfill_review.csv",
    )


def _make_approved_pair(
    session: Session, *, candidate_kwargs: dict[str, object] | None = None, **lead_overrides: object
) -> tuple[Candidate, SourcingLead]:
    candidate = Candidate(first_name="Erika", last_name="Beispiel", **(candidate_kwargs or {}))
    session.add(candidate)
    session.flush()
    lead_defaults: dict[str, object] = {
        "source_type": SourcingSourceType.STEUERBERATERVERZEICHNIS,
        "first_name": "Erika",
        "last_name": "Beispiel",
        "status": SourcingLeadStatus.APPROVED,
        "created_candidate_id": candidate.id,
    }
    lead_defaults.update(lead_overrides)
    lead = SourcingLead(**lead_defaults)
    session.add(lead)
    session.commit()
    return candidate, lead


class TestCandidateLeadSelection:
    def test_selects_only_approved_leads_with_created_candidate(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            approved, _ = _make_approved_pair(session)
            pending_candidate = Candidate(first_name="Nicht", last_name="Verknuepft")
            session.add(pending_candidate)
            session.commit()

            pairs = backfill_script._approved_candidate_lead_pairs(session)

        assert [c.id for c, _ in pairs] == [approved.id]


class TestApply:
    def test_fills_only_empty_fields_from_lead(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate, lead = _make_approved_pair(
                session,
                current_employer="Beispiel & Partner StBG",
                raw_data={"beruf": "Steuerberater(in)", "phone": "+49 30 1234567"},
            )
            candidate_id = candidate.id

            stats = backfill_script.backfill(apply=True, pairs=[(candidate, lead)])

            refreshed = session.get(Candidate, candidate_id)
            session.refresh(refreshed)

        assert stats["updated"] == 1
        assert refreshed.current_employer_internal == "Beispiel & Partner StBG"
        assert refreshed.job_title == "Steuerberater(in)"
        assert refreshed.rollen == ["steuerberater"]
        assert refreshed.phone == "+49 30 1234567"

    def test_never_overwrites_an_already_set_field(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate, lead = _make_approved_pair(
                session,
                candidate_kwargs={
                    "job_title": "Manuell korrigierter Titel",
                    "rollen": ["wirtschaftspruefer"],
                },
                current_employer="Beispiel & Partner StBG",
                raw_data={"beruf": "Steuerberater(in)"},
            )
            candidate_id = candidate.id

            backfill_script.backfill(apply=True, pairs=[(candidate, lead)])

            refreshed = session.get(Candidate, candidate_id)
            session.refresh(refreshed)

        assert refreshed.job_title == "Manuell korrigierter Titel"
        assert refreshed.rollen == ["wirtschaftspruefer"]
        # current_employer_internal war leer - darf trotzdem befuellt werden.
        assert refreshed.current_employer_internal == "Beispiel & Partner StBG"

    def test_no_usable_lead_data_counts_as_skipped(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate, lead = _make_approved_pair(session)

            stats = backfill_script.backfill(apply=True, pairs=[(candidate, lead)])

        assert stats["updated"] == 0
        assert stats["skipped"] == 1
        assert stats["errors"] == 0

    def test_dry_run_does_not_write_to_db(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate, lead = _make_approved_pair(
                session, current_employer="Beispiel & Partner StBG"
            )
            candidate_id = candidate.id

            backfill_script.backfill(apply=False, pairs=[(candidate, lead)])

            refreshed = session.get(Candidate, candidate_id)
            session.refresh(refreshed)

        assert refreshed.current_employer_internal is None
