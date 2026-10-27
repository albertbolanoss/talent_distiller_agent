from pathlib import Path

import pytest

from candidate_match_agent.libs.file_reader import extractor
from candidate_match_agent.libs.file_reader.errors import UnsupportedFileTypeError
from candidate_match_agent.libs.file_reader.extractor import SUPPORTED_EXTENSIONS, extract_text


def test_supported_extensions_lists_every_registered_extension():
    assert SUPPORTED_EXTENSIONS == [".docx", ".markdown", ".md", ".pdf", ".txt"]


@pytest.mark.parametrize("extension", SUPPORTED_EXTENSIONS)
def test_dispatches_to_the_reader_registered_for_the_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extension: str
):
    path = tmp_path / f"document{extension}"
    path.write_text("irrelevant for this test", encoding="utf-8")
    calls: list[Path] = []
    monkeypatch.setitem(extractor._READERS, extension, calls.append)

    extract_text(str(path))

    assert calls == [path]


def test_extension_matching_is_case_insensitive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "document.PDF"
    path.write_text("irrelevant for this test", encoding="utf-8")
    calls: list[Path] = []
    monkeypatch.setitem(extractor._READERS, ".pdf", calls.append)

    extract_text(str(path))

    assert calls == [path]


def test_returns_the_reader_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "document.txt"
    path.write_text("irrelevant for this test", encoding="utf-8")
    monkeypatch.setitem(extractor._READERS, ".txt", lambda _path: "extracted content")

    assert extract_text(str(path)) == "extracted content"


def test_reads_a_real_text_file_end_to_end(tmp_path: Path):
    path = tmp_path / "resume.txt"
    path.write_text("Candidate: Jane Doe", encoding="utf-8")

    assert extract_text(str(path)) == "Candidate: Jane Doe"


def test_missing_file_raises_file_not_found(tmp_path: Path):
    missing = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError, match=r"File not found.*missing\.txt"):
        extract_text(str(missing))


def test_unsupported_extension_raises_with_extension_and_supported_list(tmp_path: Path):
    path = tmp_path / "resume.csv"
    path.write_text("a,b,c", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError) as exc_info:
        extract_text(str(path))

    assert exc_info.value.extension == ".csv"
    assert exc_info.value.supported == SUPPORTED_EXTENSIONS


def test_directory_path_raises_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        extract_text(str(tmp_path))
