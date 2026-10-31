"""Coordinator: reads a resume or job posting locally, structures it, and invokes parallel MCP agents with Redis tracking."""

from dataclasses import dataclass
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
from candidate_match_agent_cli.prompts import (
    JOB_POSTING_COORDINATOR_ORCHESTRATION_PROMPT,
    RESUME_COORDINATOR_ORCHESTRATION_PROMPT,
)
from candidate_match_agent_cli.settings import get_settings
from candidate_match_agent_cli.storage import (
    DocumentType,
    JobRedisField,
    JobStore,
)

from .message_stream_handler import process_coordinator_stream

logger = get_logger(__name__)
MODULE = "[Coordinator]"


@dataclass(frozen=True, slots=True)
class CoordinatorSpec:
    """Prompt and XML tag configuration per document type."""

    doc_type: DocumentType
    system_prompt: str
    content_tag: str
    formatted_tag: str


COORDINATOR_SPECS: dict[DocumentType, CoordinatorSpec] = {
    DocumentType.RESUME: CoordinatorSpec(
        doc_type=DocumentType.RESUME,
        system_prompt=RESUME_COORDINATOR_ORCHESTRATION_PROMPT,
        content_tag="resume_content",
        formatted_tag="formatted_resume",
    ),
    DocumentType.JOB_POSTING: CoordinatorSpec(
        doc_type=DocumentType.JOB_POSTING,
        system_prompt=JOB_POSTING_COORDINATOR_ORCHESTRATION_PROMPT,
        content_tag="job_posting_content",
        formatted_tag="formatted_job_posting",
    ),
}


def _read_non_empty_text(file_path: str) -> str:
    """Extracts text from `file_path` and raises ValueError if empty."""
    raw_text = extract_text(file_path)
    if not raw_text or not raw_text.strip():
        raise ValueError(f"Empty text extracted from {file_path}")
    return raw_text


async def run_coordinator(
    file_path: str,
    doc_type: DocumentType = DocumentType.RESUME,
) -> dict[str, Any]:
    """Reads `file_path`, dispatches parallel MCP agents, checkpoints to Redis, and unifies output."""
    settings = get_settings()
    agent_env = get_agent_environment(get_agent_settings())
    spec = COORDINATOR_SPECS[doc_type]

    async with JobStore(doc_type=doc_type) as tracker:
        guardrail = CoordinatorGuardrail(tracker=tracker, settings=settings)

        try:
            allowed_tools = await guardrail.pre_execution_hook(file_path)

            if allowed_tools:
                status = await tracker.get_status(file_path)
                prompt_parts = [
                    f"<document_type>{spec.doc_type.value}</document_type>"
                ]

                if not status.has_content:
                    try:
                        raw_text = _read_non_empty_text(file_path)
                    except ValueError:
                        await tracker.save_agent_error(
                            file_path,
                            JobRedisField.CONTENT,
                            "extract_text returned empty content.",
                        )
                        raise
                    prompt_parts.append(
                        f"<{spec.content_tag}>\n{raw_text}\n</{spec.content_tag}>"
                    )
                else:
                    # Si Redis ya tiene el contenido estructurado de una ejecución previa,
                    # lo pasamos en <existing_content> para saltar Fase 1 y alimentar Fase 2.
                    existing_text = (
                        getattr(status, "content", None)
                        or _read_non_empty_text(file_path)
                    )
                    prompt_parts.append(
                        f"<existing_content>\n{existing_text}\n</existing_content>"
                    )

                prompt_parts.append(
                    f"<pending_tools>{', '.join(allowed_tools)}</pending_tools>"
                )
                if doc_type == DocumentType.JOB_POSTING and status.missing_fields:
                    prompt_parts.append(
                        f"<missing_fields>{', '.join(status.missing_fields)}</missing_fields>"
                    )
                prompt = "\n".join(prompt_parts)

                options = ClaudeAgentOptions(
                    system_prompt=spec.system_prompt,
                    model=settings.coordinator_model,
                    env=agent_env.env,
                    setting_sources=[],
                    mcp_servers={
                        SKILL_AGENT_SERVER_NAME: get_skill_agent_mcp_server(settings)
                    },
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
                    doc_type.value,
                    file_path,
                    status.has_content,
                    allowed_tools,
                    status.missing_fields,
                )

                async with ClaudeSDKClient(options=options) as client:
                    await client.query(prompt)
                    stop_reason, session_id = await process_coordinator_stream(
                        client=client,
                        tracker=tracker,
                        resume_path=file_path,
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
