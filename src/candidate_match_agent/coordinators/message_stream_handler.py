"""Consumes a coordinator turn's message stream, logging each stage as it arrives."""

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from candidate_match_agent.libs import get_logger

logger = get_logger(__name__)
MODULE = "[message_stream_handler]"


async def process_coordinator_stream(
    client: ClaudeSDKClient,
) -> tuple[str | None, str | None, str | None]:
    """Drains `client.receive_response()`, logging each stage of the turn as it arrives.

    Returns `(final_result, stop_reason, session_id)` from the turn's `ResultMessage`.
    """
    final_result: str | None = None
    stop_reason: str | None = None
    session_id: str | None = None

    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    logger.debug("%s Assistant text: %s", MODULE, block.text)
                elif isinstance(block, ToolUseBlock):
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

        elif isinstance(message, ResultMessage):
            final_result = message.result
            stop_reason = message.stop_reason
            session_id = message.session_id
            log = logger.error if message.is_error else logger.debug
            log(
                "%s Turn finished | is_error=%s | stop_reason=%s | session_id=%s",
                MODULE, message.is_error, stop_reason, session_id,
            )

    return final_result, stop_reason, session_id
