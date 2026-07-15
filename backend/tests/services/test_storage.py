import pytest

from cc_crm.services.storage import has_generic_filename


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
