"""Consumes a coordinator turn's message stream, logging each stage as it arrives."""

from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from labs_agent_lib import get_logger

logger = get_logger(__name__)
MODULE = "[message_stream_handler]"

READ_DOCUMENT_TOOL_NAME = "mcp__file-reader__read_document"


def _extract_text(content: str | list[dict[str, Any]] | None) -> str | None:
    """Flattens a tool result's `content` (string or content-block list) into plain text."""
    if content is None or isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if block.get("type") == "text")


async def process_coordinator_stream(
    client: ClaudeSDKClient,
) -> tuple[str | None, str | None, str | None]:
    """Drains `client.receive_response()`, logging each stage and capturing `read_document`'s result.

    The document content is read straight from the tool's result rather than from the model's final
    answer, so the model never has to re-generate the whole document as output tokens.

    Returns `(document_content, stop_reason, session_id)`.
    """
    document_content: str | None = None
    stop_reason: str | None = None
    session_id: str | None = None
    tool_names_by_id: dict[str, str] = {}

    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    logger.debug("%s Assistant text: %s", MODULE, block.text)
                elif isinstance(block, ToolUseBlock):
                    tool_names_by_id[block.id] = block.name
                    logger.debug(
                        "%s Tool use requested id=%s name=%s input=%s",
                        MODULE, block.id, block.name, block.input,
                    )

        elif isinstance(message, UserMessage):
            content = message.content if isinstance(message.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock):
                    logger.debug(
                        "%s Tool result tool_use_id=%s is_error=%s content=%s",
                        MODULE, block.tool_use_id, block.is_error, block.content,
                    )
                    if not block.is_error and tool_names_by_id.get(block.tool_use_id) == READ_DOCUMENT_TOOL_NAME:
                        document_content = _extract_text(block.content)

        elif isinstance(message, ResultMessage):
            stop_reason = message.stop_reason
            session_id = message.session_id
            log = logger.error if message.is_error else logger.debug
            log(
                "%s Turn finished | is_error=%s | stop_reason=%s | session_id=%s",
                MODULE, message.is_error, stop_reason, session_id,
            )

    return document_content, stop_reason, session_id
