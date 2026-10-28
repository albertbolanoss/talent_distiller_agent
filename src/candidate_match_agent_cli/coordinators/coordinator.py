"""Coordinator: delegates reading a resume and invoking 4 parallel MCP agents with Redis tracking."""

import asyncio
import sys

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from labs_agent_lib import get_logger, get_settings, get_agent_environment
from candidate_match_agent_cli.tools import (
    CERTS_SERVER,
    CERTS_SERVER_NAME,
    FILE_READER_SERVER,
    FILE_READER_SERVER_NAME,
    LANG_SERVER,
    LANG_SERVER_NAME,
    SOFT_SKILLS_SERVER,
    SOFT_SKILLS_SERVER_NAME,
    TECH_SKILLS_SERVER,
    TECH_SKILLS_SERVER_NAME,
)
from candidate_match_agent_cli.prompts import COORDINATOR_ORCHESTRATION_PROMPT

from .job_tracker import RedisJobTracker
from .message_stream_handler import (
    READ_DOCUMENT_TOOL_NAME,
    process_coordinator_stream,
)

logger = get_logger(__name__)
MODULE = "[Coordinator]"

FIELD_TO_MCP_TOOL: dict[str, str] = {
    "technical_skills": f"mcp__{TECH_SKILLS_SERVER_NAME}__extract_technical_skills",
    "soft_skills": f"mcp__{SOFT_SKILLS_SERVER_NAME}__extract_soft_skills",
    "certifications": f"mcp__{CERTS_SERVER_NAME}__extract_certifications",
    "languages": f"mcp__{LANG_SERVER_NAME}__extract_languages",
}

ALL_MCP_SERVERS = {
    FILE_READER_SERVER_NAME: FILE_READER_SERVER,
    TECH_SKILLS_SERVER_NAME: TECH_SKILLS_SERVER,
    SOFT_SKILLS_SERVER_NAME: SOFT_SKILLS_SERVER,
    CERTS_SERVER_NAME: CERTS_SERVER,
    LANG_SERVER_NAME: LANG_SERVER,
}


async def run_coordinator(
    model: str,
    resume_path: str,
    max_retries: int = 3,
) -> dict:
    """Reads `resume_path`, dispatches 4 parallel MCP agents, checkpoints to Redis, and unifies output."""
    settings = get_settings()
    agent_env = get_agent_environment(settings)

    tracker = RedisJobTracker()

    try:
        for attempt in range(1, max_retries + 1):
            try:
                needs_read, missing_fields, _ = await tracker.get_missing_requirements(resume_path)

                if not needs_read and not missing_fields:
                    logger.info("%s All fields already checkpointed in Redis for %s", MODULE, resume_path)
                    break

                allowed_tools: list[str] = []
                if needs_read:
                    allowed_tools.append(READ_DOCUMENT_TOOL_NAME)
                for field in missing_fields:
                    allowed_tools.append(FIELD_TO_MCP_TOOL[field])

                prompt = (
                    f"<resume_path>{resume_path}</resume_path>\n"
                    f"<pending_tools>{', '.join(allowed_tools)}</pending_tools>"
                )

                options = ClaudeAgentOptions(
                    system_prompt=COORDINATOR_ORCHESTRATION_PROMPT,
                    model=model,
                    env=agent_env.env,
                    setting_sources=[],
                    mcp_servers=ALL_MCP_SERVERS,
                    allowed_tools=allowed_tools,
                )

                logger.info(
                    "%s Attempt %d/%d | resume_path=%s | allowed_tools=%s",
                    MODULE, attempt, max_retries, resume_path, allowed_tools,
                )

                async with ClaudeSDKClient(options=options) as client:
                    await client.query(prompt)
                    stop_reason, session_id = await process_coordinator_stream(
                        client=client,
                        tracker=tracker,
                        resume_path=resume_path,
                    )

                status, still_missing = await tracker.update_session_and_status(resume_path, session_id)
                logger.info(
                    "%s Attempt %d finished | stop_reason=%s | status=%s | session_id=%s | still_missing=%s",
                    MODULE, attempt, stop_reason, status, session_id, still_missing,
                )

                if status == "COMPLETED":
                    break

            except Exception as exc:
                logger.exception("%s Error on attempt %d/%d: %s", MODULE, attempt, max_retries, exc)

            if attempt < max_retries:
                backoff = 2 ** (attempt - 1)
                logger.info("%s Retrying missing agents in %ds...", MODULE, backoff)
                await asyncio.sleep(backoff)

        unified_result = await tracker.unify_by_filename(resume_path)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return unified_result.model_dump()

    finally:
        await tracker.close()