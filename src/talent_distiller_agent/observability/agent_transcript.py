"""Agent transcript: the full, ordered play-by-play of one coordinator turn.

Complements the prompt log (a flat index of what was asked). The transcript replays
everything that happened in a session - assistant text, tool calls, tool results and the
final outcome - as one JSONL file per `correlation_id`; see
`documentation/prompt_log_and_agent_transcript.md` for the full design.
"""

from typing import Any

from talent_distiller_agent.settings import Settings

from ._jsonl_writer import SERVICE_NAME, append_jsonl, utc_now_iso


class AgentTranscriptWriter:
    """Appends one event line per step of a coordinator turn to `{agent_transcript_dir}/{correlation_id}.jsonl`."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _write(
        self,
        correlation_id: str,
        agent: str,
        event: str,
        *,
        session_id: str | None = None,
        **fields: Any,
    ) -> None:
        if not self.settings.observability_enabled:
            return

        record: dict[str, Any] = {
            "timestamp": utc_now_iso(),
            "correlation_id": correlation_id,
            "service": SERVICE_NAME,
            "agent": agent,
            "session_id": session_id,
            "event": event,
            **fields,
        }
        append_jsonl(self.settings.agent_transcript_dir, correlation_id, record)

    def session_start(
        self,
        correlation_id: str,
        agent: str,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        allowed_tools: list[str],
    ) -> None:
        """Records the opening of a coordinator turn, including the system prompt once."""
        self._write(
            correlation_id,
            agent,
            "session_start",
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            allowed_tools=list(allowed_tools),
        )

    def assistant_text(self, correlation_id: str, agent: str, *, text: str) -> None:
        """Records a text block emitted by the assistant."""
        self._write(correlation_id, agent, "assistant_text", text=text)

    def tool_use(
        self,
        correlation_id: str,
        agent: str,
        *,
        tool_use_id: str,
        tool_name: str,
        target_field: str,
        tool_input: Any,
    ) -> None:
        """Records a tool call the assistant dispatched."""
        self._write(
            correlation_id,
            agent,
            "tool_use",
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            target_field=target_field,
            tool_input=tool_input,
        )

    def tool_result(
        self,
        correlation_id: str,
        agent: str,
        *,
        tool_use_id: str,
        tool_name: str,
        target_field: str,
        is_error: bool,
        output: str,
    ) -> None:
        """Records the result that came back for a previously dispatched tool call."""
        self._write(
            correlation_id,
            agent,
            "tool_result",
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            target_field=target_field,
            is_error=is_error,
            output=output,
        )

    def session_end(
        self,
        correlation_id: str,
        agent: str,
        *,
        session_id: str | None,
        stop_reason: str | None,
        is_error: bool,
    ) -> None:
        """Records the closing of a coordinator turn."""
        self._write(
            correlation_id,
            agent,
            "session_end",
            session_id=session_id,
            stop_reason=stop_reason,
            is_error=is_error,
        )
