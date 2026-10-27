"""Tests for the coordinator's system prompt."""

from candidate_match_agent_cli.prompts import DOCUMENT_READ_PROMPT
from candidate_match_agent_cli.prompts.document_read import DOCUMENT_READ_PROMPT as prompt_from_module


def test_is_exported_from_the_package_root():
    assert DOCUMENT_READ_PROMPT is prompt_from_module


def test_instructs_the_model_to_call_read_document_with_the_resume_path():
    assert "read_document" in DOCUMENT_READ_PROMPT
    assert "<resume_path>" in DOCUMENT_READ_PROMPT


def test_instructs_the_model_not_to_repeat_the_document_content():
    """Repeating the content as output tokens is what made turns slow - the caller reads it
    straight from the tool result instead (see message_stream_handler.process_coordinator_stream)."""
    assert "Do NOT repeat" in DOCUMENT_READ_PROMPT
