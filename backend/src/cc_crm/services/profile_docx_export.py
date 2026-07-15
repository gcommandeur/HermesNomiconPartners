"""Renders the saved (LLM-generated, consultant-reviewed) anonymised profile
text into the real Commandeur Consulting Word letterhead (logo, navy header
bar) as a downloadable .docx.

Design choice: this renders exactly what is stored in `candidate.short_profile`
- the same text the consultant sees and can edit in the "Anonymes Profil"
textarea before saving - rather than re-deriving content from raw candidate
fields. That keeps the on-screen preview and the exported Word document in
sync and lets the consultant fix a wording issue before export without
touching code.

The master template (backend/templates/anonymes_profil_master.docx) is one of
the real historical Commandeur Consulting profile documents, used verbatim so
the letterhead/logo/fonts/colours are pixel-identical to existing profiles.
Its body paragraphs are used as formatting "donors": for each item we need to
render, we clone the matching template paragraph (which carries the exact
font/bold/colour/tab-stop formatting) and only replace its text content, then
insert the clone(s) and finally drop the original donor paragraph(s).

NOTE: this is new, not-yet-visually-verified code (nobody on this team can
render a .docx to check pixel layout outside of actually opening it in Word).
Treat the first real export as a draft to review in Word, not as final.
"""

from __future__ import annotations

import copy
import io
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from cc_crm.core.errors import ConflictError
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import Anrede

TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "templates" / "anonymes_profil_master.docx"

_HEADING_UEBERBLICK = "Überblick"
_HEADING_KURZPROFIL = "Kurzprofil"
_HEADING_QUALIFIKATIONEN = "Fachliche Qualifikationen"
_HEADING_LEBENSLAUF = "Lebenslauf (Auszug)"
_HEADING_AUSBILDUNG = "Ausbildung & Weiterbildung"
_HEADING_WEITERE_INFOS = "Weitere Infos"

_ZEITRAUM_CV = re.compile(r"^(seit\s+\d{1,2}/\d{4}|\d{1,2}/\d{4}\s*[–-]\s*\d{1,2}/\d{4})\s+(.*)$")
_ZEITRAUM_AUSBILDUNG = re.compile(r"^(\d{4}\s*[–-]\s*\d{4}|\d{4})\s+(.*)$")

_HEADER_LABELS = {
    Anrede.FRAU: "Kandidatin-Nr.",
    Anrede.HERR: "Kandidat-Nr.",
    Anrede.DIVERS: "Kandidat:in-Nr.",
    None: "Kandidat:in-Nr.",
}


class ProfileParseError(ConflictError):
    """Raised when short_profile has no usable content to export."""


def _parse_short_profile(text: str) -> dict[str, Any]:
    """Best-effort parse of the LLM-generated markdown-ish profile text into
    the sections the Word template expects. Any section that can't be found
    is simply omitted from the export instead of raising - a rough/edited
    profile should still export what is parseable."""
    text = (text or "").replace("\r\n", "\n").strip()

    sections: dict[str, str] = {}
    heading_pattern = re.compile(r"\*\*(.+?)\*\*[ \t]*\n(.*?)(?=\n\*\*.+?\*\*|\Z)", re.DOTALL)
    for heading_match in heading_pattern.finditer(text):
        sections[heading_match.group(1).strip()] = heading_match.group(2).strip()

    ueberblick: dict[str, str] = {}
    for line in sections.get(_HEADING_UEBERBLICK, "").splitlines():
        if ":" in line:
            label, _, value = line.partition(":")
            ueberblick[label.strip()] = value.strip()

    bullets = [
        line.lstrip("•-* \t").strip()
        for line in sections.get(_HEADING_QUALIFIKATIONEN, "").splitlines()
        if line.strip()
    ]

    cv_lines: list[tuple[str, str]] = []
    for line in sections.get(_HEADING_LEBENSLAUF, "").splitlines():
        line = line.strip()
        if not line:
            continue
        cv_match = _ZEITRAUM_CV.match(line)
        cv_lines.append((cv_match.group(1), cv_match.group(2)) if cv_match else ("", line))

    ausbildung_lines: list[tuple[str, str]] = []
    for line in sections.get(_HEADING_AUSBILDUNG, "").splitlines():
        line = line.strip()
        if not line:
            continue
        ausbildung_match = _ZEITRAUM_AUSBILDUNG.match(line)
        ausbildung_lines.append(
            (ausbildung_match.group(1), ausbildung_match.group(2))
            if ausbildung_match
            else ("", line)
        )

    weitere_infos: dict[str, str] = {}
    for line in sections.get(_HEADING_WEITERE_INFOS, "").splitlines():
        if ":" in line:
            label, _, value = line.partition(":")
            weitere_infos[label.strip()] = value.strip()

    header_match = re.search(r"##\s*(?:Kandidatin|Kandidat|Kandidat:in)-Nr\.\s*(\S+)", text)

    return {
        "ueberblick": ueberblick,
        "kurzprofil": sections.get(_HEADING_KURZPROFIL, "").strip(),
        "bullets": bullets,
        "cv_lines": cv_lines,
        "ausbildung_lines": ausbildung_lines,
        "weitere_infos": weitere_infos,
        "candidate_number": header_match.group(1) if header_match else None,
    }


def _section_bounds(
    doc: DocxDocument, headings: list[str]
) -> dict[str, tuple[Paragraph, list[Paragraph]]]:
    """Maps each heading text to (heading_paragraph, body_paragraphs).

    Captured as direct python-docx Paragraph object references - NOT list
    indices - computed once up front. Indices into doc.paragraphs go stale the
    moment any earlier section removes/inserts paragraphs (every render_section
    call does), so later sections would look up the wrong paragraph or run off
    the end of a now-shorter list. Object references stay valid regardless of
    what happens elsewhere in the tree, since removing one paragraph doesn't
    invalidate a sibling paragraph's own element reference.
    """
    paragraphs = doc.paragraphs
    heading_positions: list[tuple[str, int]] = []
    seen: set[str] = set()
    for i, paragraph in enumerate(paragraphs):
        text = paragraph.text.strip()
        if text in headings and text not in seen:
            heading_positions.append((text, i))
            seen.add(text)
    bounds: dict[str, tuple[Paragraph, list[Paragraph]]] = {}
    for position, (heading, index) in enumerate(heading_positions):
        next_index = (
            heading_positions[position + 1][1]
            if position + 1 < len(heading_positions)
            else len(paragraphs)
        )
        bounds[heading] = (paragraphs[index], paragraphs[index + 1 : next_index])
    return bounds


def _first_tab_run_index(paragraph: Paragraph) -> int | None:
    for i, run in enumerate(paragraph.runs):
        if run._element.find(qn("w:tab")) is not None:
            return i
    return None


def _first_non_bold_run_index(paragraph: Paragraph) -> int | None:
    for i, run in enumerate(paragraph.runs):
        if not run.bold:
            return i
    return None


def _remove_runs_after(paragraph: Paragraph, keep_index: int) -> None:
    for run in paragraph.runs[keep_index + 1 :]:
        run._element.getparent().remove(run._element)


def _clone_paragraph(template: Paragraph) -> Paragraph:
    clone_element = copy.deepcopy(template._p)
    template._p.addprevious(clone_element)
    return Paragraph(clone_element, template._parent)


def _remove_paragraph(paragraph: Paragraph) -> None:
    element = paragraph._p
    element.getparent().remove(element)


def _copy_run_format(source_run: Run, target_run: Run) -> None:
    """Copies a run's full <w:rPr> (font/bold/colour/size) onto another run,
    replacing whatever formatting python-docx gave the target by default."""
    source_rpr = source_run._element.find(qn("w:rPr"))
    target_rpr = target_run._element.find(qn("w:rPr"))
    if target_rpr is not None:
        target_run._element.remove(target_rpr)
    if source_rpr is not None:
        target_run._element.insert(0, copy.deepcopy(source_rpr))


def _fill_two_part_row(template: Paragraph, left: str, right: str) -> Paragraph:
    """Clone a '<tab>-separated template row where BOTH sides are dynamic:
    'Label:<tab>Value' (Überblick fields, label passed as `left`) as well as
    'Zeitraum<tab>Rolle' (Lebenslauf / Ausbildung & Weiterbildung lines).

    Bug history: an earlier version (_fill_label_value_row) only replaced the
    value and assumed the donor row already carried the right label - but
    render_section() reuses a single donor paragraph for every item in a
    section, so every cloned Überblick row ended up with the label text of
    whichever field happened to be rows[0] ("Wohnort:" on every line). Always
    writing BOTH sides explicitly, as this function does, avoids that class
    of bug entirely.
    """
    clone = _clone_paragraph(template)
    tab_index = _first_tab_run_index(clone)
    if tab_index is None:
        if clone.runs:
            clone.runs[0].text = f"{left} {right}".strip()
            _remove_runs_after(clone, 0)
        return clone

    left_format_source = clone.runs[0]
    right_format_source = clone.runs[tab_index]
    tab_element = right_format_source._element.find(qn("w:tab"))

    # Right side: strip everything except <w:rPr>/<w:tab/> from the tab run,
    # drop any runs after it, then append a fresh run for `right`.
    for child in list(right_format_source._element):
        if child.tag == qn("w:rPr") or child is tab_element:
            continue
        right_format_source._element.remove(child)
    _remove_runs_after(clone, tab_index)
    right_run = clone.add_run(right)
    _copy_run_format(right_format_source, right_run)

    # Left side: put `left` into the first run, drop any other runs between
    # the first run and the tab run.
    for run in clone.runs[1:tab_index]:
        run._element.getparent().remove(run._element)
    left_t = left_format_source._element.find(qn("w:t"))
    if left_t is None:
        left_t = left_format_source._element.makeelement(qn("w:t"), {})
        left_format_source._element.append(left_t)
    left_t.text = left
    left_t.set(qn("xml:space"), "preserve")

    return clone


def _fill_plain_row(template: Paragraph, text: str) -> Paragraph:
    """Clone a plain (no tab, no label) template row - used for Kurzprofil
    sentences and Fachliche Qualifikationen bullets."""
    clone = _clone_paragraph(template)
    if clone.runs:
        clone.runs[0].text = text
        _remove_runs_after(clone, 0)
    else:
        clone.add_run(text)
    return clone


def _fill_labelled_optional_row(template: Paragraph, label: str, value: str) -> Paragraph:
    """Clone a 'Label: value' row with NO tab, where the label is the bold
    run(s) and the value is the first non-bold run onward (Weitere Infos)."""
    clone = _clone_paragraph(template)
    value_index = _first_non_bold_run_index(clone)
    if value_index is None:
        clone.add_run(f"{label}: {value}")
        return clone
    if clone.runs:
        clone.runs[0].text = f"{label}: "
    clone.runs[value_index].text = value
    _remove_runs_after(clone, value_index)
    return clone


def _set_header_title(doc: DocxDocument, label: str, number: str) -> None:
    """The candidate-number title lives in the section header - either as a
    plain paragraph or (as in the current Commandeur template) inside a table
    cell alongside the logo."""

    def _apply(paragraph: Paragraph) -> bool:
        if "Nr." not in paragraph.text:
            return False
        if not paragraph.runs:
            return False
        paragraph.runs[0].text = f"{label} {number}"
        _remove_runs_after(paragraph, 0)
        return True

    for section in doc.sections:
        header = section.header
        for paragraph in header.paragraphs:
            if _apply(paragraph):
                return
        for table in header.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if _apply(paragraph):
                            return


def generate_profile_docx(candidate: Candidate) -> bytes:
    if not candidate.short_profile or not candidate.short_profile.strip():
        raise ProfileParseError(
            "Kein anonymes Profil vorhanden - bitte zuerst über 'Anonymes Profil "
            "vorbereiten' generieren und speichern."
        )
    parsed = _parse_short_profile(candidate.short_profile)

    doc = Document(str(TEMPLATE_PATH))

    number = candidate.candidate_number or parsed.get("candidate_number") or str(candidate.id)
    label = _HEADER_LABELS.get(candidate.anrede, _HEADER_LABELS[None])
    _set_header_title(doc, label, number)

    headings = [
        _HEADING_UEBERBLICK,
        _HEADING_KURZPROFIL,
        _HEADING_QUALIFIKATIONEN,
        _HEADING_LEBENSLAUF,
        _HEADING_AUSBILDUNG,
        _HEADING_WEITERE_INFOS,
    ]
    bounds = _section_bounds(doc, headings)

    def section_paragraphs(heading: str) -> list[Paragraph]:
        if heading not in bounds:
            return []
        return bounds[heading][1]

    def render_section(
        heading: str,
        items: list[Any],
        fill_one: Callable[[Paragraph, Any], Paragraph],
        remove_heading_if_empty: bool = True,
    ) -> None:
        rows = [p for p in section_paragraphs(heading) if p.text.strip()]
        if rows and items:
            donor = rows[0]
            for item in items:
                fill_one(donor, item)
            for row in rows:
                _remove_paragraph(row)
        elif not items:
            for row in rows:
                _remove_paragraph(row)
            if remove_heading_if_empty and heading in bounds:
                _remove_paragraph(bounds[heading][0])

    render_section(
        _HEADING_UEBERBLICK,
        list(parsed["ueberblick"].items()),
        lambda donor, item: _fill_two_part_row(donor, f"{item[0]}:", item[1]),
        remove_heading_if_empty=False,
    )
    render_section(
        _HEADING_KURZPROFIL,
        [c.strip() for c in parsed["kurzprofil"].split("\n") if c.strip()],
        _fill_plain_row,
    )
    render_section(_HEADING_QUALIFIKATIONEN, parsed["bullets"], _fill_plain_row)
    render_section(
        _HEADING_LEBENSLAUF,
        parsed["cv_lines"],
        lambda donor, item: _fill_two_part_row(donor, item[0], item[1]),
    )
    render_section(
        _HEADING_AUSBILDUNG,
        parsed["ausbildung_lines"],
        lambda donor, item: (
            _fill_two_part_row(donor, item[0], item[1])
            if item[0]
            else _fill_plain_row(donor, item[1])
        ),
    )
    render_section(
        _HEADING_WEITERE_INFOS,
        list(parsed["weitere_infos"].items()),
        lambda donor, item: _fill_labelled_optional_row(donor, item[0], item[1]),
    )

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
