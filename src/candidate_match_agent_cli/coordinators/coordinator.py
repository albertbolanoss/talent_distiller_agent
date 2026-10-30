"""Coordinator: reads a resume locally, structures it, and invokes 4 parallel MCP agents with Redis tracking."""

import sys
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from labs_agent_lib import (
    extract_text,
    get_agent_environment,
    get_agent_settings,
    get_logger,
)

from candidate_match_agent_cli.guardrails import CoordinatorGuardrail
from candidate_match_agent_cli.mcp_client import (
    SKILL_AGENT_SERVER_NAME,
    get_skill_agent_mcp_server,
)
from candidate_match_agent_cli.prompts import RESUME_COORDINATOR_ORCHESTRATION_PROMPT
from candidate_match_agent_cli.settings import get_settings
from candidate_match_agent_cli.storage import JobRedisField, RedisJobStore

from .message_stream_handler import process_coordinator_stream

logger = get_logger(__name__)
MODULE = "[Coordinator]"


async def run_coordinator(resume_path: str) -> dict[str, Any]:
    """Reads `resume_path`, dispatches 4 parallel MCP agents, checkpoints to Redis, and unifies output."""
    settings = get_settings()
    agent_env = get_agent_environment(get_agent_settings())

    async with RedisJobStore() as tracker:
        guardrail = CoordinatorGuardrail(tracker=tracker, settings=settings)

        try:
            allowed_tools = await guardrail.pre_execution_hook(resume_path)

            if allowed_tools:
                status = await tracker.get_status(resume_path)
                prompt_parts = [f"<resume_path>{resume_path}</resume_path>"]

                if not status.has_content:
                    raw_text = extract_text(resume_path)
                    if not raw_text or not raw_text.strip():
                        await tracker.save_agent_error(
                            resume_path,
                            JobRedisField.CONTENT,
                            "extract_text returned empty content.",
                        )
                        raise ValueError(f"Empty text extracted from {resume_path}")
                    prompt_parts.append(f"<resume_content>\n{raw_text}\n</resume_content>")

                prompt_parts.append(f"<pending_tools>{', '.join(allowed_tools)}</pending_tools>")
                prompt = "\n".join(prompt_parts)

                options = ClaudeAgentOptions(
                    system_prompt=RESUME_COORDINATOR_ORCHESTRATION_PROMPT,
                    model=settings.coordinator_model,
                    env=agent_env.env,
                    setting_sources=[],
                    mcp_servers={SKILL_AGENT_SERVER_NAME: get_skill_agent_mcp_server(settings)},
                    allowed_tools=allowed_tools,
                    hooks=guardrail.build_sdk_hooks(resume_path),
                )

                logger.info(
                    "%s resume_path=%s | has_content=%s | allowed_tools=%s",
                    MODULE,
                    resume_path,
                    status.has_content,
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