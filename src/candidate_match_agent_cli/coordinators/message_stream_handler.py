"""Consumes a coordinator turn's message stream and checkpoints structured content and MCP tool results to Redis."""

import re
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

from candidate_match_agent_cli.mcp_client import EXTRACTION_TOOL_TO_FIELD
from candidate_match_agent_cli.storage import JobRedisField, RedisJobStore

logger = get_logger(__name__)
MODULE = "[message_stream_handler]"

_FORMATTED_RESUME_PATTERN = re.compile(
    r"<formatted_resume>(.*?)</formatted_resume>",
    re.DOTALL,
)


def _extract_text(content: str | list[dict[str, Any]] | None) -> str:
    """Flattens a tool result's `content` into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if block.get("type") == "text")


def _extract_formatted_resume(text: str) -> str | None:
    """Extracts the structured resume inside `<formatted_resume>` tags if present."""
    match = _FORMATTED_RESUME_PATTERN.search(text)
    return match.group(1).strip() if match else None


async def process_coordinator_stream(
    client: ClaudeSDKClient,
    tracker: RedisJobStore,
    resume_path: str,
) -> tuple[str | None, str | None]:
    """Drains `client.receive_response()`, persisting formatted resume content and each tool result in Redis.

    Returns `(stop_reason, session_id)`.
    """
    stop_reason: str | None = None
    session_id: str | None = None
    tool_names_by_id: dict[str, str] = {}

    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    logger.debug("%s Assistant text: %s", MODULE, block.text)
                    formatted_resume = _extract_formatted_resume(block.text)
                    if formatted_resume is not None:
                        if formatted_resume:
                            await tracker.save_content(resume_path, formatted_resume)
                            logger.info(
                                "%s Saved formatted resume content to Redis for path=%s",
                                MODULE,
                                resume_path,
                            )
                        else:
                            await tracker.save_agent_error(
                                resume_path,
                                JobRedisField.CONTENT,
                                "Coordinator returned an empty <formatted_resume> block.",
                            )

                elif isinstance(block, ToolUseBlock):
                    tool_names_by_id[block.id] = block.name
                    logger.info(
                        "%s Dispatching MCP Tool id=%s name=%s",
                        MODULE,
                        block.id,
                        block.name,
                    )

        elif isinstance(message, UserMessage):
            content = message.content if isinstance(message.content, list) else []
            for block in content:
                if not isinstance(block, ToolResultBlock):
                    continue

                tool_name = tool_names_by_id.get(block.tool_use_id, "unknown")
                extracted_text = _extract_text(block.content)

                if block.is_error:
                    logger.error(
                        "%s Tool error tool_use_id=%s name=%s error=%s",
                        MODULE,
                        block.tool_use_id,
                        tool_name,
                        extracted_text,
                    )
                    if tool_name in EXTRACTION_TOOL_TO_FIELD:
                        field = EXTRACTION_TOOL_TO_FIELD[tool_name]
                        await tracker.save_agent_error(resume_path, field, extracted_text)
                    continue

                # Checkpoint any of the Parallel Extraction Agents immediately
                if tool_name in EXTRACTION_TOOL_TO_FIELD:
                    field = EXTRACTION_TOOL_TO_FIELD[tool_name]
                    await tracker.save_agent_result(resume_path, field, extracted_text)

        elif isinstance(message, ResultMessage):
            stop_reason = message.stop_reason
            session_id = message.session_id
            log = logger.error if message.is_error else logger.info
            log(
                "%s Turn finished | is_error=%s | stop_reason=%s | session_id=%s",
                MODULE,
                message.is_error,
                stop_reason,
                session_id,
            )

    return stop_reason, session_id
