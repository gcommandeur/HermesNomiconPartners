"""Tests fuer das endgueltige CC-Archiv-Loeschskript - decken die Faelle ab,
die bei einer unwiderruflichen Loeschung am wichtigsten sind: hartkodierte
Ausschluesse werden NIE geloescht, Drift seit dem Audit-Lauf (Name geaendert,
Submission neu hinzugekommen, Kandidat verschwunden) fuehrt zum Ueberspringen
statt zum Loeschen, und ein echter Treffer loescht sowohl die DB-Zeile als
auch das zugehoerige Storage-Objekt (S3/lokal)."""

import csv

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import SubmissionStatus
from cc_crm.models.operational import Document
from cc_crm.models.submission import CandidateSubmission
from scripts import delete_cc_archiv_altbestand as delete_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(delete_script, "SessionLocal", session_factory)


def _make_candidate_with_cv(session: Session, **overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "first_name": "Max",
        "last_name": "Muster",
        "candidate_number": "999",
    }
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.flush()
    session.add(
        Document(
            owner_type="candidate",
            owner_id=candidate.id,
            document_type="cv",
            filename="cv.pdf",
            storage_key=f"candidate/{candidate.id}/cv.pdf",
        )
    )
    session.commit()
    return candidate


def _csv_row(*, master_csv_id: str, first_name: str, last_name: str) -> dict[str, str]:
    return {
        "master_csv_id": master_csv_id,
        "csv_first_name": first_name,
        "csv_surname": last_name,
        "db_first_name": first_name,
        "db_last_name": last_name,
    }


def test_hard_excluded_id_is_never_deleted_even_if_row_says_ja(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _make_candidate_with_cv(
            session, candidate_number="1817", first_name="Christian", last_name="Schwarze"
        )
        row = _csv_row(master_csv_id="1817", first_name="Christian", last_name="Schwarze")

        log_row = delete_script.delete_candidate(session, row, apply=True)

        assert log_row["status"] == "uebersprungen"
        assert "ausgeschlossen" in log_row["grund"]
        remaining = session.scalar(select(Candidate).where(Candidate.candidate_number == "1817"))
        assert remaining is not None


def test_missing_candidate_is_skipped(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        row = _csv_row(master_csv_id="4200", first_name="Nicht", last_name="Vorhanden")
        log_row = delete_script.delete_candidate(session, row, apply=True)

    assert log_row["status"] == "uebersprungen"
    assert "nicht (mehr)" in log_row["grund"]


def test_name_drift_since_audit_is_skipped(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _make_candidate_with_cv(session, candidate_number="500", first_name="Alt", last_name="Name")
        row = _csv_row(master_csv_id="500", first_name="Neuer", last_name="Name")

        log_row = delete_script.delete_candidate(session, row, apply=True)

        assert log_row["status"] == "uebersprungen"
        assert "weicht" in log_row["grund"]
        remaining = session.scalar(select(Candidate).where(Candidate.candidate_number == "500"))
        assert remaining is not None


def test_new_submission_since_audit_blocks_deletion(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Kernfall: die Review-CSV kann Tage/Wochen alt sein - hat ein
    Kandidat inzwischen einen Prozess bekommen, darf trotz wuerde_geloescht=ja
    aus der alten CSV NICHT geloescht werden."""
    from cc_crm.models.client_company import ClientCompany

    with session_factory() as session:
        candidate = _make_candidate_with_cv(
            session, candidate_number="600", first_name="Neu", last_name="Prozess"
        )
        client = ClientCompany(name="Test-Kanzlei")
        session.add(client)
        session.flush()
        session.add(
            CandidateSubmission(
                candidate_id=candidate.id,
                client_company_id=client.id,
                status=SubmissionStatus.QUALIFICATION_CALL,
            )
        )
        session.commit()

        row = _csv_row(master_csv_id="600", first_name="Neu", last_name="Prozess")
        log_row = delete_script.delete_candidate(session, row, apply=True)

        assert log_row["status"] == "uebersprungen"
        assert "Submission" in log_row["grund"]
        remaining = session.scalar(select(Candidate).where(Candidate.candidate_number == "600"))
        assert remaining is not None


def test_apply_deletes_candidate_and_document(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    deleted_storage_keys: list[str] = []
    monkeypatch.setattr(
        delete_script,
        "delete_document_bytes",
        lambda storage_key: deleted_storage_keys.append(storage_key),
    )

    with session_factory() as session:
        candidate = _make_candidate_with_cv(
            session, candidate_number="700", first_name="Wird", last_name="Geloescht"
        )
        candidate_id = candidate.id
        expected_storage_key = f"candidate/{candidate_id}/cv.pdf"

        row = _csv_row(master_csv_id="700", first_name="Wird", last_name="Geloescht")
        log_row = delete_script.delete_candidate(session, row, apply=True)

        assert log_row["status"] == "geloescht"
        assert session.get(Candidate, candidate_id) is None
        assert session.scalar(select(Document).where(Document.owner_id == candidate_id)) is None
    assert deleted_storage_keys == [expected_storage_key]


def test_dry_run_deletes_nothing(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    def _fail_if_called(storage_key: str) -> None:
        pytest.fail("darf im Dry-Run nicht aufgerufen werden")

    monkeypatch.setattr(delete_script, "delete_document_bytes", _fail_if_called)

    with session_factory() as session:
        candidate = _make_candidate_with_cv(
            session, candidate_number="800", first_name="Bleibt", last_name="Stehen"
        )
        candidate_id = candidate.id

        row = _csv_row(master_csv_id="800", first_name="Bleibt", last_name="Stehen")
        log_row = delete_script.delete_candidate(session, row, apply=False)

        assert log_row["status"] == "wuerde_geloescht"
        assert session.get(Candidate, candidate_id) is not None


def test_env_payload_roundtrip_preserves_ja_row_data() -> None:
    """Kernfall des Produktions-Fallbacks: der gzip+base64-Payload muss nach
    dem Decode wieder eine per csv.DictReader lesbare CSV mit denselben
    Werten ergeben - die volle Review-CSV-Struktur (mehr Spalten als
    _ENV_PAYLOAD_FIELDS) darf dabei kein Problem sein."""
    full_rows = [
        {
            "master_csv_id": "193",
            "csv_first_name": "Thomas",
            "csv_surname": "Pollok",
            "db_first_name": "Thomas",
            "db_last_name": "Pollok",
            "document_storage_keys": "candidate/xyz/193_Pollok.pdf",
            "wuerde_geloescht": "ja",
        }
    ]

    payload = delete_script._build_env_payload(full_rows)
    decoded_csv_text = delete_script._decode_env_payload(payload)
    reconstructed_rows = list(csv.DictReader(decoded_csv_text.splitlines()))

    assert len(reconstructed_rows) == 1
    row = reconstructed_rows[0]
    assert row["master_csv_id"] == "193"
    assert row["csv_first_name"] == "Thomas"
    assert row["db_last_name"] == "Pollok"
    assert row["wuerde_geloescht"] == "ja"
    # Nicht in _ENV_PAYLOAD_FIELDS enthalten - bewusst nicht mitgenommen,
    # um den Payload klein zu halten.
    assert "document_storage_keys" not in row


def test_ensure_review_csv_available_reconstructs_from_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    missing_csv = tmp_path / "cc_archiv_deletion_review.csv"
    monkeypatch.setattr(delete_script, "REVIEW_CSV", missing_csv)
    payload = delete_script._build_env_payload(
        [
            {
                "master_csv_id": "700",
                "csv_first_name": "Wird",
                "csv_surname": "Rekonstruiert",
                "db_first_name": "Wird",
                "db_last_name": "Rekonstruiert",
                "wuerde_geloescht": "ja",
            }
        ]
    )
    monkeypatch.setenv(delete_script.REVIEW_CSV_ENV_VAR, payload)

    delete_script._ensure_review_csv_available()

    assert missing_csv.exists()
    rows = delete_script._load_rows_to_delete()
    assert len(rows) == 1
    assert rows[0]["master_csv_id"] == "700"


def test_ensure_review_csv_available_raises_without_file_or_env_var(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(delete_script, "REVIEW_CSV", tmp_path / "missing.csv")
    monkeypatch.delenv(delete_script.REVIEW_CSV_ENV_VAR, raising=False)

    with pytest.raises(SystemExit):
        delete_script._ensure_review_csv_available()


def test_run_reads_only_ja_rows_from_review_csv(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session], tmp_path
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    monkeypatch.setattr(delete_script, "delete_document_bytes", lambda storage_key: None)

    with session_factory() as session:
        _make_candidate_with_cv(
            session, candidate_number="900", first_name="Ja", last_name="Feld"
        )
        _make_candidate_with_cv(
            session, candidate_number="901", first_name="Nein", last_name="Feld"
        )

    review_csv = tmp_path / "review.csv"
    with review_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "master_csv_id",
                "csv_first_name",
                "csv_surname",
                "db_first_name",
                "db_last_name",
                "wuerde_geloescht",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "master_csv_id": "900",
                "csv_first_name": "Ja",
                "csv_surname": "Feld",
                "db_first_name": "Ja",
                "db_last_name": "Feld",
                "wuerde_geloescht": "ja",
            }
        )
        writer.writerow(
            {
                "master_csv_id": "901",
                "csv_first_name": "Nein",
                "csv_surname": "Feld",
                "db_first_name": "Nein",
                "db_last_name": "Feld",
                "wuerde_geloescht": "nein",
            }
        )
    monkeypatch.setattr(delete_script, "REVIEW_CSV", review_csv)
    monkeypatch.setattr(delete_script, "LOG_OUTPUT_PATH", tmp_path / "result.csv")

    stats = delete_script.run(apply=True)

    assert stats["total"] == 1
    assert stats["deleted"] == 1
    with session_factory() as session:
        deleted = session.scalar(select(Candidate).where(Candidate.candidate_number == "900"))
        kept = session.scalar(select(Candidate).where(Candidate.candidate_number == "901"))
        assert deleted is None
        assert kept is not None
