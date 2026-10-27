from collections.abc import Callable
from pathlib import Path

from candidate_match_agent.libs.file_reader.pdf_reader import read_pdf


def test_reads_single_page_text(make_pdf: Callable[..., Path]):
    path = make_pdf("Hello PDF")

    assert read_pdf(path) == "Hello PDF"


def test_joins_multiple_pages_with_a_blank_line(make_pdf: Callable[..., Path]):
    # pymupdf's get_text("text") ends each page's text with its own trailing newline, so the
    # "\n\n" join separator produces 3 newlines (2 blank lines) between pages, not 2 (1 blank line).
    path = make_pdf("Page one", "Page two")

    assert read_pdf(path) == "Page one\n\n\nPage two"


def test_page_without_text_contributes_no_extra_trailing_newline(make_pdf: Callable[..., Path]):
    path = make_pdf("Page one", "", "Page three")

    assert read_pdf(path) == "Page one\n\n\n\n\nPage three"


def test_blank_document_returns_empty_string(make_pdf: Callable[..., Path]):
    path = make_pdf("")

    assert read_pdf(path) == ""
