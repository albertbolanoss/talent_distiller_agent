"""Extracts text from plain-text files (.txt, .md, and similar)."""

from pathlib import Path


def read_text_file(path: Path) -> str:
    """Return the file's contents decoded as UTF-8."""
    return path.read_text(encoding="utf-8", errors="replace").strip()
