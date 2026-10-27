"""Extracts text from Word (.docx) files."""

import docx2txt
from pathlib import Path

def read_docx(path: Path) -> str:
    """Extrae todo el texto de un DOCX, incluyendo tablas."""
    text = docx2txt.process(path)
    return text.strip()
