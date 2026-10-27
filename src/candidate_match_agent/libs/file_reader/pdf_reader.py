"""Extracts text from PDF files."""

from pathlib import Path

from pypdf import PdfReader


def read_pdf(path: Path) -> str:
    """Return the concatenated text of every page in a PDF file."""
    reader = PdfReader(path)
    pages = (page.extract_text() or "" for page in reader.pages)
    return "\n\n".join(pages).strip()
