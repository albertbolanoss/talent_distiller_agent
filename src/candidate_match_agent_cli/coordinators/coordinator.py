"""Coordinator: delegates reading a resume and invoking 4 parallel MCP agents with Redis tracking."""

import sys
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from labs_agent_lib import (
    get_agent_environment,
    get_agent_settings,
    get_logger,
)

from candidate_match_agent_cli.prompts import COORDINATOR_ORCHESTRATION_PROMPT
from candidate_match_agent_cli.settings import get_settings
from candidate_match_agent_cli.storage import RedisJobStore
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

from candidate_match_agent_cli.guardrails import CoordinatorGuardrail
from .message_stream_handler import process_coordinator_stream

logger = get_logger(__name__)
MODULE = "[Coordinator]"

ALL_MCP_SERVERS = {
    FILE_READER_SERVER_NAME: FILE_READER_SERVER,
    TECH_SKILLS_SERVER_NAME: TECH_SKILLS_SERVER,
    SOFT_SKILLS_SERVER_NAME: SOFT_SKILLS_SERVER,
    CERTS_SERVER_NAME: CERTS_SERVER,
    LANG_SERVER_NAME: LANG_SERVER,
}


async def run_coordinator(resume_path: str) -> dict[str, Any]:
    """Reads `resume_path`, dispatches 4 parallel MCP agents, checkpoints to Redis, and unifies output."""
    settings = get_settings()
    agent_env = get_agent_environment(get_agent_settings())

    async with RedisJobStore() as tracker:
        guardrail = CoordinatorGuardrail(tracker=tracker, settings=settings)

        try:
            allowed_tools = await guardrail.pre_execution_hook(resume_path)

            if allowed_tools:
                prompt = (
                    f"<resume_path>{resume_path}</resume_path>\n"
                    f"<pending_tools>{', '.join(allowed_tools)}</pending_tools>"
                )

                options = ClaudeAgentOptions(
                    system_prompt=COORDINATOR_ORCHESTRATION_PROMPT,
                    model=settings.coordinator_model,
                    env=agent_env.env,
                    setting_sources=[],
                    mcp_servers=ALL_MCP_SERVERS,
                    allowed_tools=allowed_tools,
                    hooks=guardrail.build_sdk_hooks(resume_path),
                )

                logger.info(
                    "%s resume_path=%s | allowed_tools=%s",
                    MODULE,
                    resume_path,
                    allowed_tools,
                )

                async with ClaudeSDKClient(options=options) as client:
                    await client.query(prompt)
                    stop_reason, session_id = await process_coordinator_stream(
                        client=client,
                        tracker=tracker,
                        resume_path=resume_path,
                    )

                await guardrail.post_execution_hook(
                    resume_path=resume_path,
                    session_id=session_id,
                    stop_reason=stop_reason,
                )

        except Exception as exc:
            logger.exception("%s Error processing %s: %s", MODULE, resume_path, exc)

        unified_result = await tracker.unify_by_filename(resume_path)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return unified_result.model_dump()
