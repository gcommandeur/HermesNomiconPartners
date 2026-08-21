"""Regressionstests fuer den Ueberschreibungsbug in backfill_cv_rollen_und_
schwerpunkte.py --apply: die 5 Zielfelder muessen UNABHAENGIG voneinander
behandelt werden - liefert der Re-Parse fuer ein Feld keinen Vorschlag (leere
Liste/None), muss der bestehende DB-Wert erhalten bleiben statt mit leer
ueberschrieben zu werden. Vorher wurde bei JEDEM Treffer (auch nur in einem
der 5 Felder) alles ausser ausbildung_titel bedingungslos ueberschrieben."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.operational import Document
from scripts import backfill_cv_rollen_und_schwerpunkte as backfill_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(backfill_script, "SessionLocal", session_factory)


def _use_tmp_output_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Isoliert Tests von der echten Review-CSV UND der echten Checkpoint-
    Datei im Repo - ohne das wuerde jeder Testlauf, der backfill()/
    _write_review_csv aufruft, die realen Dateien unter backend/scripts/
    anfassen (siehe Vorfall: ein Sanity-Check-Lauf hat genau dort echte,
    bezahlte Extraktionsergebnisse ueberschrieben)."""
    monkeypatch.setattr(backfill_script, "OUTPUT_PATH", tmp_path / "cv_rollen_backfill_review.csv")
    monkeypatch.setattr(
        backfill_script, "PROGRESS_PATH", tmp_path / "backfill_progress_cv_rollen.json"
    )


class TestFilterByCandidateNumbers:
    """Regressionsschutz fuers neue --candidate-numbers-Flag: eine
    handverlesene Test-Stichprobe (z.B. vor einem grossen Produktions-Lauf)
    muss GENAU diese Kandidaten treffen, in der angegebenen Reihenfolge,
    und unbekannte Nummern duerfen den Lauf nicht abbrechen."""

    def test_selects_exact_candidates_in_requested_order(self) -> None:
        c1 = Candidate(candidate_number="100", first_name="A", last_name="A")
        c2 = Candidate(candidate_number="200", first_name="B", last_name="B")
        c3 = Candidate(candidate_number="300", first_name="C", last_name="C")

        result = backfill_script._filter_by_candidate_numbers([c1, c2, c3], ["300", "100"])

        assert result == [c3, c1]

    def test_unknown_candidate_number_is_skipped_not_fatal(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        c1 = Candidate(candidate_number="100", first_name="A", last_name="A")

        result = backfill_script._filter_by_candidate_numbers([c1], ["100", "999"])

        assert result == [c1]
        assert "999" in capsys.readouterr().out


def _make_candidate_with_cv(session: Session, **overrides: object) -> Candidate:
    defaults: dict[str, object] = {"first_name": "Max", "last_name": "Muster"}
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.flush()
    session.add(
        Document(
            owner_type="candidate",
            owner_id=candidate.id,
            document_type="cv",
            filename="cv.docx",
            storage_key=f"candidates/{candidate.id}/cv.docx",
        )
    )
    session.commit()
    return candidate


def _stub_extraction(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object], *, cv_text: str = "CV-Inhalt"
) -> None:
    monkeypatch.setattr(backfill_script, "read_document_bytes", lambda storage_key: b"dummy")
    monkeypatch.setattr(
        backfill_script, "extract_text_from_bytes", lambda filename, content: cv_text
    )
    monkeypatch.setattr(
        backfill_script,
        "extract_candidate_fields",
        lambda cv_text, **kwargs: {
            "rollen": [],
            "current_employer_internal": None,
            "berufliche_stationen": [],
            "fachliche_schwerpunkte": [],
            "ausbildung_titel": None,
            **payload,
        },
    )


def test_apply_keeps_existing_value_when_field_has_no_new_suggestion(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
) -> None:
    """Kernfall des Fixes: nur fachliche_schwerpunkte liefert diesmal einen
    Treffer, rollen kommt leer zurueck - das zuvor gesetzte rollen darf NICHT
    geloescht werden."""
    _use_session_factory(monkeypatch, session_factory)
    _use_tmp_output_path(monkeypatch, tmp_path)
    with session_factory() as session:
        candidate = _make_candidate_with_cv(
            session,
            rollen=["rechtsanwalt"],
            current_employer_internal="Alte Kanzlei GmbH",
            fachliche_schwerpunkte=[],
        )
        candidate_id = candidate.id
        _stub_extraction(monkeypatch, {"fachliche_schwerpunkte": ["Erbrecht"]})

        with session_factory() as inner_session:
            candidates = [inner_session.get(Candidate, candidate_id)]
        stats = backfill_script.backfill(apply=True, candidates=candidates)

        refreshed = session.get(Candidate, candidate_id)
        session.refresh(refreshed)

    assert stats["candidates_updated"] == 1
    assert refreshed.rollen == ["rechtsanwalt"]
    assert refreshed.current_employer_internal == "Alte Kanzlei GmbH"
    assert refreshed.fachliche_schwerpunkte == ["Erbrecht"]


def test_apply_overwrites_field_when_new_suggestion_present(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
) -> None:
    """Liefert der Re-Parse fuer ein Feld etwas, ist der neue Wert
    autoritativ und ersetzt den alten - auch wenn der alte Wert etwas
    anderes war."""
    _use_session_factory(monkeypatch, session_factory)
    _use_tmp_output_path(monkeypatch, tmp_path)
    with session_factory() as session:
        candidate = _make_candidate_with_cv(session, rollen=["rechtsanwalt"])
        candidate_id = candidate.id
        _stub_extraction(monkeypatch, {"rollen": ["steuerberater", "partner"]})

        with session_factory() as inner_session:
            candidates = [inner_session.get(Candidate, candidate_id)]
        backfill_script.backfill(apply=True, candidates=candidates)

        refreshed = session.get(Candidate, candidate_id)
        session.refresh(refreshed)

    assert refreshed.rollen == ["steuerberater", "partner"]


def test_review_csv_row_marks_skipped_fields(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
) -> None:
    """Die Review-CSV muss pro Kandidat sichtbar machen, welche Felder bei
    --apply erhalten blieben statt Diff gegen die DB fahren zu muessen."""
    _use_session_factory(monkeypatch, session_factory)
    _use_tmp_output_path(monkeypatch, tmp_path)
    with session_factory() as session:
        candidate = _make_candidate_with_cv(session, rollen=["rechtsanwalt"])
        candidate_id = candidate.id
        _stub_extraction(monkeypatch, {"fachliche_schwerpunkte": ["Erbrecht"]})

        with session_factory() as inner_session:
            candidates = [inner_session.get(Candidate, candidate_id)]

        rows: list[dict[str, object]] = []
        original_write = backfill_script._write_review_csv
        monkeypatch.setattr(
            backfill_script, "_write_review_csv", lambda r: rows.extend(r) or original_write(r)
        )

        backfill_script.backfill(apply=False, candidates=candidates)

    assert len(rows) == 1
    row = rows[0]
    assert "rollen" in row["felder_uebersprungen"]
    assert "fachliche_schwerpunkte" not in row["felder_uebersprungen"]
    assert row["rollen_vorschlag"] == "(behalten - kein neuer Vorschlag)"
    assert row["fachliche_schwerpunkte_vorschlag"] == "Erbrecht"


def test_dry_run_does_not_write_to_db(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    _use_tmp_output_path(monkeypatch, tmp_path)
    with session_factory() as session:
        candidate = _make_candidate_with_cv(session, rollen=[])
        candidate_id = candidate.id
        _stub_extraction(monkeypatch, {"rollen": ["steuerberater"]})

        with session_factory() as inner_session:
            candidates = [inner_session.get(Candidate, candidate_id)]
        backfill_script.backfill(apply=False, candidates=candidates)

        refreshed = session.get(Candidate, candidate_id)
        session.refresh(refreshed)

    assert refreshed.rollen == []


class TestCheckpointResume:
    """Checkpoint/Resume (siehe Modul-Docstring von backfill_cv_rollen_und_
    schwerpunkte.py): ein Neustart nach einer Unterbrechung darf fuer
    bereits erfolgreich verarbeitete Kandidaten KEINEN erneuten (bezahlten)
    LLM-Call ausloesen."""

    def test_second_run_does_not_reextract_already_processed_candidates(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Simuliert eine Unterbrechung nach 2 von 3 Kandidaten: erster Lauf
        bekommt nur die ersten 2, zweiter Lauf (nach dem 'Neustart') bekommt
        alle 3 - der LLM-Stub darf ueber BEIDE Laeufe hinweg nur 3x
        aufgerufen werden, nicht 2+3=5x."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            c1 = _make_candidate_with_cv(session, first_name="A")
            c2 = _make_candidate_with_cv(session, first_name="B")
            c3 = _make_candidate_with_cv(session, first_name="C")
            ids = [c1.id, c2.id, c3.id]

        # cv_text pro Kandidat unterschiedlich, damit die Aufrufliste
        # nachvollziehbar bleibt, WELCHER Kandidat extrahiert wurde.
        monkeypatch.setattr(backfill_script, "read_document_bytes", lambda storage_key: b"dummy")
        monkeypatch.setattr(
            backfill_script,
            "extract_text_from_bytes",
            lambda filename, content: filename,
        )
        calls: list[str] = []

        def _fake_extract(cv_text: str, **kwargs: object) -> dict[str, object]:
            calls.append(cv_text)
            return {
                "rollen": ["steuerberater"],
                "current_employer_internal": "Kanzlei X",
                "berufliche_stationen": [],
                "fachliche_schwerpunkte": [],
                "ausbildung_titel": None,
            }

        monkeypatch.setattr(backfill_script, "extract_candidate_fields", _fake_extract)

        with session_factory() as session:
            first_run_candidates = [session.get(Candidate, cid) for cid in ids[:2]]
            stats_first = backfill_script.backfill(apply=True, candidates=first_run_candidates)

        assert stats_first["candidates_updated"] == 2
        assert len(calls) == 2

        # "Neustart": zweiter backfill()-Aufruf mit ALLEN 3 Kandidaten -
        # als eigenstaendiger Prozess laedt er den Checkpoint frisch von
        # der Platte, genau wie nach einem echten Container-Neustart.
        with session_factory() as session:
            second_run_candidates = [session.get(Candidate, cid) for cid in ids]
            stats_second = backfill_script.backfill(apply=True, candidates=second_run_candidates)

        assert stats_second["resumed_from_cache"] == 2
        assert stats_second["candidates_updated"] == 3
        # Insgesamt genau 3 LLM-Aufrufe ueber beide Laeufe - keine Dopplung.
        assert len(calls) == 3

        with session_factory() as session:
            for cid in ids:
                candidate = session.get(Candidate, cid)
                assert candidate.rollen == ["steuerberater"]
                assert candidate.current_employer_internal == "Kanzlei X"

    def test_progress_is_persisted_after_each_candidate_not_only_at_the_end(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Der zweite Kandidat scheitert - der ERSTE muss trotzdem schon in
        der Checkpoint-Datei stehen (synchrones Schreiben nach jedem
        Kandidaten, nicht erst im finally-Block am Ende des ganzen Laufs)."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            c1 = _make_candidate_with_cv(session, first_name="A")
            c2 = _make_candidate_with_cv(session, first_name="B")
            ids = [c1.id, c2.id]

        monkeypatch.setattr(backfill_script, "read_document_bytes", lambda storage_key: b"dummy")
        monkeypatch.setattr(
            backfill_script, "extract_text_from_bytes", lambda filename, content: "CV-Inhalt"
        )
        call_count = 0

        def _fake_extract(cv_text: str, **kwargs: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("API-Guthaben leer")
            return {
                "rollen": ["steuerberater"],
                "current_employer_internal": None,
                "berufliche_stationen": [],
                "fachliche_schwerpunkte": [],
                "ausbildung_titel": None,
            }

        monkeypatch.setattr(backfill_script, "extract_candidate_fields", _fake_extract)

        with session_factory() as session:
            candidates = [session.get(Candidate, cid) for cid in ids]
            stats = backfill_script.backfill(apply=True, candidates=candidates)

        assert stats["errors"] == 1
        progress = backfill_script._load_progress()
        assert str(ids[0]) in progress
        assert str(ids[1]) not in progress

    def test_failed_candidate_is_retried_on_resume_not_permanently_skipped(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = _make_candidate_with_cv(session)
            candidate_id = candidate.id

        monkeypatch.setattr(backfill_script, "read_document_bytes", lambda storage_key: b"dummy")
        monkeypatch.setattr(
            backfill_script, "extract_text_from_bytes", lambda filename, content: "CV-Inhalt"
        )
        call_count = 0

        def _fake_extract(cv_text: str, **kwargs: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Timeout")
            return {
                "rollen": ["steuerberater"],
                "current_employer_internal": None,
                "berufliche_stationen": [],
                "fachliche_schwerpunkte": [],
                "ausbildung_titel": None,
            }

        monkeypatch.setattr(backfill_script, "extract_candidate_fields", _fake_extract)

        with session_factory() as session:
            first_stats = backfill_script.backfill(
                apply=True, candidates=[session.get(Candidate, candidate_id)]
            )
        assert first_stats["errors"] == 1

        with session_factory() as session:
            second_stats = backfill_script.backfill(
                apply=True, candidates=[session.get(Candidate, candidate_id)]
            )
        assert second_stats["errors"] == 0
        assert second_stats["resumed_from_cache"] == 0
        assert second_stats["candidates_updated"] == 1
        assert call_count == 2

    def test_load_progress_survives_a_corrupted_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Eine kaputte/halb geschriebene Checkpoint-Datei darf den Lauf
        nicht blockieren - im Zweifel lieber ohne Cache neu starten."""
        progress_path = tmp_path / "backfill_progress_cv_rollen.json"
        progress_path.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(backfill_script, "PROGRESS_PATH", progress_path)

        assert backfill_script._load_progress() == {}


def test_write_review_csv_backs_up_existing_file_instead_of_overwriting(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Regressionsschutz: ein bereits vorhandener Lauf mit echten, bezahlten
    Extraktionsergebnissen darf nie stillschweigend durch einen kleineren
    Folgelauf (z.B. einen Sanity-Check mit --limit 2) ersetzt werden - siehe
    Vorfall, bei dem genau das eine vollstaendige 1124-Zeilen-CSV zerstoert
    hat, ohne dass irgendwo eine Kopie der bezahlten Ergebnisse blieb."""
    output_path = tmp_path / "cv_rollen_backfill_review.csv"
    output_path.write_text("alter,inhalt\nmit,1124zeilen\n", encoding="utf-8-sig")
    monkeypatch.setattr(backfill_script, "OUTPUT_PATH", output_path)

    backfill_script._write_review_csv([])

    backups = list(tmp_path.glob("cv_rollen_backfill_review_backup_*.csv"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8-sig") == "alter,inhalt\nmit,1124zeilen\n"
    # Neue (hier leere) Datei liegt weiterhin unter dem urspruenglichen Pfad.
    assert output_path.exists()
    assert "alter,inhalt" not in output_path.read_text(encoding="utf-8-sig")
