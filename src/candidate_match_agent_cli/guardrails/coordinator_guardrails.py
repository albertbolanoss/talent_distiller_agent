"""Guardrails and SDK hooks for validating coordinator state and tool execution."""

from claude_agent_sdk import HookMatcher
from claude_agent_sdk.types import HookContext, HookInput, HookJSONOutput
from labs_agent_lib import file_writer, get_logger

from candidate_match_agent_cli.settings import Settings
from candidate_match_agent_cli.storage import RedisJobStore
from candidate_match_agent_cli.tools import (
    EXTRACTION_TOOL_TO_FIELD,
    READ_DOCUMENT_TOOL_NAME,
)

logger = get_logger(__name__)
MODULE = "[CoordinatorGuardrail]"

FIELD_TO_MCP_TOOL: dict[str, str] = {
    field: tool_name for tool_name, field in EXTRACTION_TOOL_TO_FIELD.items()
}


class CoordinatorGuardrail:
    """Enforces pre-flight, in-flight (SDK PreToolUse hook), and post-flight rules."""

    def __init__(self, tracker: RedisJobStore, settings: Settings) -> None:
        self.tracker = tracker
        self.settings = settings

    async def pre_execution_hook(self, resume_path: str) -> list[str]:
        """Validates job state before launching Claude and returns allowed tools."""
        status = await self.tracker.get_status(resume_path)

        if status.is_completed:
            logger.info(
                "%s All fields already checkpointed for %s - marking processed",
                MODULE,
                resume_path,
            )
            await self.tracker.save_session_and_completion(resume_path, is_completed=True)
            file_writer(resume_path, self.settings.coordinator_processed_folder)
            return []

        revision_number = await self.tracker.increment_attempts(resume_path)
        max_revisions = self.settings.coordinator_max_revision_number

        if revision_number > max_revisions:
            logger.error(
                "%s %s exceeded max revision number (%d/%d) - marking failed",
                MODULE,
                resume_path,
                revision_number,
                max_revisions,
            )
            file_writer(resume_path, self.settings.coordinator_failed_folder)
            return []

        allowed_tools: list[str] = []
        if not status.has_content:
            allowed_tools.append(READ_DOCUMENT_TOOL_NAME)
        allowed_tools.extend(FIELD_TO_MCP_TOOL[field] for field in status.missing_fields)

        return allowed_tools

    async def post_execution_hook(
        self,
        resume_path: str,
        session_id: str | None,
        stop_reason: str | None = None,
    ) -> None:
        """Evaluates final state after stream completion, updates Redis, and routes file."""
        status = await self.tracker.get_status(resume_path)
        is_max_revision = status.revision_number >= self.settings.coordinator_max_revision_number

        await self.tracker.save_session_and_completion(
            resume_path=resume_path,
            is_completed=status.is_completed,
            session_id=session_id,
        )

        logger.debug(
            "%s Finished | stop_reason=%s | is_completed=%s | session_id=%s | revision=%d/%d",
            MODULE,
            stop_reason,
            status.is_completed,
            session_id,
            status.revision_number,
            self.settings.coordinator_max_revision_number,
        )

        if status.is_completed:
            logger.info(
                "%s Completed extraction for %s - marking processed",
                MODULE,
                resume_path,
            )
            file_writer(resume_path, self.settings.coordinator_processed_folder)
        elif is_max_revision:
            logger.error(
                "%s %s reached max revisions (%d) without completing - marking failed",
                MODULE,
                resume_path,
                self.settings.coordinator_max_revision_number,
            )
            file_writer(resume_path, self.settings.coordinator_failed_folder)

    def build_sdk_hooks(self, resume_path: str) -> dict[str, list[HookMatcher]]:
        """Builds native Claude Agent SDK PreToolUse hooks bound to `resume_path`."""

        async def _validate_tool_use(
            input_data: HookInput,
            tool_use_id: str | None,
            context: HookContext,
        ) -> HookJSONOutput:
            tool_name = str(input_data.get("tool_name", ""))
            target_field = EXTRACTION_TOOL_TO_FIELD[tool_name]
            
            status = await self.tracker.get_status(resume_path)

            if not status.has_content:
                reason = (
                    f"Cannot execute {tool_name}: resume content is not in Redis yet. "
                    f"Execute {READ_DOCUMENT_TOOL_NAME} first."
                )
                logger.warning("%s Guardrail blocked %s: %s", MODULE, tool_name, reason)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }

            if target_field not in status.missing_fields:
                reason = f"Field '{target_field}' is already checkpointed in Redis."
                logger.info("%s Guardrail skipped duplicate call to %s", MODULE, tool_name)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }

            return {}

        # explicitly filter so that the hook applies only to extraction agents
        target_tools = "|".join(EXTRACTION_TOOL_TO_FIELD.keys())

        return {
            "PreToolUse": [
                HookMatcher(
                    matcher=target_tools,
                    hooks=[_validate_tool_use]
                )
            ],
        }
