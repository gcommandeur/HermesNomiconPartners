"""Tests fuer backfill_cv_rollen_und_schwerpunkte.py.

Schwerpunkte:
1. Ueberschreibungsbug-Regressionsschutz: die Zielfelder muessen UNABHAENGIG
   voneinander behandelt werden - liefert der Re-Parse fuer ein Feld keinen
   Vorschlag (leere Liste/None), muss der bestehende DB-Wert erhalten
   bleiben statt mit leer ueberschrieben zu werden.
2. Persistenz-Fix (2026-08-22): cv_extraction_raw wird SOFORT bei jedem
   erfolgreichen LLM-Ergebnis geschrieben, UNABHAENGIG von --apply - das ist
   jetzt der Checkpoint (ersetzt die fruehere lokale JSON-Datei, die einen
   DO-App-Platform-Container-Neustart nicht ueberlebte). Ein Kandidat mit
   bereits gesetztem cv_extraction_raw wird nie wieder per LLM verarbeitet.
3. Guthaben-Abbruch: eine Fallback-Begruendung mit "credit balance" bricht
   den GESAMTEN Lauf ab, statt sich durch alle restlichen Kandidaten zu
   versuchen; ein gewoehnlicher Fallback (Timeout o.ae.) bricht NICHT ab und
   wird einfach nicht gecacht."""

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
    """Isoliert Tests von der echten Review-CSV im Repo - ohne das wuerde
    jeder Testlauf, der backfill()/_write_review_csv aufruft, die reale
    Datei unter backend/scripts/ anfassen (siehe Vorfall: ein Sanity-Check-
    Lauf hat genau dort echte, bezahlte Extraktionsergebnisse ueberschrieben)."""
    monkeypatch.setattr(backfill_script, "OUTPUT_PATH", tmp_path / "cv_rollen_backfill_review.csv")


class TestFilterByCandidateNumbers:
    """Regressionsschutz fuers --candidate-numbers-Flag: eine handverlesene
    Test-Stichprobe (z.B. vor einem grossen Produktions-Lauf) muss GENAU
    diese Kandidaten treffen, in der angegebenen Reihenfolge, und unbekannte
    Nummern duerfen den Lauf nicht abbrechen."""

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


class TestNeedsProcessing:
    """_needs_processing() ist die neue Checkpoint-Grundlage: nur Kandidaten
    OHNE cv_extraction_raw gelten als zu bearbeiten."""

    def test_filters_out_candidates_with_existing_raw(self) -> None:
        already_done = Candidate(
            first_name="A", last_name="A", cv_extraction_raw={"rollen": ["steuerberater"]}
        )
        still_open = Candidate(first_name="B", last_name="B")

        result = backfill_script._needs_processing([already_done, still_open])

        assert result == [still_open]


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
            "edv_kenntnisse": [],
            "ausbildung_titel": None,
            "llm_fallback_used": False,
            **payload,
        },
    )


class TestApplyFieldIndependence:
    def test_apply_keeps_existing_value_when_field_has_no_new_suggestion(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Kernfall des Fixes: nur fachliche_schwerpunkte liefert diesmal
        einen Treffer, rollen kommt leer zurueck - das zuvor gesetzte rollen
        darf NICHT geloescht werden."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = _make_candidate_with_cv(
                session,
                rollen=["rechtsanwalt"],
                current_employer_internal="Alte Kanzlei GmbH",
                fachliche_schwerpunkte=[],
                edv_kenntnisse=["DATEV"],
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
        assert refreshed.edv_kenntnisse == ["DATEV"]

    def test_apply_overwrites_field_when_new_suggestion_present(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Liefert der Re-Parse fuer ein Feld etwas, ist der neue Wert
        autoritativ und ersetzt den alten - auch wenn der alte Wert etwas
        anderes war."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = _make_candidate_with_cv(session, rollen=["rechtsanwalt"])
            candidate_id = candidate.id
            _stub_extraction(
                monkeypatch,
                {"rollen": ["steuerberater", "partner"], "edv_kenntnisse": ["SAP FI/CO"]},
            )

            with session_factory() as inner_session:
                candidates = [inner_session.get(Candidate, candidate_id)]
            backfill_script.backfill(apply=True, candidates=candidates)

            refreshed = session.get(Candidate, candidate_id)
            session.refresh(refreshed)

        assert refreshed.rollen == ["steuerberater", "partner"]
        assert refreshed.edv_kenntnisse == ["SAP FI/CO"]

    def test_review_csv_row_marks_skipped_fields(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Die Review-CSV muss pro Kandidat sichtbar machen, welche Felder
        bei --apply erhalten blieben statt Diff gegen die DB fahren zu
        muessen."""
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
        assert "edv_kenntnisse" in row["felder_uebersprungen"]
        assert "fachliche_schwerpunkte" not in row["felder_uebersprungen"]
        assert row["rollen_vorschlag"] == "(behalten - kein neuer Vorschlag)"
        assert row["fachliche_schwerpunkte_vorschlag"] == "Erbrecht"


class TestPersistenceFix:
    """cv_extraction_raw ist seit dem Persistenz-Fix der Checkpoint - wird
    SOFORT bei jedem Erfolg geschrieben, UNABHAENGIG von --apply, und ein
    Kandidat mit bereits gesetztem cv_extraction_raw wird nie erneut per LLM
    verarbeitet."""

    def test_cv_extraction_raw_is_persisted_even_in_dry_run(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
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

        # Abgeleitete Spalte NICHT geschrieben (Dry-Run) ...
        assert refreshed.rollen == []
        # ... aber das Rohergebnis SCHON - das ist der eigentliche Checkpoint.
        assert refreshed.cv_extraction_raw is not None
        assert refreshed.cv_extraction_raw["rollen"] == ["steuerberater"]

    def test_candidate_with_existing_raw_triggers_no_llm_call(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = _make_candidate_with_cv(
                session, cv_extraction_raw={"rollen": ["steuerberater"]}
            )
            all_with_cv = backfill_script._candidates_with_cv(session)

        needs_processing = backfill_script._needs_processing(all_with_cv)

        assert candidate not in needs_processing
        assert needs_processing == []

    def test_interrupted_run_resumes_via_db_state_not_local_file(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Simuliert eine Unterbrechung nach 2 von 3 Kandidaten: ein
        'Neustart' fragt die Kandidatenliste erneut aus der DB ab (wie
        main() das tut) - die bereits erfolgreichen 2 tauchen dank
        cv_extraction_raw nicht mehr in der zu bearbeitenden Menge auf,
        ganz ohne lokale Datei."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            c1 = _make_candidate_with_cv(session, first_name="A")
            c2 = _make_candidate_with_cv(session, first_name="B")
            c3 = _make_candidate_with_cv(session, first_name="C")
            ids = [c1.id, c2.id, c3.id]

        monkeypatch.setattr(backfill_script, "read_document_bytes", lambda storage_key: b"dummy")
        monkeypatch.setattr(
            backfill_script, "extract_text_from_bytes", lambda filename, content: filename
        )
        calls: list[str] = []

        def _fake_extract(cv_text: str, **kwargs: object) -> dict[str, object]:
            calls.append(cv_text)
            return {
                "rollen": ["steuerberater"],
                "current_employer_internal": "Kanzlei X",
                "berufliche_stationen": [],
                "fachliche_schwerpunkte": [],
                "edv_kenntnisse": [],
                "ausbildung_titel": None,
                "llm_fallback_used": False,
            }

        monkeypatch.setattr(backfill_script, "extract_candidate_fields", _fake_extract)

        # "Lauf 1": nur die ersten 2 werden uebergeben (simuliert einen
        # Container-Neustart, der den Lauf nach 2 Kandidaten unterbricht).
        with session_factory() as session:
            first_run_candidates = [session.get(Candidate, cid) for cid in ids[:2]]
            stats_first = backfill_script.backfill(apply=True, candidates=first_run_candidates)
        assert stats_first["candidates_updated"] == 2
        assert len(calls) == 2

        # "Neustart": komplett neu aus der DB abgefragt, wie main() es tut -
        # KEINE lokale Datei im Spiel.
        with session_factory() as session:
            all_with_cv = backfill_script._candidates_with_cv(session)
            second_run_candidates = backfill_script._needs_processing(all_with_cv)
            assert len(second_run_candidates) == 1
            assert second_run_candidates[0].id == ids[2]
            stats_second = backfill_script.backfill(apply=True, candidates=second_run_candidates)

        assert stats_second["candidates_updated"] == 1
        # Insgesamt genau 3 LLM-Aufrufe ueber beide Laeufe - keine Dopplung.
        assert len(calls) == 3

        with session_factory() as session:
            for cid in ids:
                candidate = session.get(Candidate, cid)
                assert candidate.rollen == ["steuerberater"]
                assert candidate.current_employer_internal == "Kanzlei X"

    def test_ordinary_fallback_is_not_persisted_and_is_retried_on_resume(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Ein gewoehnlicher Fallback (Timeout, kein Guthaben-Problem) darf
        NICHT nach cv_extraction_raw geschrieben werden - der Kandidat bleibt
        in der 'noch zu bearbeiten'-Menge und wird beim naechsten Lauf
        automatisch per echtem LLM-Call neu versucht."""
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
                return {
                    "rollen": [],
                    "current_employer_internal": None,
                    "berufliche_stationen": [],
                    "fachliche_schwerpunkte": [],
                    "edv_kenntnisse": [],
                    "ausbildung_titel": None,
                    "llm_fallback_used": True,
                    "llm_fallback_reason": "Anthropic-API nicht erreichbar: Timeout",
                }
            return {
                "rollen": ["steuerberater"],
                "current_employer_internal": "Kanzlei X",
                "berufliche_stationen": [],
                "fachliche_schwerpunkte": [],
                "edv_kenntnisse": [],
                "ausbildung_titel": None,
                "llm_fallback_used": False,
            }

        monkeypatch.setattr(backfill_script, "extract_candidate_fields", _fake_extract)

        with session_factory() as session:
            first_stats = backfill_script.backfill(
                apply=True, candidates=[session.get(Candidate, candidate_id)]
            )
        assert first_stats["llm_fallback_not_cached"] == 1
        assert first_stats["candidates_updated"] == 0

        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
            assert refreshed.cv_extraction_raw is None
            all_with_cv = backfill_script._candidates_with_cv(session)
            second_run_candidates = backfill_script._needs_processing(all_with_cv)
            assert len(second_run_candidates) == 1
            second_stats = backfill_script.backfill(apply=True, candidates=second_run_candidates)

        assert second_stats["candidates_updated"] == 1
        assert call_count == 2

        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
            assert refreshed.rollen == ["steuerberater"]


class TestCreditExhaustedAbort:
    def test_credit_balance_reason_aborts_entire_run(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Kernfall aus der Praxis: mitten im Lauf geht das Anthropic-
        Guthaben aus - der GESAMTE Lauf muss abbrechen, nicht sich durch die
        restlichen Kandidaten fallback-versuchen."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            c1 = _make_candidate_with_cv(session, first_name="A")
            c2 = _make_candidate_with_cv(session, first_name="B")
            c3 = _make_candidate_with_cv(session, first_name="C")
            ids = [c1.id, c2.id, c3.id]

        monkeypatch.setattr(backfill_script, "read_document_bytes", lambda storage_key: b"dummy")
        monkeypatch.setattr(
            backfill_script, "extract_text_from_bytes", lambda filename, content: filename
        )
        call_count = 0

        def _fake_extract(cv_text: str, **kwargs: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return {
                    "rollen": [],
                    "current_employer_internal": None,
                    "berufliche_stationen": [],
                    "fachliche_schwerpunkte": [],
                    "edv_kenntnisse": [],
                    "ausbildung_titel": None,
                    "llm_fallback_used": True,
                    "llm_fallback_reason": (
                        "Anthropic-API antwortet mit Fehler 400: Your credit balance is "
                        "too low to access the Anthropic API."
                    ),
                }
            return {
                "rollen": ["steuerberater"],
                "current_employer_internal": "Kanzlei X",
                "berufliche_stationen": [],
                "fachliche_schwerpunkte": [],
                "edv_kenntnisse": [],
                "ausbildung_titel": None,
                "llm_fallback_used": False,
            }

        monkeypatch.setattr(backfill_script, "extract_candidate_fields", _fake_extract)

        with session_factory() as session:
            candidates = [session.get(Candidate, cid) for cid in ids]
            with pytest.raises(backfill_script.CreditExhaustedError, match="credit balance"):
                backfill_script.backfill(apply=True, candidates=candidates)

        # Nur der 3. Kandidat wurde ueberhaupt versucht (Lauf bricht ab,
        # bevor er ihn erreicht) - genau 2 LLM-Aufrufe insgesamt.
        assert call_count == 2

        with session_factory() as session:
            # Kandidat 1 (vor dem Abbruch erfolgreich) bleibt persistiert.
            first = session.get(Candidate, ids[0])
            assert first.cv_extraction_raw is not None
            assert first.rollen == ["steuerberater"]
            # Kandidat 2 (der Guthaben-Fallback) wurde NICHT gecacht.
            second = session.get(Candidate, ids[1])
            assert second.cv_extraction_raw is None
            # Kandidat 3 wurde gar nicht erst versucht.
            third = session.get(Candidate, ids[2])
            assert third.cv_extraction_raw is None


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


class TestRowLevelDataErrorHandling:
    """Punkt 4 des Konsolidierten Auftrags 'Fehlerbehebung Import': ein
    DataError (z.B. Wert zu lang fuer eine Spalte) beim Schreiben EINES
    Kandidaten darf den GESAMTEN Lauf nicht abstuerzen lassen - ohne
    session.rollback() waeren nach einem fehlgeschlagenen commit() ALLE
    nachfolgenden commits in derselben Session ebenfalls ungueltig (genau
    das war der gemeldete Absturz: 'value too long for type character
    varying(240)')."""

    def test_data_error_on_cv_extraction_raw_commit_skips_row_and_continues(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            c1 = _make_candidate_with_cv(session, first_name="A")
            c2 = _make_candidate_with_cv(session, first_name="B")
            ids = [c1.id, c2.id]
        _stub_extraction(monkeypatch, {"rollen": ["steuerberater"]})

        from sqlalchemy.exc import DataError
        from sqlalchemy.orm import Session as SASession

        original_commit = SASession.commit
        calls = {"n": 0}

        def flaky_commit(self: SASession) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise DataError(
                    "INSERT", {}, Exception("value too long for type character varying(240)")
                )
            original_commit(self)

        monkeypatch.setattr(SASession, "commit", flaky_commit)

        with session_factory() as session:
            candidates = [session.get(Candidate, cid) for cid in ids]
        stats = backfill_script.backfill(apply=True, candidates=candidates)

        # Der erste Kandidat (fehlgeschlagener commit) zaehlt als
        # uebersprungen, NICHT als Fehler, der den Lauf beendet - der zweite
        # Kandidat wird trotzdem noch verarbeitet.
        assert stats["candidates_checked"] == 2
        assert stats["skipped_data_error"] == 1
        assert stats["candidates_updated"] == 1

        with session_factory() as session:
            first = session.get(Candidate, ids[0])
            second = session.get(Candidate, ids[1])
        # rollback() greift: der fehlgeschlagene Schreibvorgang hinterlaesst
        # keine Halbdaten.
        assert first.cv_extraction_raw is None
        assert second.cv_extraction_raw is not None
        assert second.rollen == ["steuerberater"]

    def test_data_error_on_derived_columns_commit_keeps_raw_persisted(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Schlaegt NUR der zweite commit() (abgeleitete Spalten unter
        --apply) fehl, bleibt das bereits committete cv_extraction_raw aus
        dem ersten commit() trotzdem als Checkpoint erhalten - nur die
        abgeleiteten Spalten dieses einen Kandidaten gehen verloren."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = _make_candidate_with_cv(session)
            candidate_id = candidate.id
        _stub_extraction(monkeypatch, {"rollen": ["steuerberater"]})

        from sqlalchemy.exc import DataError
        from sqlalchemy.orm import Session as SASession

        original_commit = SASession.commit
        calls = {"n": 0}

        def flaky_commit(self: SASession) -> None:
            calls["n"] += 1
            if calls["n"] == 2:
                raise DataError("UPDATE", {}, Exception("value too long"))
            original_commit(self)

        monkeypatch.setattr(SASession, "commit", flaky_commit)

        with session_factory() as session:
            candidates = [session.get(Candidate, candidate_id)]
        stats = backfill_script.backfill(apply=True, candidates=candidates)

        assert stats["skipped_data_error"] == 1

        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        # Erster commit (cv_extraction_raw) war erfolgreich und bleibt
        # bestehen, auch wenn der zweite commit (abgeleitete Spalten)
        # fehlschlug.
        assert refreshed.cv_extraction_raw is not None
        assert refreshed.rollen == []


class TestConfirmBeforeRunning:
    def test_zero_candidates_skips_confirmation(self, capsys: pytest.CaptureFixture) -> None:
        assert backfill_script._confirm_before_running(0, skip_confirmation=False) is True

    def test_yes_flag_skips_interactive_prompt(self, capsys: pytest.CaptureFixture) -> None:
        # Kein input()-Aufruf noetig - wuerde in einem nohup-Lauf ohne
        # interaktives stdin sonst blockieren/crashen.
        assert backfill_script._confirm_before_running(5, skip_confirmation=True) is True
        assert "--yes gesetzt" in capsys.readouterr().out

    def test_declining_returns_false(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "n")
        assert backfill_script._confirm_before_running(5, skip_confirmation=False) is False

    def test_confirming_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", lambda _: "j")
        assert backfill_script._confirm_before_running(5, skip_confirmation=False) is True
