"""Consumes a coordinator turn's message stream and checkpoints each MCP tool result to Redis."""

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
from .job_tracker import RedisJobTracker

logger = get_logger(__name__)
MODULE = "[message_stream_handler]"

READ_DOCUMENT_TOOL_NAME = "mcp__file-reader__read_document"

# Map each distributed MCP tool name to its Redis Hash field name
EXTRACTION_TOOL_TO_FIELD: dict[str, str] = {
    "mcp__tech-skills-agent__extract_technical_skills": "technical_skills",
    "mcp__soft-skills-agent__extract_soft_skills": "soft_skills",
    "mcp__certs-agent__extract_certifications": "certifications",
    "mcp__lang-agent__extract_languages": "languages",
}


def _extract_text(content: str | list[dict[str, Any]] | None) -> str | None:
    """Flattens a tool result's `content` into plain text."""
    if content is None or isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if block.get("type") == "text")


async def process_coordinator_stream(
    client: ClaudeSDKClient,
    tracker: RedisJobTracker,
    resume_path: str,
) -> tuple[str | None, str | None]:
    """Drains `client.receive_response()`, persisting each tool result in Redis immediately.

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
                elif isinstance(block, ToolUseBlock):
                    tool_names_by_id[block.id] = block.name
                    logger.info(
                        "%s Dispatching MCP Tool id=%s name=%s",
                        MODULE, block.id, block.name,
                    )

        elif isinstance(message, UserMessage):
            content = message.content if isinstance(message.content, list) else []
            for block in content:
                if not isinstance(block, ToolResultBlock):
                    continue

                tool_name = tool_names_by_id.get(block.tool_use_id, "unknown")
                extracted_text = _extract_text(block.content) or ""

                if block.is_error:
                    logger.error(
                        "%s Tool error tool_use_id=%s name=%s error=%s",
                        MODULE, block.tool_use_id, tool_name, extracted_text,
                    )
                    if tool_name in EXTRACTION_TOOL_TO_FIELD:
                        field = EXTRACTION_TOOL_TO_FIELD[tool_name]
                        await tracker.save_agent_error(resume_path, field, extracted_text)
                    continue

                # 1. Checkpoint Document Read
                if tool_name == READ_DOCUMENT_TOOL_NAME:
                    await tracker.save_content(resume_path, extracted_text)

                # 2. Checkpoint any of the 4 Parallel Extraction Agents immediately
                elif tool_name in EXTRACTION_TOOL_TO_FIELD:
                    field = EXTRACTION_TOOL_TO_FIELD[tool_name]
                    await tracker.save_agent_result(resume_path, field, extracted_text)

        elif isinstance(message, ResultMessage):
            stop_reason = message.stop_reason
            session_id = message.session_id
            log = logger.error if message.is_error else logger.info
            log(
                "%s Turn finished | is_error=%s | stop_reason=%s | session_id=%s",
                MODULE, message.is_error, stop_reason, session_id,
            )

    return stop_reason, session_id
