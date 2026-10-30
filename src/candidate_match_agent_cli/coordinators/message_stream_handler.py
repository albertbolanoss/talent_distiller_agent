"""Consumes a coordinator turn's message stream and checkpoints structured content and MCP tool results to Redis."""

import json
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
from candidate_match_agent_cli.storage import (
    DESIRABLE_PREFIX,
    DocumentType,
    JobRedisField,
    RedisJobStore,
)

logger = get_logger(__name__)
MODULE = "[message_stream_handler]"

_FORMATTED_CONTENT_PATTERN = re.compile(
    r"<formatted_(?:resume|job_posting)>(.*?)</formatted_(?:resume|job_posting)>",
    re.DOTALL,
)


def _extract_text(content: str | list[dict[str, Any]] | None) -> str:
    """Flattens a tool result's `content` into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "".join(block.get("text", "") for block in content if block.get("type") == "text")


def _extract_formatted_content(text: str) -> str | None:
    """Extracts structured content inside `<formatted_resume>` or `<formatted_job_posting>` tags."""
    match = _FORMATTED_CONTENT_PATTERN.search(text)
    return match.group(1).strip() if match else None


def _is_desirable_tool_input(tool_input: Any) -> bool:
    """Detects if a ToolUseBlock input explicitly targets desirable requirements."""
    if not isinstance(tool_input, dict):
        return False
    if tool_input.get("is_desirable") is True or tool_input.get("desirable") is True:
        return True
    for key in ("type", "category", "requirement_type", "section", "kind"):
        val = str(tool_input.get(key, "")).lower()
        if "desir" in val or "deseable" in val or "nice_to_have" in val or "optional" in val:
            return True
    return False


async def _resolve_target_field(
    tracker: RedisJobStore,
    file_path: str,
    base_field: str,
    tool_input: Any,
    assigned_fields_in_turn: set[str],
) -> str:
    """Resolves whether a tool invocation maps to `<field>` or `desirable_<field>`."""
    if tracker.doc_type != DocumentType.JOB_POSTING:
        return base_field

    desirable_field = f"{DESIRABLE_PREFIX}{base_field}"

    if _is_desirable_tool_input(tool_input):
        assigned_fields_in_turn.add(desirable_field)
        return desirable_field

    status = await tracker.get_status(file_path)
    if base_field in status.missing_fields and base_field not in assigned_fields_in_turn:
        assigned_fields_in_turn.add(base_field)
        return base_field

    assigned_fields_in_turn.add(desirable_field)
    return desirable_field


async def _save_tool_output(
    tracker: RedisJobStore,
    file_path: str,
    target_field: str,
    base_field: str,
    extracted_text: str,
) -> None:
    """Persists tool output, splitting mandatory and desirable keys if returned in a single composite JSON."""
    if tracker.doc_type == DocumentType.JOB_POSTING:
        try:
            parsed = json.loads(extracted_text)
            if isinstance(parsed, dict) and "desirable" in parsed and (
                "mandatory" in parsed or "required" in parsed
            ):
                mandatory_data = parsed.get("mandatory", parsed.get("required"))
                desirable_data = parsed.get("desirable")
                await tracker.save_agent_result(
                    file_path, base_field, json.dumps(mandatory_data)
                )
                await tracker.save_agent_result(
                    file_path,
                    f"{DESIRABLE_PREFIX}{base_field}",
                    json.dumps(desirable_data),
                )
                return
        except json.JSONDecodeError:
            pass

    await tracker.save_agent_result(file_path, target_field, extracted_text)


async def process_coordinator_stream(
    client: ClaudeSDKClient,
    tracker: RedisJobStore,
    resume_path: str,
) -> tuple[str | None, str | None]:
    """Drains `client.receive_response()`, persisting formatted content and each tool result in Redis.

    Returns `(stop_reason, session_id)`.
    """
    stop_reason: str | None = None
    session_id: str | None = None
    tool_calls_by_id: dict[str, tuple[str, str]] = {}  # tool_use_id -> (tool_name, target_field)
    assigned_fields_in_turn: set[str] = set()

    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    logger.debug("%s Assistant text: %s", MODULE, block.text)
                    formatted_content = _extract_formatted_content(block.text)
                    if formatted_content is not None:
                        if formatted_content:
                            await tracker.save_content(resume_path, formatted_content)
                            logger.info(
                                "%s Saved formatted %s content to Redis for path=%s",
                                MODULE,
                                tracker.doc_type,
                                resume_path,
                            )
                        else:
                            await tracker.save_agent_error(
                                resume_path,
                                JobRedisField.CONTENT,
                                f"Coordinator returned an empty formatted {tracker.doc_type} block.",
                            )

                elif isinstance(block, ToolUseBlock):
                    target_field = "unknown"
                    if block.name in EXTRACTION_TOOL_TO_FIELD:
                        base_field = EXTRACTION_TOOL_TO_FIELD[block.name]
                        target_field = await _resolve_target_field(
                            tracker=tracker,
                            file_path=resume_path,
                            base_field=base_field,
                            tool_input=getattr(block, "input", None),
                            assigned_fields_in_turn=assigned_fields_in_turn,
                        )
                    tool_calls_by_id[block.id] = (block.name, target_field)
                    logger.info(
                        "%s Dispatching MCP Tool id=%s name=%s target_field=%s",
                        MODULE,
                        block.id,
                        block.name,
                        target_field,
                    )

        elif isinstance(message, UserMessage):
            content = message.content if isinstance(message.content, list) else []
            for block in content:
                if not isinstance(block, ToolResultBlock):
                    continue

                tool_name, target_field = tool_calls_by_id.get(
                    block.tool_use_id, ("unknown", "unknown")
                )
                extracted_text = _extract_text(block.content)

                if block.is_error:
                    logger.error(
                        "%s Tool error tool_use_id=%s name=%s field=%s error=%s",
                        MODULE,
                        block.tool_use_id,
                        tool_name,
                        target_field,
                        extracted_text,
                    )
                    if tool_name in EXTRACTION_TOOL_TO_FIELD:
                        await tracker.save_agent_error(resume_path, target_field, extracted_text)
                    continue

                if tool_name in EXTRACTION_TOOL_TO_FIELD:
                    base_field = EXTRACTION_TOOL_TO_FIELD[tool_name]
                    await _save_tool_output(
                        tracker=tracker,
                        file_path=resume_path,
                        target_field=target_field,
                        base_field=base_field,
                        extracted_text=extracted_text,
                    )

        elif isinstance(message, ResultMessage):
            stop_reason = message.stop_reason
            session_id = message.session_id
            log = logger.error if message.is_error else logger.info
            log(
                "%s Turn finished | doc_type=%s | is_error=%s | stop_reason=%s | session_id=%s",
                MODULE,
                tracker.doc_type,
                message.is_error,
                stop_reason,
                session_id,
            )

    return stop_reason, session_id
