"""Picks a reader for a document from its extension and extracts its text."""

from pathlib import Path

from .docx_reader import read_docx
from .errors import UnsupportedFileTypeError
from .pdf_reader import read_pdf
from .text_reader import read_text_file

_READERS = {
    ".pdf": read_pdf,
    ".docx": read_docx,
    ".txt": read_text_file,
    ".md": read_text_file,
    ".markdown": read_text_file,
}

SUPPORTED_EXTENSIONS = sorted(_READERS)


def extract_text(file_path: str) -> str:
    """Read `file_path` and return its text content.

    The reader is picked from the file's extension (see SUPPORTED_EXTENSIONS);
    callers don't need to know which parser handles which format.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    read = _READERS.get(path.suffix.lower())
    if read is None:
        raise UnsupportedFileTypeError(path.suffix, SUPPORTED_EXTENSIONS)

    return read(path)
