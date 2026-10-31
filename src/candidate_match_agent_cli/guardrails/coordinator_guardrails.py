"""Guardrails and SDK hooks for validating coordinator state and tool execution."""

from claude_agent_sdk import HookCallback, HookContext, HookInput, HookJSONOutput, HookMatcher
from labs_agent_lib import file_writer, get_logger

from candidate_match_agent_cli.mcp_client import EXTRACTION_TOOL_TO_FIELD
from candidate_match_agent_cli.settings import Settings
from candidate_match_agent_cli.storage import DESIRABLE_PREFIX, DocumentType, JobStore

logger = get_logger(__name__)
MODULE = "[CoordinatorGuardrail]"

FIELD_TO_MCP_TOOL: dict[str, str] = {
    **{field: tool_name for tool_name, field in EXTRACTION_TOOL_TO_FIELD.items()},
    **{
        f"{DESIRABLE_PREFIX}{field}": tool_name
        for tool_name, field in EXTRACTION_TOOL_TO_FIELD.items()
    },
}


def _deny(reason: str) -> HookJSONOutput:
    """Builds a `PreToolUse` deny response carrying `reason` back to the model."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


class CoordinatorGuardrail:
    """Enforces pre-flight, in-flight (SDK PreToolUse hook), and post-flight rules."""

    def __init__(self, tracker: JobStore, settings: Settings) -> None:
        self.tracker = tracker
        self.settings = settings

    @property
    def processed_folder(self) -> str:
        if self.tracker.doc_type == DocumentType.JOB_POSTING:
            return self.settings.job_posting_processed_folder or f"{self.settings.job_posting_dir}/processed"
        return self.settings.coordinator_processed_folder or f"{self.settings.resume_dir}/processed"

    @property
    def failed_folder(self) -> str:
        if self.tracker.doc_type == DocumentType.JOB_POSTING:
            return self.settings.job_posting_failed_folder or f"{self.settings.job_posting_dir}/failed"
        return self.settings.coordinator_failed_folder or f"{self.settings.resume_dir}/failed"

    async def pre_execution_hook(self, file_path: str) -> list[str]:
        """Validates job state before launching Claude and returns deduplicated allowed tools."""
        status = await self.tracker.get_status(file_path)

        if status.is_completed:
            logger.info(
                "%s All fields already checkpointed for %s - marking processed",
                MODULE,
                file_path,
            )
            await self.tracker.save_session_and_completion(file_path, is_completed=True)
            file_writer(file_path, self.processed_folder)
            return []

        revision_number = await self.tracker.increment_attempts(file_path)
        max_revisions = self.settings.coordinator_max_revision_number

        if revision_number > max_revisions:
            logger.error(
                "%s %s exceeded max revision number (%d/%d) - marking failed",
                MODULE,
                file_path,
                revision_number,
                max_revisions,
            )
            file_writer(file_path, self.failed_folder)
            return []

        return list(dict.fromkeys(FIELD_TO_MCP_TOOL[field] for field in status.missing_fields))

    async def post_execution_hook(
        self,
        file_path: str,
        session_id: str | None,
        stop_reason: str | None = None,
    ) -> None:
        """Evaluates final state after stream completion, updates Redis, and routes file."""
        status = await self.tracker.get_status(file_path)
        is_max_revision = status.revision_number >= self.settings.coordinator_max_revision_number

        await self.tracker.save_session_and_completion(
            file_path=file_path,
            is_completed=status.is_completed,
            session_id=session_id,
        )

        logger.debug(
            "%s Finished | doc_type=%s | stop_reason=%s | is_completed=%s | session_id=%s | revision=%d/%d",
            MODULE,
            self.tracker.doc_type,
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
                file_path,
            )
            file_writer(file_path, self.processed_folder)
        elif is_max_revision:
            logger.error(
                "%s %s reached max revisions (%d) without completing - marking failed",
                MODULE,
                file_path,
                self.settings.coordinator_max_revision_number,
            )
            file_writer(file_path, self.failed_folder)

    def _extraction_guard(
        self,
        tool_name: str,
        base_field: str,
        file_path: str,
        formatted_tag: str,
    ) -> HookCallback:
        """Builds a `PreToolUse` callback gating `tool_name` on `base_field`'s Redis checkpoint state."""

        async def _guard(
            input_data: HookInput,
            tool_use_id: str | None,
            context: HookContext,
        ) -> HookJSONOutput:
            candidate_fields = self.tracker.get_target_fields_for_base_field(base_field)
            status = await self.tracker.wait_for_content(file_path)

            if not status.has_content:
                reason = (
                    f"Cannot execute {tool_name}: document content is not in Redis yet. "
                    f"You must emit the structured content inside <{formatted_tag}>...</{formatted_tag}> "
                    "before invoking any extraction tools."
                )
                logger.warning("%s Guardrail blocked %s: %s", MODULE, tool_name, reason)
                return _deny(reason)

            if not any(field in status.missing_fields for field in candidate_fields):
                reason = f"All fields for '{base_field}' ({', '.join(candidate_fields)}) are already checkpointed in Redis."
                logger.info("%s Guardrail skipped duplicate call to %s", MODULE, tool_name)
                return _deny(reason)

            return {}

        return _guard

    def build_sdk_hooks(self, file_path: str, formatted_tag: str = "formatted_resume") -> dict[str, list[HookMatcher]]:
        """Declares one `PreToolUse` `HookMatcher` per extraction tool for `ClaudeAgentOptions.hooks`."""
        return {
            "PreToolUse": [
                HookMatcher(
                    matcher=tool_name,
                    hooks=[self._extraction_guard(tool_name, base_field, file_path, formatted_tag)],
                )
                for tool_name, base_field in EXTRACTION_TOOL_TO_FIELD.items()
            ],
        }
