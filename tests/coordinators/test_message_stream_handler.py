"""Tests for draining a coordinator turn's message stream."""

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from labs_agent_lib import AgentTranscriptWriter

from talent_distiller_agent.coordinators.message_stream_handler import (
    _extract_formatted_content,
    _extract_text,
    _is_desirable_tool_input,
    process_coordinator_stream,
)
from talent_distiller_agent.storage import DocumentType
from talent_distiller_agent.storage.redis_job_store import JobStatus

RESUME_PATH = "resume/jane.pdf"
JOB_POSTING_PATH = "job_posting/backend.pdf"
CORRELATION_ID = "corr-1"


class _DisabledObservabilitySettings:
    """Keeps `AgentTranscriptWriter` a no-op so these Redis-focused tests stay unaffected."""

    observability_enabled = False
    agent_transcript_dir = "unused"


_NOOP_TRANSCRIPT = AgentTranscriptWriter(_DisabledObservabilitySettings(), service="talent_distiller_agent")

EXTRACT_TECH_TOOL = "mcp__candidate-skill-agent-technical__extract_technical_skills"
EXTRACT_SOFT_TOOL = "mcp__candidate-skill-agent-soft__extract_soft_skills"
EXTRACT_LANG_TOOL = "mcp__candidate-skill-agent-languages__extract_languages"


def test_extract_text_returns_empty_string_for_none():
    assert _extract_text(None) == ""


def test_extract_text_passes_through_a_plain_string():
    assert _extract_text("raw text") == "raw text"


def test_extract_text_concatenates_text_blocks_and_ignores_others():
    content = [
        {"type": "text", "text": "Hello "},
        {"type": "tool_reference", "tool_name": "ignored"},
        {"type": "text", "text": "world"},
    ]
    assert _extract_text(content) == "Hello world"


def test_extract_formatted_content_returns_none_when_no_tag_is_present():
    assert _extract_formatted_content("just plain text") is None


def test_extract_formatted_content_extracts_and_strips_a_formatted_resume_block():
    text = "preamble <formatted_resume>\n  content here \n</formatted_resume> trailing"
    assert _extract_formatted_content(text) == "content here"


def test_extract_formatted_content_extracts_a_formatted_job_posting_block():
    text = "<formatted_job_posting>role details</formatted_job_posting>"
    assert _extract_formatted_content(text) == "role details"


def test_is_desirable_tool_input_returns_false_for_a_non_dict_input():
    assert _is_desirable_tool_input(None) is False
    assert _is_desirable_tool_input("not a dict") is False


def test_is_desirable_tool_input_returns_false_when_no_signal_is_present():
    assert _is_desirable_tool_input({"file_path": "x"}) is False


def test_is_desirable_tool_input_detects_the_is_desirable_flag():
    assert _is_desirable_tool_input({"is_desirable": True}) is True


def test_is_desirable_tool_input_detects_the_desirable_flag():
    assert _is_desirable_tool_input({"desirable": True}) is True


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("type", "Desirable"),
        ("category", "deseable"),
        ("requirement_type", "nice_to_have"),
        ("section", "optional"),
        ("kind", "Optional"),
    ],
)
def test_is_desirable_tool_input_detects_keyword_signals(key: str, value: str):
    assert _is_desirable_tool_input({key: value}) is True


class _StubClient:
    """Replays a fixed list of messages as the stream `process_coordinator_stream` drains."""

    def __init__(self, messages: list) -> None:
        self._messages = messages

    async def receive_response(self):
        for message in self._messages:
            yield message


class _FakeTracker:
    """Records every Redis checkpoint `process_coordinator_stream` would have made."""

    def __init__(
        self, doc_type: DocumentType = DocumentType.RESUME, missing_fields: list[str] | None = None
    ) -> None:
        self.doc_type = doc_type
        self._missing_fields = list(missing_fields or [])
        self.contents: list[str] = []
        self.results: list[tuple[str, str]] = []
        self.errors: list[tuple[str, str]] = []

    async def get_status(self, file_path: str) -> JobStatus:
        return JobStatus(
            resume_path=file_path,
            revision_number=0,
            has_content=True,
            missing_fields=list(self._missing_fields),
        )

    async def save_content(self, file_path: str, content: str) -> None:
        self.contents.append(content)

    async def save_agent_result(self, file_path: str, field: str, raw_json: str) -> None:
        self.results.append((field, raw_json))

    async def save_agent_error(self, file_path: str, field: str, error_msg: str) -> None:
        self.errors.append((field, error_msg))


def _result_message(
    *, is_error: bool = False, stop_reason: str | None = "end_turn", session_id: str = "session-1"
) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=is_error,
        num_turns=1,
        session_id=session_id,
        stop_reason=stop_reason,
    )


async def test_captures_formatted_resume_content_from_a_text_block():
    messages = [
        AssistantMessage(
            content=[TextBlock(text="<formatted_resume>Jane Doe\nProfile</formatted_resume>")], model="claude"
        ),
        _result_message(stop_reason="end_turn", session_id="session-42"),
    ]
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.contents == ["Jane Doe\nProfile"]
    assert stop_reason == "end_turn"
    assert session_id == "session-42"


async def test_records_an_agent_error_for_an_empty_formatted_resume_block():
    messages = [
        AssistantMessage(content=[TextBlock(text="<formatted_resume></formatted_resume>")], model="claude"),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.contents == []
    assert tracker.errors == [("content", "Coordinator returned an empty formatted resume block.")]


async def test_records_an_agent_error_for_an_empty_formatted_job_posting_block():
    messages = [
        AssistantMessage(
            content=[TextBlock(text="<formatted_job_posting></formatted_job_posting>")], model="claude"
        ),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING)

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.errors == [("content", "Coordinator returned an empty formatted job_posting block.")]


async def test_ignores_text_blocks_without_a_formatted_tag():
    messages = [
        AssistantMessage(content=[TextBlock(text="just thinking out loud")], model="claude"),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.contents == []
    assert tracker.errors == []


async def test_checkpoints_an_extraction_result_under_its_redis_field_for_a_resume():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="soft-1", name=EXTRACT_SOFT_TOOL, input={})], model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="soft-1", content='{"soft_skills": ["communication"]}')]),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [("soft_skills", '{"soft_skills": ["communication"]}')]


async def test_captures_an_errored_extraction_tool_result_as_an_agent_error():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="tech-1", name=EXTRACT_TECH_TOOL, input={})], model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="tech-1", content="boom", is_error=True)]),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.errors == [("technical_skills", "boom")]
    assert tracker.results == []


async def test_ignores_an_errored_result_from_an_unrecognized_tool():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="search-1", name="ToolSearch", input={})], model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="search-1", content="boom", is_error=True)]),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.contents == []
    assert tracker.results == []
    assert tracker.errors == []


async def test_ignores_a_successful_result_from_an_unrecognized_tool():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="search-1", name="ToolSearch", input={})], model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="search-1", content="some tool reference")]),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.contents == []
    assert tracker.results == []
    assert tracker.errors == []


async def test_ignores_non_tool_result_blocks_and_string_only_user_messages():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="soft-1", name=EXTRACT_SOFT_TOOL, input={})], model="claude"),
        UserMessage(
            content=[
                TextBlock(text="(not a tool result - must be skipped without stopping the scan)"),
                ToolResultBlock(tool_use_id="soft-1", content='{"soft_skills": []}'),
            ]
        ),
        UserMessage(content="just acknowledging, no tool results in this turn"),
        _result_message(stop_reason="end_turn", session_id="session-42"),
    ]
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [("soft_skills", '{"soft_skills": []}')]
    assert stop_reason == "end_turn"
    assert session_id == "session-42"


async def test_result_message_with_is_error_is_still_reported():
    messages = [_result_message(is_error=True, stop_reason="error", session_id="session-err")]
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert stop_reason == "error"
    assert session_id == "session-err"


async def test_ignores_message_types_it_does_not_handle():
    messages = [
        SystemMessage(subtype="init", data={}),
        AssistantMessage(content=[ThinkingBlock(thinking="hmm", signature="sig")], model="claude"),
        _result_message(stop_reason="end_turn", session_id="session-1"),
    ]
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert stop_reason == "end_turn"
    assert session_id == "session-1"


async def test_returns_all_none_for_an_empty_stream():
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(
        _StubClient([]), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert (stop_reason, session_id) == (None, None)


async def test_last_result_message_wins_when_the_stream_has_more_than_one():
    messages = [
        _result_message(stop_reason="tool_use", session_id="first"),
        _result_message(stop_reason="end_turn", session_id="second"),
    ]
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(
        _StubClient(messages), tracker, RESUME_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert stop_reason == "end_turn"
    assert session_id == "second"


async def test_resolves_the_mandatory_field_for_a_job_posting_when_it_is_still_missing():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={})], model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="lang-1", content='{"languages": ["english"]}')]),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["languages", "desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [("languages", '{"languages": ["english"]}')]


async def test_resolves_the_desirable_field_when_the_tool_input_flags_it_as_desirable():
    messages = [
        AssistantMessage(
            content=[ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={"is_desirable": True})],
            model="claude",
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="lang-1", content='{"languages": ["french"]}')]),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["languages", "desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [("desirable_languages", '{"languages": ["french"]}')]


async def test_resolves_the_desirable_field_once_the_mandatory_field_is_already_checkpointed():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={})], model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="lang-1", content='{"languages": ["german"]}')]),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [("desirable_languages", '{"languages": ["german"]}')]


async def test_second_call_to_the_same_mandatory_field_within_a_turn_falls_back_to_desirable():
    messages = [
        AssistantMessage(
            content=[
                ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={}),
                ToolUseBlock(id="lang-2", name=EXTRACT_LANG_TOOL, input={}),
            ],
            model="claude",
        ),
        UserMessage(
            content=[
                ToolResultBlock(tool_use_id="lang-1", content='{"languages": ["english"]}'),
                ToolResultBlock(tool_use_id="lang-2", content='{"languages": ["spanish"]}'),
            ]
        ),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["languages", "desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [
        ("languages", '{"languages": ["english"]}'),
        ("desirable_languages", '{"languages": ["spanish"]}'),
    ]


async def test_records_an_agent_error_under_the_resolved_desirable_field_for_a_job_posting():
    messages = [
        AssistantMessage(
            content=[ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={"category": "nice_to_have"})],
            model="claude",
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="lang-1", content="boom", is_error=True)]),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["languages", "desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.errors == [("desirable_languages", "boom")]


async def test_splits_a_composite_mandatory_desirable_json_payload_for_a_job_posting():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={})], model="claude"),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="lang-1",
                    content='{"mandatory": ["english"], "desirable": ["french"]}',
                )
            ]
        ),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["languages", "desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [
        ("languages", '["english"]'),
        ("desirable_languages", '["french"]'),
    ]


async def test_splits_a_composite_required_desirable_json_payload_for_a_job_posting():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={})], model="claude"),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="lang-1",
                    content='{"required": ["english"], "desirable": ["french"]}',
                )
            ]
        ),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["languages", "desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [
        ("languages", '["english"]'),
        ("desirable_languages", '["french"]'),
    ]


async def test_saves_a_dict_with_only_a_desirable_key_directly_without_splitting():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={})], model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="lang-1", content='{"desirable": ["french"]}')]),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["languages", "desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [("languages", '{"desirable": ["french"]}')]


async def test_saves_a_non_json_payload_directly_for_a_job_posting():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={})], model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="lang-1", content="not json")]),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["languages", "desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [("languages", "not json")]


async def test_saves_a_json_array_payload_directly_for_a_job_posting():
    messages = [
        AssistantMessage(content=[ToolUseBlock(id="lang-1", name=EXTRACT_LANG_TOOL, input={})], model="claude"),
        UserMessage(content=[ToolResultBlock(tool_use_id="lang-1", content='["english"]')]),
        _result_message(),
    ]
    tracker = _FakeTracker(doc_type=DocumentType.JOB_POSTING, missing_fields=["languages", "desirable_languages"])

    await process_coordinator_stream(
        _StubClient(messages), tracker, JOB_POSTING_PATH, CORRELATION_ID, _NOOP_TRANSCRIPT
    )

    assert tracker.results == [("languages", '["english"]')]
