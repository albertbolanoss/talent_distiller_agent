"""Tests for draining a coordinator turn's message stream."""

from collections.abc import AsyncIterator

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

from candidate_match_agent_cli.coordinators.message_stream_handler import (
    READ_DOCUMENT_TOOL_NAME,
    process_coordinator_stream,
)

RESUME_PATH = "resume/jane.pdf"


class _StubClient:
    """Replays a fixed list of messages as the stream `process_coordinator_stream` drains."""

    def __init__(self, messages: list) -> None:
        self._messages = messages

    async def receive_response(self) -> AsyncIterator:
        for message in self._messages:
            yield message


class _FakeTracker:
    """Records every Redis checkpoint `process_coordinator_stream` would have made."""

    def __init__(self) -> None:
        self.contents: list[str] = []
        self.results: list[tuple[str, str]] = []
        self.errors: list[tuple[str, str]] = []

    async def save_content(self, resume_path: str, content: str) -> None:
        assert resume_path == RESUME_PATH
        self.contents.append(content)

    async def save_agent_result(self, resume_path: str, field: str, raw_json: str) -> None:
        assert resume_path == RESUME_PATH
        self.results.append((field, raw_json))

    async def save_agent_error(self, resume_path: str, field: str, error_msg: str) -> None:
        assert resume_path == RESUME_PATH
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


async def test_captures_the_read_document_result_and_ignores_unrelated_tools():
    messages = [
        AssistantMessage(
            content=[
                ThinkingBlock(thinking="let me find the tool", signature="sig"),
                ToolUseBlock(id="search-1", name="ToolSearch", input={"query": "read_document"}),
            ],
            model="claude",
        ),
        UserMessage(
            content=[
                TextBlock(text="(not a tool result - must be skipped without stopping the scan)"),
                ToolResultBlock(
                    tool_use_id="search-1",
                    content=[{"type": "tool_reference", "tool_name": READ_DOCUMENT_TOOL_NAME}],
                ),
            ]
        ),
        AssistantMessage(
            content=[ToolUseBlock(id="read-1", name=READ_DOCUMENT_TOOL_NAME, input={"file_path": "resume.pdf"})],
            model="claude",
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="read-1",
                    content=[{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}],
                    is_error=False,
                )
            ]
        ),
        UserMessage(content="just acknowledging, no tool results in this turn"),
        AssistantMessage(content=[TextBlock(text="Done.")], model="claude"),
        _result_message(stop_reason="end_turn", session_id="session-42"),
    ]
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert tracker.contents == ["Hello world"]
    assert tracker.results == []
    assert tracker.errors == []
    assert stop_reason == "end_turn"
    assert session_id == "session-42"


async def test_records_an_agent_error_instead_of_content_for_an_errored_read():
    messages = [
        AssistantMessage(
            content=[ToolUseBlock(id="read-1", name=READ_DOCUMENT_TOOL_NAME, input={})], model="claude"
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="read-1", content="boom", is_error=True)]),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert tracker.contents == []
    assert tracker.errors == [("content", "boom")]


async def test_captures_an_errored_extraction_tool_result_as_an_agent_error():
    messages = [
        AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tech-1",
                    name="mcp__candidate-skill-agent__extract_technical_skills",
                    input={},
                )
            ],
            model="claude",
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="tech-1", content="boom", is_error=True)]),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert tracker.errors == [("technical_skills", "boom")]
    assert tracker.results == []


async def test_ignores_an_errored_result_from_an_unrecognized_tool():
    messages = [
        AssistantMessage(
            content=[ToolUseBlock(id="search-1", name="ToolSearch", input={})], model="claude"
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="search-1", content="boom", is_error=True)]),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert tracker.contents == []
    assert tracker.results == []
    assert tracker.errors == []


async def test_records_an_agent_error_when_the_document_read_returns_empty_content():
    messages = [
        AssistantMessage(
            content=[ToolUseBlock(id="read-1", name=READ_DOCUMENT_TOOL_NAME, input={})], model="claude"
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="read-1", content=None, is_error=False)]),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert tracker.contents == []
    assert tracker.errors == [("content", "Document reader returned empty content.")]


async def test_extracts_a_plain_string_tool_result():
    messages = [
        AssistantMessage(
            content=[ToolUseBlock(id="read-1", name=READ_DOCUMENT_TOOL_NAME, input={})], model="claude"
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="read-1", content="raw text result", is_error=False)]),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert tracker.contents == ["raw text result"]


async def test_checkpoints_an_extraction_agent_result_under_its_redis_field():
    messages = [
        AssistantMessage(
            content=[
                ToolUseBlock(
                    id="soft-1",
                    name="mcp__candidate-skill-agent__extract_soft_skills",
                    input={},
                )
            ],
            model="claude",
        ),
        UserMessage(
            content=[ToolResultBlock(tool_use_id="soft-1", content='{"soft_skills": ["communication"]}')]
        ),
        _result_message(),
    ]
    tracker = _FakeTracker()

    await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert tracker.results == [("soft_skills", '{"soft_skills": ["communication"]}')]


async def test_result_message_with_is_error_is_still_reported():
    messages = [_result_message(is_error=True, stop_reason="error", session_id="session-err")]
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert stop_reason == "error"
    assert session_id == "session-err"


async def test_ignores_message_types_it_does_not_handle():
    messages = [
        SystemMessage(subtype="init", data={}),
        _result_message(stop_reason="end_turn", session_id="session-1"),
    ]
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert stop_reason == "end_turn"
    assert session_id == "session-1"


async def test_returns_all_none_for_an_empty_stream():
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(_StubClient([]), tracker, RESUME_PATH)

    assert (stop_reason, session_id) == (None, None)


async def test_last_result_message_wins_when_the_stream_has_more_than_one():
    messages = [
        _result_message(stop_reason="tool_use", session_id="first"),
        _result_message(stop_reason="end_turn", session_id="second"),
    ]
    tracker = _FakeTracker()

    stop_reason, session_id = await process_coordinator_stream(_StubClient(messages), tracker, RESUME_PATH)

    assert stop_reason == "end_turn"
    assert session_id == "second"
