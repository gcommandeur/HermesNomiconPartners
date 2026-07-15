import importlib.util
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "convert_linkedin_export", SCRIPTS_DIR / "convert_linkedin_export.py"
)
assert _spec is not None and _spec.loader is not None
convert_linkedin_export = importlib.util.module_from_spec(_spec)
sys.modules["convert_linkedin_export"] = convert_linkedin_export
_spec.loader.exec_module(convert_linkedin_export)


SAMPLE_EXPORT = """Notes:
"When exporting your connection data, some fields may be missing."


First Name,Last Name,URL,Email Address,Company,Position,Connected On
Anna,Beispiel,https://www.linkedin.com/in/anna,anna@example.com,Kanzlei Weber,Steuerberater/in,01 Jan 2026
Tom,Mustermann,https://www.linkedin.com/in/tom,,Audit Partners Muenchen,Wirtschaftspruefer/in,15 Feb 2026
,NoFirstName,https://www.linkedin.com/in/x,x@example.com,Nowhere,Nobody,01 Jan 2026
"""


def test_convert_maps_and_skips_incomplete_rows(tmp_path: Path) -> None:
    source = tmp_path / "Connections.csv"
    source.write_text(SAMPLE_EXPORT, encoding="utf-8")
    target = tmp_path / "candidates_ready.csv"

    count = convert_linkedin_export.convert(source, target)

    assert count == 2
    content = target.read_text(encoding="utf-8-sig")
    assert "Anna,Beispiel,anna@example.com" in content
    assert "NoFirstName" not in content


def test_find_header_row_skips_leading_notes() -> None:
    lines = SAMPLE_EXPORT.splitlines()
    index = convert_linkedin_export.find_header_row(lines)
    assert lines[index].startswith("First Name")
