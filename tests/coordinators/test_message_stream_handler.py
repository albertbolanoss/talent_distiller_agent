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

from candidate_match_agent.coordinators.message_stream_handler import (
    READ_DOCUMENT_TOOL_NAME,
    process_coordinator_stream,
)


class _StubClient:
    """Replays a fixed list of messages as the stream `process_coordinator_stream` drains."""

    def __init__(self, messages: list) -> None:
        self._messages = messages

    async def receive_response(self) -> AsyncIterator:
        for message in self._messages:
            yield message


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

    content, stop_reason, session_id = await process_coordinator_stream(_StubClient(messages))

    assert content == "Hello world"
    assert stop_reason == "end_turn"
    assert session_id == "session-42"


async def test_does_not_capture_content_from_an_errored_tool_result():
    messages = [
        AssistantMessage(
            content=[ToolUseBlock(id="read-1", name=READ_DOCUMENT_TOOL_NAME, input={})], model="claude"
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="read-1", content="boom", is_error=True)]),
        _result_message(),
    ]

    content, _, _ = await process_coordinator_stream(_StubClient(messages))

    assert content is None


async def test_extracts_a_plain_string_tool_result():
    messages = [
        AssistantMessage(
            content=[ToolUseBlock(id="read-1", name=READ_DOCUMENT_TOOL_NAME, input={})], model="claude"
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id="read-1", content="raw text result", is_error=False)]),
        _result_message(),
    ]

    content, _, _ = await process_coordinator_stream(_StubClient(messages))

    assert content == "raw text result"


async def test_result_message_with_is_error_is_still_reported():
    messages = [_result_message(is_error=True, stop_reason="error", session_id="session-err")]

    content, stop_reason, session_id = await process_coordinator_stream(_StubClient(messages))

    assert content is None
    assert stop_reason == "error"
    assert session_id == "session-err"


async def test_ignores_message_types_it_does_not_handle():
    messages = [
        SystemMessage(subtype="init", data={}),
        _result_message(stop_reason="end_turn", session_id="session-1"),
    ]

    content, stop_reason, session_id = await process_coordinator_stream(_StubClient(messages))

    assert content is None
    assert stop_reason == "end_turn"
    assert session_id == "session-1"


async def test_returns_all_none_for_an_empty_stream():
    content, stop_reason, session_id = await process_coordinator_stream(_StubClient([]))

    assert (content, stop_reason, session_id) == (None, None, None)


async def test_last_result_message_wins_when_the_stream_has_more_than_one():
    messages = [
        _result_message(stop_reason="tool_use", session_id="first"),
        _result_message(stop_reason="end_turn", session_id="second"),
    ]

    _, stop_reason, session_id = await process_coordinator_stream(_StubClient(messages))

    assert stop_reason == "end_turn"
    assert session_id == "second"
