"""Tests for the prompt log writer."""

import json
from pathlib import Path

from talent_distiller_agent.observability import PromptLogWriter
from talent_distiller_agent.settings import Settings


def _settings(tmp_path: Path, observability_enabled: bool = True) -> Settings:
    return Settings(
        _env_file=None,
        observability_enabled=observability_enabled,
        prompt_log_dir=str(tmp_path / "prompt_log"),
    )


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_log_prompt_writes_one_jsonl_line_with_the_expected_fields(tmp_path: Path):
    writer = PromptLogWriter(_settings(tmp_path))

    writer.log_prompt(
        correlation_id="corr-1",
        agent="coordinator",
        model="model-x",
        system_prompt_name="resume_coordinator_orchestration",
        user_prompt="<resume_path>resume/jane.pdf</resume_path>",
        attempt=1,
    )

    lines = _read_lines(tmp_path / "prompt_log" / "corr-1.jsonl")
    assert len(lines) == 1
    assert lines[0]["correlation_id"] == "corr-1"
    assert lines[0]["service"] == "talent_distiller_agent"
    assert lines[0]["agent"] == "coordinator"
    assert lines[0]["event"] == "prompt"
    assert lines[0]["model"] == "model-x"
    assert lines[0]["system_prompt_name"] == "resume_coordinator_orchestration"
    assert lines[0]["user_prompt"] == "<resume_path>resume/jane.pdf</resume_path>"
    assert lines[0]["attempt"] == 1
    assert "timestamp" in lines[0]


def test_log_prompt_defaults_attempt_to_one(tmp_path: Path):
    writer = PromptLogWriter(_settings(tmp_path))

    writer.log_prompt(
        correlation_id="corr-2",
        agent="extract_technical_skills",
        model="model-y",
        system_prompt_name="technical_skill_extraction",
        user_prompt="Document type: resume",
    )

    lines = _read_lines(tmp_path / "prompt_log" / "corr-2.jsonl")
    assert lines[0]["attempt"] == 1


def test_log_prompt_appends_successive_attempts_to_the_same_file(tmp_path: Path):
    writer = PromptLogWriter(_settings(tmp_path))

    writer.log_prompt(
        correlation_id="corr-3",
        agent="extract_technical_skills",
        model="model-y",
        system_prompt_name="technical_skill_extraction",
        user_prompt="first attempt",
        attempt=1,
    )
    writer.log_prompt(
        correlation_id="corr-3",
        agent="extract_technical_skills",
        model="model-y",
        system_prompt_name="technical_skill_extraction",
        user_prompt="corrected attempt",
        attempt=2,
    )

    lines = _read_lines(tmp_path / "prompt_log" / "corr-3.jsonl")
    assert [line["attempt"] for line in lines] == [1, 2]


def test_log_prompt_is_a_noop_when_observability_is_disabled(tmp_path: Path):
    writer = PromptLogWriter(_settings(tmp_path, observability_enabled=False))

    writer.log_prompt(
        correlation_id="corr-4",
        agent="coordinator",
        model="model-x",
        system_prompt_name="resume_coordinator_orchestration",
        user_prompt="irrelevant",
    )

    assert not (tmp_path / "prompt_log").exists()
