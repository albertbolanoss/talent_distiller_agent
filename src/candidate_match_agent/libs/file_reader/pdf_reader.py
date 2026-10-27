"""Extracts text from PDF files."""


import pymupdf
from pathlib import Path

def read_pdf(path: Path) -> str:
    """Return the concatenated text of every page in a PDF file."""
    doc = pymupdf.open(path)
    pages = [page.get_text("text") for page in doc]
    return "\n\n".join(pages).strip()