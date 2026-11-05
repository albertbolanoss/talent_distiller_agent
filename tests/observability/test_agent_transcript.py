"""Tests for the agent transcript writer."""

import json
from pathlib import Path

from talent_distiller_agent.observability import AgentTranscriptWriter
from talent_distiller_agent.settings import Settings


def _settings(tmp_path: Path, observability_enabled: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        observability_enabled=observability_enabled,
        agent_transcript_dir=str(tmp_path / "agent_transcript"),
    )


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_session_start_writes_the_system_prompt_once(tmp_path: Path):
    writer = AgentTranscriptWriter(_settings(tmp_path))

    writer.session_start(
        "corr-1",
        "coordinator",
        model="model-x",
        system_prompt="You are a coordinator.",
        user_prompt="<resume_path>resume/jane.pdf</resume_path>",
        allowed_tools=["mcp__candidate-skill-agent-technical__extract_technical_skills"],
    )

    lines = _read_lines(tmp_path / "agent_transcript" / "corr-1.jsonl")
    assert len(lines) == 1
    event = lines[0]
    assert event["correlation_id"] == "corr-1"
    assert event["service"] == "talent_distiller_agent"
    assert event["agent"] == "coordinator"
    assert event["event"] == "session_start"
    assert event["model"] == "model-x"
    assert event["system_prompt"] == "You are a coordinator."
    assert event["allowed_tools"] == ["mcp__candidate-skill-agent-technical__extract_technical_skills"]
    assert event["session_id"] is None


def test_assistant_text_writes_the_text_block(tmp_path: Path):
    writer = AgentTranscriptWriter(_settings(tmp_path))

    writer.assistant_text("corr-2", "coordinator", text="DONE")

    lines = _read_lines(tmp_path / "agent_transcript" / "corr-2.jsonl")
    assert lines[0]["event"] == "assistant_text"
    assert lines[0]["text"] == "DONE"


def test_tool_use_writes_the_dispatched_tool_call(tmp_path: Path):
    writer = AgentTranscriptWriter(_settings(tmp_path))

    writer.tool_use(
        "corr-3",
        "coordinator",
        tool_use_id="tool-1",
        tool_name="mcp__candidate-skill-agent-technical__extract_technical_skills",
        target_field="technical_skills",
        tool_input={"content": "..."},
    )

    lines = _read_lines(tmp_path / "agent_transcript" / "corr-3.jsonl")
    assert lines[0]["event"] == "tool_use"
    assert lines[0]["tool_use_id"] == "tool-1"
    assert lines[0]["tool_name"] == "mcp__candidate-skill-agent-technical__extract_technical_skills"
    assert lines[0]["target_field"] == "technical_skills"
    assert lines[0]["tool_input"] == {"content": "..."}


def test_tool_result_writes_the_returned_output(tmp_path: Path):
    writer = AgentTranscriptWriter(_settings(tmp_path))

    writer.tool_result(
        "corr-4",
        "coordinator",
        tool_use_id="tool-1",
        tool_name="mcp__candidate-skill-agent-technical__extract_technical_skills",
        target_field="technical_skills",
        is_error=False,
        output='[{"skill": "Python"}]',
    )

    lines = _read_lines(tmp_path / "agent_transcript" / "corr-4.jsonl")
    assert lines[0]["event"] == "tool_result"
    assert lines[0]["is_error"] is False
    assert lines[0]["output"] == '[{"skill": "Python"}]'


def test_session_end_writes_the_final_outcome(tmp_path: Path):
    writer = AgentTranscriptWriter(_settings(tmp_path))

    writer.session_end(
        "corr-5",
        "coordinator",
        session_id="session-123",
        stop_reason="end_turn",
        is_error=False,
    )

    lines = _read_lines(tmp_path / "agent_transcript" / "corr-5.jsonl")
    assert lines[0]["event"] == "session_end"
    assert lines[0]["session_id"] == "session-123"
    assert lines[0]["stop_reason"] == "end_turn"
    assert lines[0]["is_error"] is False


def test_events_for_the_same_correlation_id_append_in_order(tmp_path: Path):
    writer = AgentTranscriptWriter(_settings(tmp_path))

    writer.assistant_text("corr-6", "coordinator", text="first")
    writer.assistant_text("corr-6", "coordinator", text="second")

    lines = _read_lines(tmp_path / "agent_transcript" / "corr-6.jsonl")
    assert [line["text"] for line in lines] == ["first", "second"]


def test_every_event_is_a_noop_when_observability_is_disabled(tmp_path: Path):
    writer = AgentTranscriptWriter(_settings(tmp_path, observability_enabled=False))

    writer.session_start(
        "corr-7", "coordinator", model="model-x", system_prompt="x", user_prompt="x", allowed_tools=[]
    )
    writer.assistant_text("corr-7", "coordinator", text="x")
    writer.tool_use(
        "corr-7", "coordinator", tool_use_id="x", tool_name="x", target_field="x", tool_input={}
    )
    writer.tool_result(
        "corr-7",
        "coordinator",
        tool_use_id="x",
        tool_name="x",
        target_field="x",
        is_error=False,
        output="x",
    )
    writer.session_end("corr-7", "coordinator", session_id=None, stop_reason=None, is_error=False)

    assert not (tmp_path / "agent_transcript").exists()
