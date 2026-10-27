"""Extracts text from Word (.docx) files."""

from pathlib import Path

from docx import Document


def read_docx(path: Path) -> str:
    """Return the text of every paragraph in a .docx file, in order.

    Text inside tables is not included; resumes rarely rely on tables for content.
    """
    document = Document(path)
    paragraphs = (paragraph.text for paragraph in document.paragraphs)
    return "\n".join(paragraphs).strip()
