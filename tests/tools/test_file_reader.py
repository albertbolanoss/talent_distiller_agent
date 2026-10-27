"""Tests for the `read_document` MCP tool."""

from pathlib import Path

import pytest

from candidate_match_agent.libs.file_reader.errors import UnsupportedFileTypeError
from candidate_match_agent.tools.file_reader import read_document


def test_name_and_description_advertise_the_supported_extensions():
    assert read_document.name == "read_document"
    assert ".pdf" in read_document.description
    assert ".docx" in read_document.description


async def test_handler_returns_the_extracted_text_as_a_content_block(tmp_path: Path):
    path = tmp_path / "resume.txt"
    path.write_text("Candidate: Jane Doe", encoding="utf-8")

    result = await read_document.handler({"file_path": str(path)})

    assert result == {"content": [{"type": "text", "text": "Candidate: Jane Doe"}]}


async def test_handler_raises_for_an_unsupported_extension(tmp_path: Path):
    path = tmp_path / "resume.csv"
    path.write_text("a,b,c", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError):
        await read_document.handler({"file_path": str(path)})
