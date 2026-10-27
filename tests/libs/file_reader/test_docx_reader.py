from pathlib import Path

from docx import Document

from candidate_match_agent.libs.file_reader.docx_reader import read_docx


def _make_docx(tmp_path: Path, paragraphs: list[str], name: str = "resume.docx") -> Path:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    path = tmp_path / name
    document.save(path)
    return path


def test_joins_paragraphs_with_blank_lines_in_order(tmp_path: Path):
    path = _make_docx(tmp_path, ["Candidate: Jane Doe", "Skills: Python, SQL"])

    assert read_docx(path) == "Candidate: Jane Doe\n\nSkills: Python, SQL"


def test_strips_leading_and_trailing_blank_paragraphs(tmp_path: Path):
    path = _make_docx(tmp_path, ["", "Candidate: Jane Doe", ""])

    assert read_docx(path) == "Candidate: Jane Doe"


def test_empty_document_returns_empty_string(tmp_path: Path):
    path = _make_docx(tmp_path, [])

    assert read_docx(path) == ""


def test_table_text_is_included(tmp_path: Path):
    document = Document()
    document.add_paragraph("Candidate: Jane Doe")
    table = document.add_table(rows=1, cols=1)
    table.rows[0].cells[0].text = "Skill: Python"
    path = tmp_path / "with_table.docx"
    document.save(path)

    assert read_docx(path) == "Candidate: Jane Doe\n\nSkill: Python"
