import pytest

from cc_crm.core.config import get_settings
from cc_crm.services import storage
from cc_crm.services.storage import cv_upload_filename, has_generic_filename, read_document_bytes


@pytest.mark.parametrize(
    "filename",
    [
        "resume.pdf",
        "Resume.PDF",
        "CV.docx",
        "cv1.pdf",
        "cv (2).pdf",
        "Bewerbung.pdf",
        "bewerbung (1).docx",
        "Lebenslauf.pdf",
        "lebenslauf1.pdf",
        "lebenslauf (3).pdf",
        "  cv  .pdf",
    ],
)
def test_generic_filenames_are_detected(filename: str) -> None:
    assert has_generic_filename(filename) is True


@pytest.mark.parametrize(
    "filename",
    [
        "lebenslauf-hans-mueller.pdf",
        "Lebenslauf_Hans_Mueller.pdf",
        "cv-erika-muster.docx",
        "Anschreiben.pdf",
        "Zeugnis.pdf",
        "resume_final_v2.pdf",
    ],
)
def test_non_generic_filenames_are_not_flagged(filename: str) -> None:
    assert has_generic_filename(filename) is False


class TestCvUploadFilename:
    """Dateibenennung fuer CVs (Konsolidierter Auftrag "Schnelle
    Submission"): CV_NACHNAME.VORNAME + Endung."""

    def test_basic_convention(self) -> None:
        assert (
            cv_upload_filename(
                first_name="Max", last_name="Mustermann", existing_cv_count=0, extension=".pdf"
            )
            == "CV_Mustermann.Max.pdf"
        )

    def test_extension_without_leading_dot_is_normalized(self) -> None:
        assert (
            cv_upload_filename(
                first_name="Max", last_name="Mustermann", existing_cv_count=0, extension="pdf"
            )
            == "CV_Mustermann.Max.pdf"
        )

    def test_umlauts_are_transliterated(self) -> None:
        assert (
            cv_upload_filename(
                first_name="Jürgen", last_name="Müller", existing_cv_count=0, extension=".docx"
            )
            == "CV_Mueller.Juergen.docx"
        )
        assert (
            cv_upload_filename(
                first_name="Katja", last_name="Groß", existing_cv_count=0, extension=".pdf"
            )
            == "CV_Gross.Katja.pdf"
        )

    def test_second_cv_gets_counter_suffix(self) -> None:
        assert (
            cv_upload_filename(
                first_name="Max", last_name="Mustermann", existing_cv_count=1, extension=".pdf"
            )
            == "CV_Mustermann.Max_2.pdf"
        )
        assert (
            cv_upload_filename(
                first_name="Max", last_name="Mustermann", existing_cv_count=2, extension=".pdf"
            )
            == "CV_Mustermann.Max_3.pdf"
        )

    def test_double_name_with_space_becomes_hyphenated(self) -> None:
        """Doppelnamen mit Leerzeichen (z.B. "von der Heide") werden NICHT
        abgeschnitten, sondern zu einem zusammenhaengenden, bindestrich-
        getrennten Namensteil."""
        assert (
            cv_upload_filename(
                first_name="Anna", last_name="von der Heide", existing_cv_count=0, extension=".pdf"
            )
            == "CV_von-der-Heide.Anna.pdf"
        )

    def test_existing_hyphenated_double_name_is_preserved(self) -> None:
        assert (
            cv_upload_filename(
                first_name="Max",
                last_name="Müller-Lüdenscheid",
                existing_cv_count=0,
                extension=".pdf",
            )
            == "CV_Mueller-Luedenscheid.Max.pdf"
        )

    def test_missing_name_falls_back_to_placeholder(self) -> None:
        assert (
            cv_upload_filename(first_name="", last_name="", existing_cv_count=0, extension=".pdf")
            == "CV_Unbekannt.Unbekannt.pdf"
        )


def test_read_document_bytes_translates_s3_no_such_key_to_file_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressionsschutz: live auf Produktion bestaetigt, dass ein Document
    mit einer DB-Zeile ohne zugehoeriges S3-Objekt (z.B. bei der SQLite->
    Postgres-Migration mitgenommene Zeile ohne echten Datei-Upload) mit
    botocore.errorfactory.NoSuchKey scheiterte - das lief als unbehandelte
    Exception bis zum globalen 500-Handler durch. profile_generator.py::
    _cv_text_for_candidate faengt bereits OSError um read_document_bytes() ab
    (faellt dann auf Quali-Call-Daten zurueck) - FileNotFoundError ist eine
    OSError-Subklasse, das S3-Backend muss also denselben Typ werfen wie das
    lokale Backend, nicht botocore's eigenen ClientError durchreichen."""
    from botocore.exceptions import ClientError

    class _FakeS3Client:
        def get_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject"
            )

    settings = get_settings()
    monkeypatch.setattr(settings, "s3_bucket", "test-bucket")
    monkeypatch.setattr(storage, "_s3_client", lambda: _FakeS3Client())

    with pytest.raises(FileNotFoundError):
        read_document_bytes("candidate/some-id/missing.pdf")
