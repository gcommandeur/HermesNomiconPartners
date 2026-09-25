"""Tests fuer scripts/backfill_rollen_from_cv_extraction_raw.py (Schritt 1
des CV-Reparse-Auftrags) - reiner JSON-zu-Spalte-Transfer aus bereits
vorhandenem Candidate.cv_extraction_raw, KEIN LLM-Call."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from scripts.archive import backfill_rollen_from_cv_extraction_raw as backfill_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(backfill_script, "SessionLocal", session_factory)


def _use_tmp_output_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        backfill_script, "OUTPUT_PATH", tmp_path / "cv_extraction_raw_backfill_review.csv"
    )


def _raw(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "rollen": ["steuerberater"],
        "current_employer_internal": "Kanzlei Muster GmbH",
        "berufliche_stationen": [
            {"kanzleityp": "Steuerkanzlei", "kanzleigroesse": "klein", "dauer_jahre": 2}
        ],
        "fachliche_schwerpunkte": ["Umsatzsteuer"],
    }
    defaults.update(overrides)
    return defaults


class TestCandidateSelection:
    def test_selects_only_candidates_with_raw_and_at_least_one_empty_target_field(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            complete = Candidate(
                first_name="A", last_name="A",
                cv_extraction_raw=_raw(),
                rollen=["steuerberater"], current_employer_internal="X",
                berufliche_stationen=[{"kanzleityp": "x", "kanzleigroesse": "y", "dauer_jahre": 1}],
                fachliche_schwerpunkte=["Y"],
            )
            gap = Candidate(first_name="B", last_name="B", cv_extraction_raw=_raw())
            no_raw = Candidate(first_name="C", last_name="C")
            session.add_all([complete, gap, no_raw])
            session.commit()

            result = backfill_script._candidates_with_raw_and_gap(session)

            names = {(c.first_name, c.last_name) for c in result}
            assert names == {("B", "B")}


class TestApply:
    def test_apply_fills_only_empty_fields_from_raw_json(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                first_name="Max", last_name="Muster",
                cv_extraction_raw=_raw(rollen=["rechtsanwalt", "partner"]),
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

            stats = backfill_script.backfill(apply=True, candidates=[candidate])

            refreshed = session.get(Candidate, candidate_id)
            session.refresh(refreshed)

        assert stats["updated"] == 1
        assert refreshed.rollen == ["rechtsanwalt", "partner"]
        assert refreshed.current_employer_internal == "Kanzlei Muster GmbH"
        assert refreshed.fachliche_schwerpunkte == ["Umsatzsteuer"]

    def test_apply_never_overwrites_an_already_set_field(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Kernregel: ein bereits gesetzter Wert (z.B. manuell korrigiert)
        darf NIE durch den Rohtext im JSON ersetzt werden, auch wenn dort
        etwas anderes steht."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                first_name="Max", last_name="Muster",
                rollen=["wirtschaftspruefer"],
                cv_extraction_raw=_raw(
                    rollen=["steuerberater"], fachliche_schwerpunkte=["Erbrecht"]
                ),
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

            backfill_script.backfill(apply=True, candidates=[candidate])

            refreshed = session.get(Candidate, candidate_id)
            session.refresh(refreshed)

        assert refreshed.rollen == ["wirtschaftspruefer"]
        assert refreshed.fachliche_schwerpunkte == ["Erbrecht"]

    def test_no_usable_data_in_raw_counts_as_skipped(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                first_name="Max", last_name="Muster",
                cv_extraction_raw={
                    "rollen": [],
                    "current_employer_internal": None,
                    "berufliche_stationen": [],
                    "fachliche_schwerpunkte": [],
                },
            )
            session.add(candidate)
            session.commit()

            stats = backfill_script.backfill(apply=True, candidates=[candidate])

        assert stats["updated"] == 0
        assert stats["skipped"] == 1
        assert stats["errors"] == 0

    def test_malformed_raw_is_a_row_level_error_not_fatal(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Row-Level-Fehlerbehandlung wie beim CSV-Import: ein kaputter
        Datensatz (hier: cv_extraction_raw ist kein Objekt) darf den Lauf
        nicht abbrechen und muss als Fehler gezaehlt werden, nicht stumm
        durchrutschen."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            broken = Candidate(
                first_name="Broken", last_name="Data", cv_extraction_raw=["not", "a", "dict"]
            )
            good = Candidate(first_name="Good", last_name="Data", cv_extraction_raw=_raw())
            session.add_all([broken, good])
            session.commit()

            stats = backfill_script.backfill(apply=True, candidates=[broken, good])

            session.refresh(good)

        assert stats["errors"] == 1
        assert stats["updated"] == 1
        # Die gute Zeile muss trotz des Fehlers bei der kaputten ueberlebt
        # haben (gleiches Muster wie beim mail_sync-Rollback-Regressionstest).
        assert good.rollen == ["steuerberater"]

    def test_dry_run_does_not_write_to_db(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(first_name="Max", last_name="Muster", cv_extraction_raw=_raw())
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

            backfill_script.backfill(apply=False, candidates=[candidate])

            refreshed = session.get(Candidate, candidate_id)
            session.refresh(refreshed)

        assert refreshed.rollen == []
        assert refreshed.current_employer_internal is None


class TestReviewCsvBackup:
    def test_write_review_csv_backs_up_existing_file_instead_of_overwriting(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        output_path = tmp_path / "cv_extraction_raw_backfill_review.csv"
        output_path.write_text("alter,inhalt\nmit,daten\n", encoding="utf-8-sig")
        monkeypatch.setattr(backfill_script, "OUTPUT_PATH", output_path)

        backfill_script._write_review_csv([])

        backups = list(tmp_path.glob("cv_extraction_raw_backfill_review_backup_*.csv"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8-sig") == "alter,inhalt\nmit,daten\n"
        assert output_path.exists()
        assert "alter,inhalt" not in output_path.read_text(encoding="utf-8-sig")
