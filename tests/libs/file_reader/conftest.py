"""Shared fixtures for file_reader tests."""

from collections.abc import Callable
from pathlib import Path

import pytest


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def pdf_bytes(*page_texts: str) -> bytes:
    """Build a minimal, valid PDF with one page per entry in `page_texts`.

    Hand-rolled instead of produced by a PDF-writing library, so these tests
    exercise the reader (pypdf) against plain PDF syntax rather than against
    whatever another library's writer happens to produce.
    """
    page_count = len(page_texts)
    font_id = 3 + 2 * page_count

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{3 + i} 0 R' for i in range(page_count))}] "
            f"/Count {page_count} >>"
        ).encode(),
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i, text in enumerate(page_texts):
        page_id = 3 + i
        content_id = 3 + page_count + i
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode()
        stream = f"BT /F1 24 Tf 10 100 Td ({_escape_pdf_text(text)}) Tj ET".encode("latin-1")
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    buf = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for obj_id in sorted(objects):
        offsets[obj_id] = len(buf)
        buf += f"{obj_id} 0 obj\n".encode()
        buf += objects[obj_id]
        buf += b"\nendobj\n"

    xref_offset = len(buf)
    max_id = max(objects)
    buf += f"xref\n0 {max_id + 1}\n".encode()
    buf += b"0000000000 65535 f \n"
    for obj_id in range(1, max_id + 1):
        offset = offsets.get(obj_id)
        line = f"{offset:010d} 00000 n \n" if offset is not None else "0000000000 00000 f \n"
        buf += line.encode()
    buf += (
        f"trailer\n<< /Size {max_id + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    ).encode()
    return bytes(buf)


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    """Return a factory that writes a PDF with the given page texts and returns its path."""

    def _make(*page_texts: str, name: str = "document.pdf") -> Path:
        path = tmp_path / name
        path.write_bytes(pdf_bytes(*page_texts))
        return path

    return _make
