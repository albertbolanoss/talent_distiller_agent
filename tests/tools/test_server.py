"""Tests for the in-process file-reader MCP server."""

from candidate_match_agent.tools import FILE_READER_SERVER, FILE_READER_SERVER_NAME


def test_server_name_matches_the_exported_constant():
    assert FILE_READER_SERVER["name"] == FILE_READER_SERVER_NAME == "file-reader"


def test_server_is_an_in_process_sdk_server():
    assert FILE_READER_SERVER["type"] == "sdk"
    assert FILE_READER_SERVER["instance"].name == FILE_READER_SERVER_NAME
