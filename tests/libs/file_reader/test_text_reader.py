from pathlib import Path

from candidate_match_agent.libs.file_reader.text_reader import read_text_file


def test_reads_plain_text_content(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("Hello plain text\nSecond line", encoding="utf-8")

    assert read_text_file(path) == "Hello plain text\nSecond line"


def test_strips_leading_and_trailing_whitespace(tmp_path: Path):
    path = tmp_path / "notes.md"
    path.write_text("\n\n  # Title  \n\n", encoding="utf-8")

    assert read_text_file(path) == "# Title"


def test_preserves_non_ascii_characters(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("Candidato: José Ñáñez", encoding="utf-8")

    assert read_text_file(path) == "Candidato: José Ñáñez"


def test_replaces_invalid_utf8_bytes_instead_of_raising(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_bytes(b"valid before \xff\xfe invalid")

    result = read_text_file(path)

    assert "valid before" in result
    assert "�" in result
