"""Tests fuer scripts/apply_titelschutz_unverified_flags.py - setzt
Candidate.rollen_unbestaetigt fuer die vom Audit gefundenen Faelle
(Konsolidierter Auftrag "Titelschutz-Korrektur ohne Datenverlust + Rollen-
Herkunft + Rechtsgebiete", Schritt 2)."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from scripts import apply_titelschutz_unverified_flags as script
from scripts import audit_titelschutz_unverified_roles as audit_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(script, "SessionLocal", session_factory)
    monkeypatch.setattr(audit_script, "SessionLocal", session_factory)


def _use_tmp_output_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        script, "OUTPUT_PATH", tmp_path / "apply_titelschutz_unverified_flags_review.csv"
    )


class TestApplyFlags:
    def test_dry_run_does_not_write(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="1",
                first_name="Anna",
                last_name="Muster",
                rollen=["steuerberater"],
                job_title="Tax Manager",
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        rows = audit_script.audit()
        stats = script.apply_flags(apply=False, rows=rows)

        assert stats["candidates_newly_flagged"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rollen_unbestaetigt is False

    def test_apply_flags_the_candidate_and_keeps_rollen_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="2",
                first_name="Bernd",
                last_name="Beispiel",
                rollen=["steuerberater"],
                job_title="Tax Consultant M&A Consultant",
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        rows = audit_script.audit()
        stats = script.apply_flags(apply=True, rows=rows)

        assert stats["candidates_newly_flagged"] == 1
        with session_factory() as session:
            refreshed = session.get(Candidate, candidate_id)
        assert refreshed.rollen_unbestaetigt is True
        # rollen selbst bleibt unangetastet - kein Datenverlust.
        assert refreshed.rollen == ["steuerberater"]

    def test_apply_writes_audit_log_entry(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="3",
                first_name="Carla",
                last_name="Muster",
                rollen=["rechtsanwalt"],
                job_title="Senior Associate",
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        rows = audit_script.audit()
        script.apply_flags(apply=True, rows=rows)

        with session_factory() as session:
            from sqlalchemy import select

            from cc_crm.models.recruiting import AuditLog

            entries = list(
                session.scalars(
                    select(AuditLog).where(
                        AuditLog.entity_type == "candidate",
                        AuditLog.entity_id == candidate_id,
                        AuditLog.action == "rollen_unbestaetigt_markiert",
                    )
                )
            )
        assert len(entries) == 1
        assert entries[0].changed_by is None
        assert entries[0].new_values["rollen_unbestaetigt"] is True

    def test_does_not_flag_or_log_a_candidate_with_evidence(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="4",
                first_name="Dirk",
                last_name="Muster",
                rollen=["steuerberater"],
                ausbildung_titel="Steuerberater seit 2014",
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()
        stats = script.apply_flags(apply=True, rows=rows)

        assert stats["candidates_checked"] == 0
        assert stats["candidates_newly_flagged"] == 0

    def test_already_flagged_candidate_is_skipped_and_not_logged_again(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        """Idempotenz - ein wiederholter Lauf (z.B. nach neuen Kandidaten)
        darf bereits markierte Faelle nicht erneut loggen."""
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="5",
                first_name="Elena",
                last_name="Beispiel",
                rollen=["steuerberater"],
                job_title="Tax Manager",
                rollen_unbestaetigt=True,
            )
            session.add(candidate)
            session.commit()
            candidate_id = candidate.id

        rows = audit_script.audit()
        stats = script.apply_flags(apply=True, rows=rows)

        assert stats["candidates_newly_flagged"] == 0
        assert stats["already_flagged"] == 1
        with session_factory() as session:
            from sqlalchemy import select

            from cc_crm.models.recruiting import AuditLog

            entries = list(
                session.scalars(
                    select(AuditLog).where(
                        AuditLog.entity_type == "candidate",
                        AuditLog.entity_id == candidate_id,
                    )
                )
            )
        assert entries == []

    def test_running_twice_is_idempotent(
        self, monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
    ) -> None:
        _use_session_factory(monkeypatch, session_factory)
        _use_tmp_output_path(monkeypatch, tmp_path)
        with session_factory() as session:
            candidate = Candidate(
                candidate_number="6",
                first_name="Finn",
                last_name="Beispiel",
                rollen=["wirtschaftspruefer"],
                job_title="Audit Director",
            )
            session.add(candidate)
            session.commit()

        rows = audit_script.audit()
        first_run = script.apply_flags(apply=True, rows=rows)
        rows_again = audit_script.audit()
        second_run = script.apply_flags(apply=True, rows=rows_again)

        assert first_run["candidates_newly_flagged"] == 1
        assert second_run["candidates_newly_flagged"] == 0
        assert second_run["already_flagged"] == 1
