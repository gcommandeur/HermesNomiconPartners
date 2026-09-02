"""Tests fuer scripts/backfill_rollen_from_job_title.py - einmaliges
Nachziehen von rollen fuer bereits verarbeitete Kandidaten mit gefuelltem
job_title/qualification, aber leerem rollen (Zwischenthema "Rolle fehlt bei
gefuelltem Jobtitel"). KEIN LLM-Call."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from scripts import backfill_rollen_from_job_title as script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(script, "SessionLocal", session_factory)


def _use_tmp_output_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        script, "OUTPUT_PATH", tmp_path / "backfill_rollen_from_job_title_review.csv"
    )


class TestCandidatesToCheck:
    def test_finds_candidate_with_job_title_and_empty_rollen(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            session.add(
                Candidate(
                    candidate_number="1",
                    first_name="Anna",
                    last_name="Muster",
                    job_title="Steuerberater",
                    rollen=[],
                )
            )
            session.commit()

        with session_factory() as session:
            result = script._candidates_to_check(session)
        assert len(result) == 1

    def test_ignores_candidate_with_rollen_already_set(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            session.add(
                Candidate(
                    candidate_number="2",
                    first_name="Bernd",
                    last_name="Beispiel",
                    job_title="Steuerberater",
                    rollen=["partner"],
                )
            )
            session.commit()

        with session_factory() as session:
            result = script._candidates_to_check(session)
        assert result == []

    def test_ignores_candidate_without_job_title_or_qualification(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            session.add(Candidate(candidate_number="3", first_name="Carla", last_name="Muster"))
            session.commit()

        with session_factory() as session:
            result = script._candidates_to_check(session)
        assert result == []

    def test_finds_candidate_via_qualification_only(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            session.add(
                Candidate(
                    candidate_number="4",
                    first_name="Dirk",
                    last_name="Muster",
                    qualification="Bilanzbuchhalter",
                    rollen=[],
                )
            )
            session.commit()

        with session_factory() as session:
            result = script._candidates_to_check(session)
        assert len(result) == 1


class TestBackfillApply:
    def test_dry_run_does_not_write(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="5",
                first_name="Elena",
                last_name="Beispiel",
                job_title="Steuerberater",
                rollen=[],
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        stats = script.backfill(apply=False, candidates=candidates)

        assert stats["candidates_updated"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rollen == []

    def test_apply_sets_derived_rollen(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="6",
                first_name="Finn",
                last_name="Beispiel",
                job_title="Bilanzbuchhalterin",
                rollen=[],
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        stats = script.backfill(apply=True, candidates=candidates)

        assert stats["candidates_updated"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rollen == ["bilanzbuchhalter"]

    def test_no_keyword_match_is_skipped_and_stays_empty(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Konservativ: englischer Industrietitel bleibt unangetastet, kein
        Fehler dieses Skripts."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="7",
                first_name="Greta",
                last_name="Beispiel",
                job_title="Tax Manager",
                rollen=[],
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        stats = script.backfill(apply=True, candidates=candidates)

        assert stats["candidates_updated"] == 0
        assert stats["skipped_no_keyword_match"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rollen == []

    def test_titelschutz_safety_still_applies_in_backfill(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Nutzer-Beispiel Nr. 3586 "Fachangestelle Steuerberater" -
        bekommt steuerfachangestellte, NICHT das geschuetzte steuerberater."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="8",
                first_name="Hannes",
                last_name="Beispiel",
                job_title="Fachangestelle Steuerberater",
                rollen=[],
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        script.backfill(apply=True, candidates=candidates)

        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rollen == ["steuerfachangestellte"]
