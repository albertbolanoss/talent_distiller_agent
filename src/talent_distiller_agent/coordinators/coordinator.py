"""Coordinator: reads a resume or job posting locally, structures it, and invokes parallel MCP agents with Redis tracking."""

from dataclasses import dataclass
import sys
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from labs_agent_lib import (
    AgentTranscriptWriter,
    PromptLogWriter,
    extract_text,
    get_agent_environment,
    get_agent_settings,
    get_logger,
)

from talent_distiller_agent.guardrails import CoordinatorGuardrail
from talent_distiller_agent.mcp_client import get_skill_agent_mcp_servers
from talent_distiller_agent.prompts import (
    JOB_POSTING_COORDINATOR_ORCHESTRATION_PROMPT,
    RESUME_COORDINATOR_ORCHESTRATION_PROMPT,
)
from talent_distiller_agent.settings import get_settings
from talent_distiller_agent.storage import (
    DocumentType,
    JobRedisField,
    RedisJobStore,
)

from .message_stream_handler import AGENT_NAME, process_coordinator_stream

logger = get_logger(__name__)
MODULE = "[Coordinator]"
SERVICE_NAME = "talent_distiller_agent"


@dataclass(frozen=True, slots=True)
class CoordinatorSpec:
    """Prompt and XML tag configuration per document type."""

    doc_type: DocumentType
    system_prompt: str
    system_prompt_name: str
    path_tag: str
    content_tag: str
    formatted_tag: str


COORDINATOR_SPECS: dict[DocumentType, CoordinatorSpec] = {
    DocumentType.RESUME: CoordinatorSpec(
        doc_type=DocumentType.RESUME,
        system_prompt=RESUME_COORDINATOR_ORCHESTRATION_PROMPT,
        system_prompt_name="resume_coordinator_orchestration",
        path_tag="resume_path",
        content_tag="resume_content",
        formatted_tag="formatted_resume",
    ),
    DocumentType.JOB_POSTING: CoordinatorSpec(
        doc_type=DocumentType.JOB_POSTING,
        system_prompt=JOB_POSTING_COORDINATOR_ORCHESTRATION_PROMPT,
        system_prompt_name="job_posting_coordinator_orchestration",
        path_tag="job_posting_path",
        content_tag="job_posting_content",
        formatted_tag="formatted_job_posting",
    ),
}


async def run_coordinator(
    file_path: str,
    doc_type: DocumentType = DocumentType.RESUME,
) -> dict[str, Any]:
    """Reads `file_path`, dispatches parallel MCP agents, checkpoints to Redis, and unifies output."""
    settings = get_settings()
    agent_env = get_agent_environment(get_agent_settings())
    spec = COORDINATOR_SPECS[doc_type]

    async with RedisJobStore(doc_type=doc_type) as tracker:
        guardrail = CoordinatorGuardrail(tracker=tracker, settings=settings)

        try:
            allowed_tools = await guardrail.pre_execution_hook(file_path)

            if allowed_tools:
                status = await tracker.get_status(file_path)
                prompt_parts = [
                    f"<{spec.path_tag}>{file_path}</{spec.path_tag}>",
                    f"<correlation_id>{status.correlation_id or ''}</correlation_id>",
                ]

                if not status.has_content:
                    raw_text = extract_text(file_path)
                    if not raw_text or not raw_text.strip():
                        await tracker.save_agent_error(
                            file_path,
                            JobRedisField.CONTENT,
                            "extract_text returned empty content.",
                        )
                        raise ValueError(f"Empty text extracted from {file_path}")
                    prompt_parts.append(
                        f"<{spec.content_tag}>\n{raw_text}\n</{spec.content_tag}>"
                    )

                prompt_parts.append(f"<pending_tools>{', '.join(allowed_tools)}</pending_tools>")
                if doc_type == DocumentType.JOB_POSTING:
                    prompt_parts.append(
                        f"<missing_fields>{', '.join(status.missing_fields)}</missing_fields>"
                    )
                prompt = "\n".join(prompt_parts)

                options = ClaudeAgentOptions(
                    system_prompt=spec.system_prompt,
                    model=settings.coordinator_model,
                    env={
                        **agent_env.env,
                        "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT": str(
                            settings.coordinator_mcp_tool_idle_timeout_ms
                        ),
                    },
                    setting_sources=[],
                    mcp_servers=get_skill_agent_mcp_servers(settings),
                    allowed_tools=allowed_tools,
                    tools=[],
                    hooks=guardrail.build_sdk_hooks(
                        file_path,
                        formatted_tag=spec.formatted_tag,
                    ),
                )

                logger.info(
                    "%s doc_type=%s | path=%s | has_content=%s | allowed_tools=%s | missing_fields=%s",
                    MODULE,
                    doc_type,
                    file_path,
                    status.has_content,
                    allowed_tools,
                    status.missing_fields,
                )

                correlation_id = status.correlation_id or ""
                prompt_log = PromptLogWriter(settings, service=SERVICE_NAME)
                transcript = AgentTranscriptWriter(settings, service=SERVICE_NAME)
                prompt_log.log_prompt(
                    correlation_id=correlation_id,
                    agent=AGENT_NAME,
                    model=settings.coordinator_model,
                    system_prompt_name=spec.system_prompt_name,
                    user_prompt=prompt,
                )
                transcript.session_start(
                    correlation_id,
                    AGENT_NAME,
                    model=settings.coordinator_model,
                    system_prompt=spec.system_prompt,
                    user_prompt=prompt,
                    allowed_tools=allowed_tools,
                )

                async with ClaudeSDKClient(options=options) as client:
                    await client.query(prompt)
                    stop_reason, session_id = await process_coordinator_stream(
                        client=client,
                        tracker=tracker,
                        resume_path=file_path,
                        correlation_id=correlation_id,
                        transcript=transcript,
                    )

                await guardrail.post_execution_hook(
                    file_path=file_path,
                    session_id=session_id,
                    stop_reason=stop_reason,
                )

        except Exception as exc:
            logger.exception(
                "%s Error processing %s (%s): %s",
                MODULE,
                file_path,
                doc_type,
                exc,
            )

        unified_result = await tracker.unify_by_filename(file_path)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        return unified_result.model_dump()


async def run_resume_coordinator(resume_path: str) -> dict[str, Any]:
    """Convenience entrypoint for resume extraction."""
    return await run_coordinator(resume_path, doc_type=DocumentType.RESUME)


async def run_job_posting_coordinator(job_posting_path: str) -> dict[str, Any]:
    """Convenience entrypoint for job posting extraction."""
    return await run_coordinator(job_posting_path, doc_type=DocumentType.JOB_POSTING)
