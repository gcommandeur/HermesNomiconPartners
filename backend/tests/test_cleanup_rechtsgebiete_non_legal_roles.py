"""Tests fuer scripts/cleanup_rechtsgebiete_non_legal_roles.py - Bereinigung
bestehender rechtsgebiete-Eintraege bei Kandidaten ohne juristische Rolle
(Konsolidierter Auftrag "Titelschutz-Korrektur ohne Datenverlust + Rollen-
Herkunft + Rechtsgebiete", Schritt 4). KEIN LLM-Call."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from scripts import cleanup_rechtsgebiete_non_legal_roles as script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(script, "SessionLocal", session_factory)


def _use_tmp_output_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        script, "OUTPUT_PATH", tmp_path / "cleanup_rechtsgebiete_non_legal_roles_review.csv"
    )


class TestCandidatesToCheck:
    def test_finds_non_legal_role_with_rechtsgebiete_set(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            session.add(
                Candidate(
                    candidate_number="1",
                    first_name="Anna",
                    last_name="Muster",
                    rollen=["steuerberater"],
                    rechtsgebiete=["steuerrecht"],
                )
            )
            session.commit()

        with session_factory() as session:
            result = script._candidates_to_check(session)
        assert len(result) == 1
        assert result[0].candidate_number == "1"

    def test_ignores_legal_role_even_with_rechtsgebiete_set(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            session.add(
                Candidate(
                    candidate_number="2",
                    first_name="Bernd",
                    last_name="Beispiel",
                    rollen=["rechtsanwalt"],
                    rechtsgebiete=["arbeitsrecht"],
                )
            )
            session.commit()

        with session_factory() as session:
            result = script._candidates_to_check(session)
        assert result == []

    def test_ignores_non_legal_role_with_empty_rechtsgebiete(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            session.add(
                Candidate(
                    candidate_number="3",
                    first_name="Carla",
                    last_name="Muster",
                    rollen=["steuerberater"],
                    rechtsgebiete=[],
                )
            )
            session.commit()

        with session_factory() as session:
            result = script._candidates_to_check(session)
        assert result == []

    def test_finds_candidate_with_no_rollen_at_all(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
    ) -> None:
        """Keine Rolle gesetzt zaehlt auch als "keine juristische Rolle"."""
        _use_session_factory(monkeypatch, session_factory)
        with session_factory() as session:
            session.add(
                Candidate(
                    candidate_number="4",
                    first_name="Dirk",
                    last_name="Muster",
                    rollen=[],
                    rechtsgebiete=["steuerrecht"],
                )
            )
            session.commit()

        with session_factory() as session:
            result = script._candidates_to_check(session)
        assert len(result) == 1


class TestCleanupApply:
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
                rollen=["steuerberater"],
                rechtsgebiete=["steuerrecht"],
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        stats = script.cleanup(apply=False, candidates=candidates)

        assert stats["candidates_updated"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rechtsgebiete == ["steuerrecht"]

    def test_apply_clears_rechtsgebiete_for_non_legal_role(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="6",
                first_name="Finn",
                last_name="Beispiel",
                rollen=["steuerberater"],
                rechtsgebiete=["steuerrecht"],
                cv_extraction_raw={"rechtsgebiete": ["steuerrecht"], "job_title": "Tax Manager"},
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        stats = script.cleanup(apply=True, candidates=candidates)

        assert stats["candidates_updated"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rechtsgebiete == []
        # cv_extraction_raw wird konsistent mitgezogen, andere Schluessel
        # bleiben unangetastet.
        assert refreshed.cv_extraction_raw["rechtsgebiete"] == []
        assert refreshed.cv_extraction_raw["job_title"] == "Tax Manager"

    def test_apply_leaves_fachliche_schwerpunkte_untouched(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Die fachliche Einordnung geht nicht verloren - sie steht bereits
        redundant in fachliche_schwerpunkte (Nutzer-Vorgabe: "unkritisch,
        weil die Information redundant vorliegt")."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="7",
                first_name="Greta",
                last_name="Beispiel",
                rollen=["steuerberater"],
                rechtsgebiete=["steuerrecht"],
                fachliche_schwerpunkte=["Steuerrecht", "Umsatzsteuer"],
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        script.cleanup(apply=True, candidates=candidates)

        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.fachliche_schwerpunkte == ["Steuerrecht", "Umsatzsteuer"]

    def test_apply_does_not_touch_legal_role_candidates(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="8",
                first_name="Hannes",
                last_name="Beispiel",
                rollen=["rechtsanwalt"],
                rechtsgebiete=["arbeitsrecht"],
            )
            session.add(candidate)
            session.commit()

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        stats = script.cleanup(apply=True, candidates=candidates)

        assert stats["candidates_checked"] == 0
        assert stats["candidates_updated"] == 0
