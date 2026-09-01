"""Tests fuer scripts/backfill_ausbildung_kuerzung_abschluesse_rechtsgebiete.py
- rueckwirkende, rein regelbasierte Kuerzung von ausbildung_titel/
qualification PLUS Ableitung von abschluesse/rechtsgebiete fuer bereits
verarbeitete Kandidaten (Punkte 6/7b/8a). KEIN LLM-Call."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from scripts import backfill_ausbildung_kuerzung_abschluesse_rechtsgebiete as script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(script, "SessionLocal", session_factory)


def _use_tmp_output_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        script,
        "OUTPUT_PATH",
        tmp_path / "ausbildung_kuerzung_abschluesse_rechtsgebiete_review.csv",
    )


class TestBackfillApply:
    def test_shortens_ausbildung_titel_and_derives_abschluesse(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="1",
                first_name="Anna",
                last_name="Muster",
                ausbildung_titel=(
                    "Steuerberaterin (Bestellung 19.05.2009); Ausbildung zur "
                    "Steuerfachangestellten (2000)"
                ),
                cv_extraction_raw={"ausbildung_titel": "irrelevant"},
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
        assert (
            refreshed.ausbildung_titel
            == "Steuerberaterin; Ausbildung zur Steuerfachangestellten"
        )
        assert "berufsexamen_stb" in refreshed.abschluesse
        assert "ausbildung" in refreshed.abschluesse
        # cv_extraction_raw wird konsistent mitgezogen.
        assert refreshed.cv_extraction_raw["ausbildung_titel"] == refreshed.ausbildung_titel

    def test_derives_rechtsgebiete_from_fachliche_schwerpunkte(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """rollen=["rechtsanwalt"] (Schritt 4 der Titelschutz-Korrektur:
        rechtsgebiete wird nur bei einer juristischen Rolle abgeleitet -
        ohne das waere das Ergebnis jetzt korrekt leer, siehe
        test_drops_rechtsgebiete_for_non_legal_role unten)."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="1",
                first_name="Anna",
                last_name="Muster",
                rollen=["rechtsanwalt"],
                fachliche_schwerpunkte=["Arbeitsrecht", "Vertragsrecht"],
                cv_extraction_raw={"fachliche_schwerpunkte": ["Arbeitsrecht", "Vertragsrecht"]},
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        script.backfill(apply=True, candidates=candidates)

        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rechtsgebiete == ["arbeitsrecht", "vertragsrecht"]

    def test_drops_rechtsgebiete_for_non_legal_role(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Schritt 4 der Titelschutz-Korrektur: genau der Bug, der den
        urspruenglichen Lauf dieses Skripts bei fast jedem Steuerberater
        "Steuerrecht" eintragen liess - rechtsgebiete bleibt jetzt leer ohne
        rechtsanwalt/rechtsfachangestellte in rollen."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="2",
                first_name="Bernd",
                last_name="Beispiel",
                rollen=["steuerberater"],
                fachliche_schwerpunkte=["Steuerrecht"],
                cv_extraction_raw={"fachliche_schwerpunkte": ["Steuerrecht"]},
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        script.backfill(apply=True, candidates=candidates)

        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rechtsgebiete == []

    def test_does_not_overwrite_already_set_abschluesse_or_rechtsgebiete(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Ein bereits gesetzter Wert (z.B. echtes LLM-Ergebnis nach
        Einfuehrung der Felder) ist autoritativ und wird NIE ueberschrieben."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="1",
                first_name="Anna",
                last_name="Muster",
                fachliche_schwerpunkte=["Arbeitsrecht"],
                abschluesse=["fortbildung"],
                rechtsgebiete=["steuerrecht"],
                cv_extraction_raw={"rollen": []},
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        script.backfill(apply=True, candidates=candidates)

        with session_factory() as verify_session:
            refreshed = verify_session.get(Candidate, candidate_id)
        assert refreshed.abschluesse == ["fortbildung"]
        assert refreshed.rechtsgebiete == ["steuerrecht"]

    def test_idempotent_second_run_reports_no_change(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="1",
                first_name="Anna",
                last_name="Muster",
                ausbildung_titel="Steuerberaterin (Bestellung 2009)",
                cv_extraction_raw={"ausbildung_titel": "irrelevant"},
            )
            session.add(candidate)
            session.commit()

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        first_stats = script.backfill(apply=True, candidates=candidates)
        assert first_stats["candidates_updated"] == 1

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        second_stats = script.backfill(apply=True, candidates=candidates)

        assert second_stats["candidates_updated"] == 0
        assert second_stats["skipped_no_change"] == 1

    def test_dry_run_writes_nothing(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="1",
                first_name="Anna",
                last_name="Muster",
                ausbildung_titel="Steuerberaterin (Bestellung 2009)",
                cv_extraction_raw={"ausbildung_titel": "irrelevant"},
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
        assert refreshed.ausbildung_titel == "Steuerberaterin (Bestellung 2009)"


class TestRowLevelDataErrorHandling:
    def test_data_error_on_one_row_does_not_abort_remaining_rows(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            broken = Candidate(
                candidate_number="1",
                first_name="Broken",
                last_name="Row",
                ausbildung_titel="Steuerberaterin (Bestellung 2009)",
                cv_extraction_raw={"ausbildung_titel": "irrelevant"},
            )
            good = Candidate(
                candidate_number="2",
                first_name="Good",
                last_name="Row",
                ausbildung_titel="WP-Examen (2018)",
                cv_extraction_raw={"ausbildung_titel": "irrelevant"},
            )
            session.add_all([broken, good])
            session.commit()
            broken_id, good_id = broken.id, good.id

        from sqlalchemy.exc import DataError
        from sqlalchemy.orm import Session as SASession

        original_commit = SASession.commit
        calls = {"n": 0}

        def flaky_commit(self: SASession) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise DataError("UPDATE", {}, Exception("value too long"))
            original_commit(self)

        monkeypatch.setattr(SASession, "commit", flaky_commit)

        with session_factory() as session:
            candidates = script._candidates_to_check(session)
        stats = script.backfill(apply=True, candidates=candidates)

        assert stats["skipped_data_error"] == 1
        assert stats["candidates_updated"] == 1

        with session_factory() as session:
            broken_refreshed = session.get(Candidate, broken_id)
            good_refreshed = session.get(Candidate, good_id)
        assert broken_refreshed.ausbildung_titel == "Steuerberaterin (Bestellung 2009)"
        assert good_refreshed.ausbildung_titel == "WP-Examen"
