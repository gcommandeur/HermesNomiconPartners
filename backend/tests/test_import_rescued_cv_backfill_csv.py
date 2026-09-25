"""Tests fuer scripts/import_rescued_cv_backfill_csv.py - importiert die
geretteten Ergebnisse eines fruehen, nie persistierten Backfill-Laufs aus
einer CSV. KEIN LLM-Call, reiner CSV-zu-Spalte-Transfer."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from scripts.archive import import_rescued_cv_backfill_csv as import_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(import_script, "SessionLocal", session_factory)


def _use_tmp_output_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        import_script, "OUTPUT_PATH", tmp_path / "rescued_cv_backfill_import_review.csv"
    )


def _row(candidate_id: str, **overrides: str) -> dict[str, str]:
    defaults: dict[str, str] = {
        "candidate_number": "4330",
        "candidate_id": candidate_id,
        "job_title_zur_orientierung": "Steuerberaterin",
        "rollen_aktuell": "",
        "rollen_vorschlag": "steuerberater",
        "current_employer_internal_aktuell": "",
        "current_employer_internal_vorschlag": "Kanzlei Muster GmbH",
        "berufliche_stationen_vorschlag": (
            '[{"kanzleityp": "Steuerkanzlei", "kanzleigroesse": "klein", '
            '"dauer_jahre": 2, "rolle": "steuerberater"}]'
        ),
        "fachliche_schwerpunkte_aktuell": "",
        "fachliche_schwerpunkte_vorschlag": "Umsatzsteuer, Jahresabschluss",
        "ausbildung_titel_aktuell": "",
        "ausbildung_titel_vorschlag": "Steuerberaterprüfung 2019",
        "confidence": "high",
        "source_is_agency_profile": "False",
        "felder_uebersprungen": "",
        "error": "",
    }
    defaults.update(overrides)
    return defaults


class TestParsingHelpers:
    def test_parse_list_field_splits_on_comma(self) -> None:
        assert import_script._parse_list_field("Umsatzsteuer, Jahresabschluss") == [
            "Umsatzsteuer",
            "Jahresabschluss",
        ]

    def test_parse_list_field_treats_marker_and_empty_as_no_value(self) -> None:
        assert import_script._parse_list_field("") == []
        assert import_script._parse_list_field(import_script.NO_SUGGESTION_MARKER) == []

    def test_parse_optional_field_treats_marker_and_empty_as_none(self) -> None:
        assert import_script._parse_optional_field("") is None
        assert import_script._parse_optional_field(import_script.NO_SUGGESTION_MARKER) is None
        assert import_script._parse_optional_field("Kanzlei X") == "Kanzlei X"

    def test_parse_stationen_field_parses_json(self) -> None:
        result = import_script._parse_stationen_field('[{"kanzleityp": "x"}]')
        assert result == [{"kanzleityp": "x"}]

    def test_parse_stationen_field_rejects_non_array_json(self) -> None:
        with pytest.raises(ValueError, match="JSON-Array"):
            import_script._parse_stationen_field('{"not": "a list"}')


class TestImportRows:
    def test_apply_writes_derived_columns_and_raw(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(candidate_number="4330", first_name="Anna", last_name="Muster")
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        stats = import_script.import_rows(apply=True, rows=[_row(str(candidate_id))])

        assert stats["imported"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
            assert refreshed.rollen == ["steuerberater"]
            assert refreshed.current_employer_internal == "Kanzlei Muster GmbH"
            assert refreshed.fachliche_schwerpunkte == ["Umsatzsteuer", "Jahresabschluss"]
            assert refreshed.ausbildung_titel == "Steuerberaterprüfung 2019"
            assert refreshed.cv_extraction_raw is not None
            assert refreshed.cv_extraction_raw["rollen"] == ["steuerberater"]

    def test_dry_run_writes_nothing(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(candidate_number="4330", first_name="Anna", last_name="Muster")
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        stats = import_script.import_rows(apply=False, rows=[_row(str(candidate_id))])

        assert stats["imported"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
            assert refreshed.rollen == []
            assert refreshed.cv_extraction_raw is None

    def test_row_with_error_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Die 458 Guthaben-Fallback-/16 leere-CV-/2 defekte-PDF-Zeilen haben
        ein gesetztes error-Feld - fuer die gibt es keinen verwertbaren
        Vorschlag."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(candidate_number="4330", first_name="Anna", last_name="Muster")
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        stats = import_script.import_rows(
            apply=True,
            rows=[_row(str(candidate_id), error="LLM-Fallback: credit balance is too low")],
        )

        assert stats["imported"] == 0
        assert stats["skipped_row_had_error"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
            assert refreshed.cv_extraction_raw is None

    def test_unknown_candidate_id_is_skipped_not_fatal(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)

        stats = import_script.import_rows(
            apply=True, rows=[_row("00000000-0000-0000-0000-000000000000")]
        )

        assert stats["imported"] == 0
        assert stats["skipped_candidate_not_found_or_already_done"] == 1

    def test_candidate_with_existing_raw_is_skipped_idempotently(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Ein erneuter Lauf des Import-Skripts (z.B. nach einem
        Teilabbruch) darf einen bereits importierten Kandidaten nicht
        nochmal anfassen."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="4330",
                first_name="Anna",
                last_name="Muster",
                cv_extraction_raw={"rollen": ["steuerberater"]},
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        stats = import_script.import_rows(apply=True, rows=[_row(str(candidate_id))])

        assert stats["imported"] == 0
        assert stats["skipped_candidate_not_found_or_already_done"] == 1

    def test_field_independence_keeps_existing_value_when_no_suggestion(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="4330",
                first_name="Anna",
                last_name="Muster",
                current_employer_internal="Bestehende Kanzlei",
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        import_script.import_rows(
            apply=True,
            rows=[
                _row(
                    str(candidate_id),
                    current_employer_internal_vorschlag=import_script.NO_SUGGESTION_MARKER,
                )
            ],
        )

        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
            assert refreshed.current_employer_internal == "Bestehende Kanzlei"
            assert refreshed.rollen == ["steuerberater"]

    def test_malformed_stationen_json_is_a_row_level_failure_not_fatal(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            broken = Candidate(candidate_number="1", first_name="Broken", last_name="Row")
            good = Candidate(candidate_number="2", first_name="Good", last_name="Row")
            session.add_all([broken, good])
            session.commit()
            broken_id, good_id = broken.id, good.id

        stats = import_script.import_rows(
            apply=True,
            rows=[
                _row(str(broken_id), berufliche_stationen_vorschlag="{not valid json"),
                _row(str(good_id)),
            ],
        )

        assert stats["failed"] == 1
        assert stats["imported"] == 1
        with session_factory() as session:
            good_refreshed = session.get(Candidate, good_id)
            assert good_refreshed.rollen == ["steuerberater"]


class TestRowLevelDataErrorHandling:
    """Punkt 4 des Konsolidierten Auftrags 'Fehlerbehebung Import': ein
    DataError beim Schreiben EINER Zeile (z.B. Wert zu lang) darf den Import
    der restlichen Zeilen nicht abbrechen - erfordert session.rollback(),
    sonst schlagen alle nachfolgenden commits in derselben Session ebenfalls
    fehl."""

    def test_data_error_on_one_row_does_not_abort_remaining_rows(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            broken = Candidate(candidate_number="1", first_name="Broken", last_name="Row")
            good = Candidate(candidate_number="2", first_name="Good", last_name="Row")
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

        stats = import_script.import_rows(
            apply=True, rows=[_row(str(broken_id)), _row(str(good_id))]
        )

        assert stats["skipped_data_error"] == 1
        assert stats["imported"] == 1
        with session_factory() as session:
            broken_refreshed = session.get(Candidate, broken_id)
            good_refreshed = session.get(Candidate, good_id)
        assert broken_refreshed.cv_extraction_raw is None
        assert good_refreshed.cv_extraction_raw is not None
        assert good_refreshed.rollen == ["steuerberater"]


def test_write_review_csv_backs_up_existing_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    output_path = tmp_path / "rescued_cv_backfill_import_review.csv"
    output_path.write_text("alter,inhalt\n", encoding="utf-8-sig")
    monkeypatch.setattr(import_script, "OUTPUT_PATH", output_path)

    import_script._write_review_csv([])

    backups = list(tmp_path.glob("rescued_cv_backfill_import_review_backup_*.csv"))
    assert len(backups) == 1
    assert output_path.exists()
