"""Tests fuer scripts/backfill_edv_kenntnisse_aus_fachliche_schwerpunkte.py -
regelbasierte, kostenlose Trennung von Software-Nennungen aus
fachliche_schwerpunkte."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from scripts.archive import backfill_edv_kenntnisse_aus_fachliche_schwerpunkte as edv_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(edv_script, "SessionLocal", session_factory)


def _use_tmp_output_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        edv_script, "OUTPUT_PATH", tmp_path / "edv_kenntnisse_backfill_review.csv"
    )


class TestSplitSoftwareEntries:
    def test_moves_known_software_terms(self) -> None:
        remaining, moved = edv_script.split_software_entries(
            ["Umsatzsteuer", "DATEV", "Jahresabschluss", "SAP FI/CO"]
        )
        assert remaining == ["Umsatzsteuer", "Jahresabschluss"]
        assert moved == ["DATEV", "SAP FI/CO"]

    def test_is_case_insensitive(self) -> None:
        remaining, moved = edv_script.split_software_entries(["datev-Kenntnisse"])
        assert remaining == []
        assert moved == ["datev-Kenntnisse"]

    def test_word_boundary_avoids_false_positive_substring(self) -> None:
        """'Wortschatz' darf nicht wegen zufaelliger Substring-Ueberlappung
        mit einem Vokabeleintrag matchen (Regressionsschutz fuer den
        \\b-Wortgrenzen-Match)."""
        remaining, moved = edv_script.split_software_entries(["Vertragsrecht"])
        assert remaining == ["Vertragsrecht"]
        assert moved == []

    def test_no_software_terms_leaves_list_unchanged(self) -> None:
        remaining, moved = edv_script.split_software_entries(["Umsatzsteuer", "M&A"])
        assert remaining == ["Umsatzsteuer", "M&A"]
        assert moved == []

    def test_empty_list(self) -> None:
        assert edv_script.split_software_entries([]) == ([], [])


class TestCandidatesToCheck:
    def test_only_candidates_with_raw_are_included(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            with_raw = Candidate(
                first_name="A", last_name="A", cv_extraction_raw={"rollen": []}
            )
            without_raw = Candidate(first_name="B", last_name="B")
            session.add_all([with_raw, without_raw])
            session.commit()

            result = edv_script._candidates_to_check(session)

        assert [c.id for c in result] == [with_raw.id]


class TestBackfill:
    def test_apply_moves_entries_and_updates_raw(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                first_name="Max",
                last_name="Muster",
                fachliche_schwerpunkte=["Umsatzsteuer", "DATEV", "SAP"],
                cv_extraction_raw={
                    "fachliche_schwerpunkte": ["Umsatzsteuer", "DATEV", "SAP"],
                    "edv_kenntnisse": [],
                    "rollen": ["steuerberater"],
                },
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        stats = edv_script.backfill(
            apply=True, candidates=[session_factory().get(Candidate, candidate_id)]
        )

        assert stats["candidates_updated"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
            assert refreshed.fachliche_schwerpunkte == ["Umsatzsteuer"]
            assert refreshed.edv_kenntnisse == ["DATEV", "SAP"]
            assert refreshed.cv_extraction_raw["fachliche_schwerpunkte"] == ["Umsatzsteuer"]
            assert refreshed.cv_extraction_raw["edv_kenntnisse"] == ["DATEV", "SAP"]
            # rollen (unbeteiligtes Feld) im Rohergebnis bleibt unangetastet.
            assert refreshed.cv_extraction_raw["rollen"] == ["steuerberater"]

    def test_dry_run_writes_nothing(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                first_name="Max",
                last_name="Muster",
                fachliche_schwerpunkte=["DATEV"],
                cv_extraction_raw={"fachliche_schwerpunkte": ["DATEV"], "edv_kenntnisse": []},
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        stats = edv_script.backfill(
            apply=False, candidates=[session_factory().get(Candidate, candidate_id)]
        )

        assert stats["candidates_updated"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
            assert refreshed.fachliche_schwerpunkte == ["DATEV"]
            assert refreshed.edv_kenntnisse == []

    def test_candidate_with_edv_kenntnisse_already_set_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Verhindert eine wiederholte/doppelte Verschiebung bei erneutem
        Skriptlauf - z.B. ein Kandidat, der laengst per echtem LLM-Lauf
        (nach Einfuehrung von edv_kenntnisse) sauber getrennt wurde."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                first_name="Max",
                last_name="Muster",
                fachliche_schwerpunkte=["Umsatzsteuer"],
                edv_kenntnisse=["DATEV"],
                cv_extraction_raw={"rollen": []},
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        stats = edv_script.backfill(
            apply=True, candidates=[session_factory().get(Candidate, candidate_id)]
        )

        assert stats["skipped_edv_kenntnisse_already_set"] == 1
        assert stats["candidates_updated"] == 0

    def test_nothing_to_move_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                first_name="Max",
                last_name="Muster",
                fachliche_schwerpunkte=["Umsatzsteuer"],
                cv_extraction_raw={"rollen": []},
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        stats = edv_script.backfill(
            apply=True, candidates=[session_factory().get(Candidate, candidate_id)]
        )

        assert stats["skipped_nothing_to_move"] == 1
        assert stats["candidates_updated"] == 0


def test_write_review_csv_backs_up_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    output_path = tmp_path / "edv_kenntnisse_backfill_review.csv"
    output_path.write_text("alter,inhalt\n", encoding="utf-8-sig")
    monkeypatch.setattr(edv_script, "OUTPUT_PATH", output_path)

    edv_script._write_review_csv([])

    backups = list(tmp_path.glob("edv_kenntnisse_backfill_review_backup_*.csv"))
    assert len(backups) == 1
    assert output_path.exists()
